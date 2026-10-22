"""Typing Race: everyone types the same passage; first to finish wins.

Rules: docs/games/typing-race.md. The server owns the timeline (countdown, start, close)
and judges every progress report against the passage, so a browser can only claim
characters it actually typed correctly, and no faster than a human could.
"""

from __future__ import annotations

import copy
import random
import time
from collections.abc import Callable
from typing import Any

from app.games.base import (
    Action,
    GameEngine,
    GameError,
    GameInfo,
    Options,
    Outcome,
    Placing,
    State,
    log,
    rank,
    who,
)
from app.games.typing_passages import PASSAGES

COUNTDOWN_MS = 5_000
# Race length option -> (time limit in seconds, label).
LENGTHS: dict[str, tuple[int, str]] = {
    "short": (90, "Short passage"),
    "medium": (150, "Medium passage"),
    "long": (240, "Long passage"),
}
DEFAULT_LENGTH = "medium"
# Anti-cheat: nobody types more than ~300 WPM (25 chars/s); the slack absorbs latency.
MAX_CHARS_PER_SECOND = 25
SLACK_CHARS = 10
# How far past the end of the passage a report may run (typos after the last word).
MAX_EXTRA_CHARS = 10


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def correct_prefix(typed: str, passage: str) -> int:
    """Length of the longest prefix of ``typed`` that matches the passage."""
    pos = 0
    for a, b in zip(typed, passage, strict=False):
        if a != b:
            break
        pos += 1
    return pos


def wpm(chars: int, elapsed_ms: int) -> float:
    """Words per minute, with the standard five characters per word."""
    if chars <= 0 or elapsed_ms <= 0:
        return 0.0
    return (chars / 5) / (elapsed_ms / 60_000)


class TypingRaceEngine(GameEngine):
    info = GameInfo("typing", "Typing Race", 2, 8,
                    "Race to type the same passage. Fastest accurate typist wins.")
    timed = True

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock  # wall-clock seconds; injectable for tests

    def now(self) -> float:
        return self.clock()

    def _now_ms(self) -> int:
        return int(self.clock() * 1000)

    # -- options -----------------------------------------------------------------------

    def validate_options(self, options: Options | None) -> Options:
        options = dict(options or {})
        length = options.pop("length", None)
        if options:
            raise GameError("Unknown Typing Race option")
        if length in (None, ""):
            return {"length": DEFAULT_LENGTH}
        if not isinstance(length, str) or length not in LENGTHS:
            raise GameError("Passage length must be short, medium or long")
        return {"length": length}

    def options_label(self, options: Options) -> str | None:
        length = (options or {}).get("length")
        return LENGTHS[length if length in LENGTHS else DEFAULT_LENGTH][1]

    def configure(self, state: State, options: Options) -> None:
        length = options.get("length", DEFAULT_LENGTH)
        if length not in LENGTHS or length == state["length"]:
            return
        self._set_passage(state, length)

    @staticmethod
    def _set_passage(state: State, length: str) -> None:
        # The seed was drawn from the game RNG in new_game(), so the choice stays
        # reproducible however the room options arrive.
        choices = PASSAGES[length]
        state["length"] = length
        state["passage"] = choices[random.Random(state["seed"]).randrange(len(choices))]
        state["limit_ms"] = LENGTHS[length][0] * 1000
        state["ends_at"] = state["start_at"] + state["limit_ms"]

    # -- game --------------------------------------------------------------------------

    def new_game(self, players: list[str], rng: random.Random) -> State:
        state: State = {
            "players": list(players),
            "seed": rng.randrange(2**31),
            "length": DEFAULT_LENGTH,
            "passage": "",
            "start_at": self._now_ms() + COUNTDOWN_MS,   # epoch ms; typing opens here
            "limit_ms": 0,
            "ends_at": 0,                                 # epoch ms; the race closes here
            "progress": {p: {"pos": 0, "finished_at": None, "wpm": None, "place": None}
                         for p in players},
            "finishers": [],                              # in finishing order
            "result": None,                               # {"winners", "draw", "reason"}
            "ended_at": None,
            "log": [],
        }
        self._set_passage(state, DEFAULT_LENGTH)
        return state

    def _apply(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        now = self._now_ms()
        if now >= state["ends_at"]:
            self._close(state, now)  # time ran out before this report arrived
            return
        if action["type"] != "progress":
            raise GameError("Unknown action")
        self._progress(state, player, action, now)

    def _progress(self, state: State, player: str, action: Action, now: int) -> None:
        if now < state["start_at"]:
            raise GameError("The race has not started")
        mine = state["progress"][player]
        if mine["finished_at"] is not None:
            raise GameError("You have already finished")
        typed = action.get("typed")
        passage = state["passage"]
        if not isinstance(typed, str):
            raise GameError("Send what you have typed as text")
        if len(typed) > len(passage) + MAX_EXTRA_CHARS:
            raise GameError("That is longer than the passage")
        pos = correct_prefix(typed, passage)
        elapsed_ms = now - state["start_at"]
        if pos > elapsed_ms * MAX_CHARS_PER_SECOND / 1000 + SLACK_CHARS:
            raise GameError("Too fast to be real typing (over 300 WPM): progress not accepted")
        mine["pos"] = pos
        if pos < len(passage):
            return
        mine["finished_at"] = now
        mine["wpm"] = round(wpm(len(passage), elapsed_ms))
        previous = state["finishers"][-1] if state["finishers"] else None
        # Finishing in the same millisecond shares the place.
        if previous and state["progress"][previous]["finished_at"] == now:
            mine["place"] = state["progress"][previous]["place"]
        else:
            mine["place"] = len(state["finishers"]) + 1
        state["finishers"].append(player)
        log(state, f"{who(player)} finished {ordinal(mine['place'])} at {mine['wpm']} WPM")
        if all(state["progress"][p]["finished_at"] is not None for p in state["players"]):
            self._end(state, now, "Everyone finished")

    def _end(self, state: State, now: int, why: str) -> None:
        """Decide the result from the finishers, or else from progress."""
        players = state["players"]
        progress = state["progress"]
        finishers = [p for p in state["finishers"] if p in players]
        if finishers:
            best_place = min(progress[p]["place"] for p in finishers)
            firsts = [p for p in finishers if progress[p]["place"] == best_place]
            speed = progress[firsts[0]]["wpm"]
            state["result"] = {"winners": firsts, "draw": False,
                               "reason": f"Finished first at {speed} WPM"}
        else:
            best = max((progress[p]["pos"] for p in players), default=0)
            leaders = [p for p in players if progress[p]["pos"] == best]
            if best == 0 or (len(leaders) == len(players) and len(players) > 1):
                state["result"] = {"winners": [], "draw": True, "reason": "Time's up"}
            else:
                state["result"] = {"winners": leaders, "draw": False, "reason": "Time's up"}
        state["ended_at"] = now
        log(state, f"Race over: {why.lower()}")

    def _close(self, state: State, now: int) -> None:
        if state["result"] is None:
            self._end(state, now, "Time's up")

    def deadline(self, state: State) -> float | None:
        if state["result"] is not None:
            return None
        return state["ends_at"] / 1000

    def expire(self, state: State) -> State:
        due = self.deadline(state)
        if due is None or self.now() < due:
            return state
        new_state = copy.deepcopy(state)
        self._close(new_state, self._now_ms())
        return new_state

    def _remove_player(self, state: State, player: str) -> None:
        state["players"].remove(player)
        state["progress"].pop(player, None)
        if player in state["finishers"]:
            state["finishers"].remove(player)
        log(state, f"{who(player)} left the race")
        players = state["players"]
        now = self._now_ms()
        if len(players) == 1:
            state["result"] = {"winners": list(players), "draw": False,
                               "reason": "Everyone else left"}
            state["ended_at"] = now
        elif all(state["progress"][p]["finished_at"] is not None for p in players):
            self._end(state, now, "Everyone finished")

    def awaiting(self, state: State) -> list[str]:
        if state["result"] is not None:
            return []
        return [p for p in state["players"] if state["progress"][p]["finished_at"] is None]

    def outcome(self, state: State) -> Outcome | None:
        result = state["result"]
        if result is None:
            return None
        return Outcome(winners=list(result["winners"]), draw=result["draw"],
                       reason=result["reason"])

    def standings(self, state: State) -> list[Placing]:
        length = len(state["passage"])
        entries: list[tuple[str, tuple[Any, ...], str]] = []
        for p in state["players"]:
            mine = state["progress"][p]
            if mine["finished_at"] is not None:
                entries.append((p, (1, -mine["finished_at"]), f"{mine['wpm']} WPM"))
            else:
                entries.append((p, (0, mine["pos"]), f"{mine['pos'] * 100 // length}% complete"))
        return rank(entries)

    # -- view --------------------------------------------------------------------------

    def view(self, state: State, player: str | None) -> dict[str, Any]:
        now = self._now_ms()
        over = state["result"] is not None
        clock = min(now, state["ended_at"] or now, state["ends_at"])
        elapsed = max(0, clock - state["start_at"])
        length = len(state["passage"])
        racers = []
        for p in state["players"]:
            mine = state["progress"][p]
            finished = mine["finished_at"] is not None
            racers.append({
                "id": p,
                "pos": mine["pos"],
                "percent": mine["pos"] * 100 // length,
                "finished": finished,
                "place": mine["place"],
                "wpm": mine["wpm"] if finished else round(wpm(mine["pos"], elapsed)),
                "time_ms": mine["finished_at"] - state["start_at"] if finished else None,
            })
        me = next((r for r in racers if r["id"] == player), None)
        if over:
            phase = "over"
        elif now < state["start_at"]:
            phase = "countdown"
        else:
            phase = "racing"
        return {
            "players": state["players"],
            "length": state["length"],
            "length_label": LENGTHS[state["length"]][1],
            "passage": state["passage"],
            "phase": phase,
            # Relative times as of this view: browsers count down locally from here.
            "starts_in_ms": max(0, state["start_at"] - now),
            "ends_in_ms": 0 if over else max(0, state["ends_at"] - now),
            "elapsed_ms": elapsed,
            "limit_ms": state["limit_ms"],
            "racers": racers,
            "me": me,
            "result": state["result"],
            "results": [
                {"id": pl.player, "place": pl.place, "detail": pl.detail,
                 "wpm": next(r["wpm"] for r in racers if r["id"] == pl.player),
                 "finished": state["progress"][pl.player]["finished_at"] is not None}
                for pl in self.standings(state)
            ] if over else None,
            "log": state["log"],
        }
