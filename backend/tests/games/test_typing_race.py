"""Typing Race: countdown, prefix judging, anti-cheat, finishing, clock, standings, views."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from contextlib import ExitStack
from typing import Any

import pytest

from app.games.base import GameError, Placing
from app.games.typing_passages import PASSAGES
from app.games.typing_race import (
    COUNTDOWN_MS,
    LENGTHS,
    TypingRaceEngine,
    correct_prefix,
    ordinal,
)


class FakeTime:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def t() -> FakeTime:
    return FakeTime()


@pytest.fixture
def e(t: FakeTime) -> TypingRaceEngine:
    return TypingRaceEngine(clock=t)


def race(e: TypingRaceEngine, players: list[str] | None = None, length: str = "short",
         seed: int = 1) -> dict:
    return e.start(players or ["a", "b"], random.Random(seed), {"length": length})


def go(t: FakeTime, seconds: float = 0.0) -> None:
    """Advance past the countdown, then ``seconds`` more."""
    t.now += COUNTDOWN_MS / 1000 + seconds


def type_(e: TypingRaceEngine, state: dict, player: str, typed: str) -> dict:
    return e.apply(state, player, {"type": "progress", "typed": typed}, random.Random(1))


def finish(e: TypingRaceEngine, state: dict, player: str) -> dict:
    return type_(e, state, player, state["passage"])


def places(placings: list[Placing]) -> list[tuple[str, int, str]]:
    return [(p.player, p.place, p.detail) for p in placings]


# -- passages and options --------------------------------------------------------------


def test_passages_are_plain_ascii_in_three_lengths() -> None:
    bounds = {"short": (100, 150), "medium": (200, 280), "long": (350, 450)}
    assert set(PASSAGES) == set(LENGTHS) == set(bounds)
    assert sum(len(v) for v in PASSAGES.values()) >= 30
    for length, passages in PASSAGES.items():
        low, high = bounds[length]
        assert len(set(passages)) == len(passages)
        for p in passages:
            assert low <= len(p) <= high, (length, len(p), p)
            assert p.isascii() and p.isprintable() and "  " not in p and p == p.strip()
            assert '"' not in p and "`" not in p


def test_options_validation(e: TypingRaceEngine) -> None:
    for length in ("short", "medium", "long"):
        assert e.validate_options({"length": length}) == {"length": length}
    assert e.validate_options(None) == {"length": "medium"}
    assert e.validate_options({}) == {"length": "medium"}
    assert e.validate_options({"length": None}) == {"length": "medium"}
    with pytest.raises(GameError, match="short, medium or long"):
        e.validate_options({"length": "epic"})
    with pytest.raises(GameError, match="short, medium or long"):
        e.validate_options({"length": 3})
    with pytest.raises(GameError, match="Unknown Typing Race option"):
        e.validate_options({"time_control": "1+0"})
    assert e.options_label({"length": "short"}) == "Short passage"
    assert e.options_label({"length": "medium"}) == "Medium passage"
    assert e.options_label({"length": "long"}) == "Long passage"
    assert e.options_label({}) == "Medium passage"


def test_length_picks_passage_and_time_limit(e: TypingRaceEngine, t: FakeTime) -> None:
    for length, (limit, _) in LENGTHS.items():
        state = race(e, length=length)
        assert state["passage"] in PASSAGES[length]
        assert state["start_at"] == int(t.now * 1000) + COUNTDOWN_MS
        assert state["ends_at"] == state["start_at"] + limit * 1000
        assert e.deadline(state) == pytest.approx(state["ends_at"] / 1000)
    # new_game alone (no options) is a medium race; the RNG decides which passage.
    plain = e.new_game(["a", "b"], random.Random(5))
    assert plain["passage"] in PASSAGES["medium"]
    picks = {race(e, length="long", seed=s)["passage"] for s in range(40)}
    assert len(picks) > 3
    assert race(e, seed=9)["passage"] == race(e, seed=9)["passage"]  # reproducible


# -- countdown and judging ---------------------------------------------------------------


def test_progress_rejected_during_countdown(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e)
    with pytest.raises(GameError, match="The race has not started"):
        type_(e, state, "a", state["passage"][:1])
    t.now += 4.99
    with pytest.raises(GameError, match="The race has not started"):
        type_(e, state, "a", "")
    t.now += 0.01
    assert type_(e, state, "a", state["passage"][:3])["progress"]["a"]["pos"] == 3


def test_prefix_logic_typos_and_backspace(e: TypingRaceEngine, t: FakeTime) -> None:
    assert correct_prefix("Thw quick", "The quick") == 2
    assert correct_prefix("", "abc") == 0
    assert correct_prefix("abcdef", "abc") == 3
    state = race(e)
    passage = state["passage"]
    go(t, 10)
    state = type_(e, state, "a", passage[:20])
    assert state["progress"]["a"]["pos"] == 20
    # A typo at index 12: everything after it does not count.
    typo = passage[:12] + ("#" if passage[12] != "#" else "!") + passage[13:25]
    state = type_(e, state, "a", typo)
    assert state["progress"]["a"]["pos"] == 12  # progress can go down
    # Backspacing over the typo and carrying on.
    state = type_(e, state, "a", passage[:12])
    state = type_(e, state, "a", passage[:30])
    assert state["progress"]["a"]["pos"] == 30
    assert state["progress"]["b"]["pos"] == 0


def test_malformed_and_overlong_reports(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e)
    go(t, 30)
    for bad in (None, 5, ["a"], {"x": 1}):
        with pytest.raises(GameError, match="as text"):
            e.apply(state, "a", {"type": "progress", "typed": bad}, random.Random(1))
    with pytest.raises(GameError, match="as text"):
        e.apply(state, "a", {"type": "progress"}, random.Random(1))
    with pytest.raises(GameError, match="longer than the passage"):
        type_(e, state, "a", state["passage"][:-1] + "x" * 12)
    type_(e, state, "a", state["passage"][:-1] + "x" * 11)  # a few extra characters are fine
    with pytest.raises(GameError, match="Unknown action"):
        e.apply(state, "a", {"type": "finish"}, random.Random(1))
    with pytest.raises(GameError, match="not playing"):
        type_(e, state, "zed", "x")


def test_anti_cheat_rejects_superhuman_speed(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e)
    passage = state["passage"]
    go(t, 0.0)
    assert type_(e, state, "a", passage[:10])["progress"]["a"]["pos"] == 10  # slack
    with pytest.raises(GameError, match="Too fast.*300 WPM"):
        type_(e, state, "a", passage)  # a paste at GO
    t.now += 2  # 2 s: at most 2 * 25 + 10 = 60 characters
    assert type_(e, state, "a", passage[:60])["progress"]["a"]["pos"] == 60
    with pytest.raises(GameError, match="Too fast"):
        type_(e, state, "a", passage[:61])
    # Garbage after the correct prefix does not count towards the limit.
    assert type_(e, state, "a", passage[:60] + "#" * 5)["progress"]["a"]["pos"] == 60


# -- finishing ---------------------------------------------------------------------------


def test_finishing_order_wpm_and_end(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e, ["a", "b", "c"])
    n = len(state["passage"])
    go(t, 30)
    state = finish(e, state, "b")
    mine = state["progress"]["b"]
    assert mine["finished_at"] == int(t.now * 1000) and mine["place"] == 1
    assert mine["wpm"] == round((n / 5) / 0.5)  # n characters in 30 s
    assert state["log"][-1] == f"{{{{b}}}} finished 1st at {mine['wpm']} WPM"
    assert e.outcome(state) is None and e.awaiting(state) == ["a", "c"]
    with pytest.raises(GameError, match="already finished"):
        finish(e, state, "b")
    t.now += 30
    state = finish(e, state, "a")
    assert state["progress"]["a"]["place"] == 2
    assert state["progress"]["a"]["wpm"] == round((n / 5) / 1.0)
    assert "finished 2nd" in state["log"][-1]
    assert e.outcome(state) is None
    t.now += 15
    state = finish(e, state, "c")
    assert "finished 3rd" in state["log"][-2] and "Race over" in state["log"][-1]
    outcome = e.outcome(state)
    assert outcome is not None and outcome.winners == ["b"] and not outcome.draw
    assert outcome.reason == f"Finished first at {state['progress']['b']['wpm']} WPM"
    assert e.awaiting(state) == [] and e.deadline(state) is None
    assert places(e.standings(state)) == [
        ("b", 1, f"{state['progress']['b']['wpm']} WPM"),
        ("a", 2, f"{state['progress']['a']['wpm']} WPM"),
        ("c", 3, f"{state['progress']['c']['wpm']} WPM"),
    ]
    with pytest.raises(GameError, match="The game is over"):
        type_(e, state, "a", "x")


def test_same_millisecond_finish_shares_the_win(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e)
    go(t, 20)
    state = finish(e, finish(e, state, "a"), "b")
    assert state["progress"]["b"]["place"] == 1
    assert e.outcome(state).winners == ["a", "b"]
    assert [p.place for p in e.standings(state)] == [1, 1]


# -- the clock ---------------------------------------------------------------------------


def test_expire_with_finishers(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e, ["a", "b", "c"])
    n = len(state["passage"])
    go(t, 40)
    state = finish(e, state, "c")
    state = type_(e, state, "a", state["passage"][: n // 2])
    state = type_(e, state, "b", state["passage"][: n // 4])
    t.now = state["ends_at"] / 1000 - 0.01
    assert e.expire(state) is state
    t.now += 0.02
    expired = e.expire(state)
    assert expired is not state and e.outcome(state) is None  # original untouched
    outcome = e.outcome(expired)
    assert outcome.winners == ["c"] and outcome.reason.startswith("Finished first at")
    assert e.deadline(expired) is None and e.expire(expired) is expired
    assert places(e.standings(expired)) == [
        ("c", 1, f"{expired['progress']['c']['wpm']} WPM"),
        ("a", 2, f"{(n // 2) * 100 // n}% complete"),
        ("b", 3, f"{(n // 4) * 100 // n}% complete"),
    ]


def test_expire_without_finishers_furthest_wins(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e, ["a", "b", "c"])
    go(t, 20)
    state = type_(e, state, "a", state["passage"][:40])
    state = type_(e, state, "b", state["passage"][:70])
    state = type_(e, state, "c", state["passage"][:70])
    t.now = state["ends_at"] / 1000
    outcome = e.outcome(e.expire(state))
    assert outcome.winners == ["b", "c"] and not outcome.draw  # ties share the win
    assert outcome.reason == "Time's up"
    assert [p.place for p in e.standings(e.expire(state))] == [1, 1, 3]


def test_expire_with_nobody_typing_is_a_draw(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e)
    t.now = state["ends_at"] / 1000 + 5
    outcome = e.outcome(e.expire(state))
    assert outcome.draw and outcome.winners == [] and outcome.reason == "Time's up"
    tied = race(e)
    go(t, 0)
    t.now = tied["start_at"] / 1000 + 10
    tied = type_(e, type_(e, tied, "a", tied["passage"][:50]), "b", tied["passage"][:50])
    t.now = tied["ends_at"] / 1000
    assert e.outcome(e.expire(tied)).draw  # everyone level: nobody beat anybody


def test_late_report_ends_the_race_instead(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e)
    go(t, 30)
    state = type_(e, state, "a", state["passage"][:50])
    t.now = state["ends_at"] / 1000 + 0.2
    late = finish(e, state, "b")  # arrived after the close: not counted
    assert late["progress"]["b"]["finished_at"] is None
    assert e.outcome(late).winners == ["a"] and e.outcome(late).reason == "Time's up"


# -- leaving -----------------------------------------------------------------------------


def test_last_player_standing_wins(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e, ["a", "b", "c"])
    go(t, 10)
    state = e.remove_player(state, "a")
    assert e.outcome(state) is None and state["players"] == ["b", "c"]
    assert "a" not in state["progress"] and "left the race" in state["log"][-1]
    state = e.remove_player(state, "c")
    outcome = e.outcome(state)
    assert outcome.winners == ["b"] and outcome.reason == "Everyone else left"
    assert e.deadline(state) is None


def test_leaving_can_complete_the_race(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e, ["a", "b", "c"])
    go(t, 30)
    state = finish(e, state, "a")
    t.now += 1
    state = finish(e, state, "b")
    state = e.remove_player(state, "c")  # the only one still typing gives up
    outcome = e.outcome(state)
    assert outcome.winners == ["a"] and outcome.reason.startswith("Finished first")
    assert [p.player for p in e.standings(state)] == ["a", "b"]


def test_winner_leaving_after_finishing(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e, ["a", "b", "c"])
    go(t, 30)
    state = finish(e, state, "a")
    t.now += 1
    state = finish(e, state, "b")
    assert state["progress"]["b"]["place"] == 2
    state = e.remove_player(state, "a")
    t.now = state["ends_at"] / 1000
    assert e.outcome(e.expire(state)).winners == ["b"]


# -- views -------------------------------------------------------------------------------


def test_views_count_down_and_report_progress(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e, ["a", "b"], length="short")
    view = e.view(state, "a")
    assert view["phase"] == "countdown" and view["starts_in_ms"] == COUNTDOWN_MS
    assert view["ends_in_ms"] == COUNTDOWN_MS + 90_000 and view["limit_ms"] == 90_000
    assert view["passage"] == state["passage"] and view["length_label"] == "Short passage"
    assert view["me"]["id"] == "a" and view["me"]["pos"] == 0 and view["results"] is None
    assert "seed" not in view and "progress" not in view
    t.now += 2
    assert e.view(state, "a")["starts_in_ms"] == COUNTDOWN_MS - 2000
    t.now += 3 + 12  # 12 s into the race
    state = type_(e, state, "a", state["passage"][:50])
    view = e.view(state, "b")
    assert view["phase"] == "racing" and view["starts_in_ms"] == 0
    assert view["elapsed_ms"] == 12_000 and view["ends_in_ms"] == 78_000
    a, b = view["racers"]
    n = len(state["passage"])
    assert a == {"id": "a", "pos": 50, "percent": 50 * 100 // n, "finished": False,
                 "place": None, "wpm": 50, "time_ms": None}  # 10 words in 12 s
    assert b["pos"] == 0 and b["wpm"] == 0
    assert view["me"] == b
    # A spectator (the host) sees everything public and has no status of their own.
    spectator = e.view(state, None)
    assert spectator["me"] is None and spectator["racers"] == view["racers"]
    t.now += 18
    state = finish(e, state, "a")
    mine = e.view(state, "a")["me"]
    assert mine["finished"] and mine["place"] == 1 and mine["percent"] == 100
    assert mine["time_ms"] == 30_000 and mine["wpm"] == round((n / 5) / 0.5)


def test_view_when_over_has_results(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e, ["a", "b"])
    go(t, 30)
    state = finish(e, state, "b")
    state = type_(e, state, "a", state["passage"][:30])
    t.now = state["ends_at"] / 1000 + 1
    state = e.expire(state)
    t.now += 100  # frozen once over
    view = e.view(state, "a")
    assert view["phase"] == "over" and view["ends_in_ms"] == 0
    assert view["elapsed_ms"] == state["limit_ms"]
    assert view["result"]["winners"] == ["b"]
    assert [(r["id"], r["place"], r["finished"]) for r in view["results"]] == [
        ("b", 1, True), ("a", 2, False)]
    assert view["results"][1]["detail"].endswith("% complete")
    assert view["results"][1]["wpm"] == round((30 / 5) / (state["limit_ms"] / 60_000))


def test_helpers() -> None:
    assert [ordinal(i) for i in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st"]


# -- API integration ---------------------------------------------------------------------


def api_move(view: dict[str, Any]) -> dict[str, Any] | None:
    """A bot for the API integration test: type as much as the anti-cheat allows.

    Returns None during the countdown and once finished. The limit is computed from the
    view's elapsed time, which is a lower bound by the time the report arrives.
    """
    me = view.get("me")
    if view["phase"] != "racing" or not me or me["finished"]:
        return None
    passage = view["passage"]
    allowed = int(view["elapsed_ms"] * 25 / 1000) + 5
    return {"type": "progress", "typed": passage[: max(me["pos"], min(len(passage), allowed))]}


def skip_countdown(monkeypatch: pytest.MonkeyPatch, engine: TypingRaceEngine,
                   seconds: float = 30.0) -> None:
    """Jump the engine clock ahead (after the game started) so a race is ready to finish.

    30 s past the start allows 25 * 25 + 10 = 635 characters, more than any passage,
    while staying well inside even the short race's 90 s limit.
    """
    real = time.time
    monkeypatch.setattr(engine, "clock", lambda: real() + seconds)


def test_api_move_respects_the_limit(e: TypingRaceEngine, t: FakeTime) -> None:
    state = race(e, length="long")
    assert api_move(e.view(state, "a")) is None
    assert api_move(e.view(state, None)) is None
    go(t, 0.5)
    move = api_move(e.view(state, "a"))
    assert move is not None and len(move["typed"]) == 17
    state = e.apply(state, "a", move, random.Random(1))
    for _ in range(40):
        t.now += 0.5
        view = e.view(state, "a")
        if (move := api_move(view)) is None:
            break
        state = e.apply(state, "a", move, random.Random(1))
    assert state["progress"]["a"]["finished_at"] is not None


def test_race_through_the_api(monkeypatch: pytest.MonkeyPatch, admin: Any,
                              approved_player: Callable[[str], Any]) -> None:
    from app.games import registry
    from tests.conftest import receive_until

    engine = TypingRaceEngine()
    monkeypatch.setitem(registry.GAMES, "typing", engine)
    bad = admin.post("/api/admin/rooms", json={
        "game_type": "typing", "name": "Bad", "options": {"length": "huge"}})
    assert bad.status_code == 400 and "short, medium or long" in bad.json()["detail"]

    a, b = approved_player("Alpha"), approved_player("Beta")
    with ExitStack() as stack:
        sockets = [stack.enter_context(p.ws("/ws/player")) for p in (a, b)]
        for ws in sockets:
            ws.receive_json()
        room_id = admin.post("/api/admin/rooms", json={
            "game_type": "typing", "name": "Race", "max_players": 2,
            "options": {"length": "short"}}).json()["id"]
        for p in (a, b):
            assert p.post(f"/api/rooms/{room_id}/join").status_code == 200
            p.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
        assert admin.post(f"/api/admin/rooms/{room_id}/start").status_code == 200
        state = a.get("/api/state").json()
        assert state["room"]["options_label"] == "Short passage"
        game = state["game"]
        assert game["phase"] == "countdown" and game["passage"] in PASSAGES["short"]
        early = a.post(f"/api/rooms/{room_id}/actions",
                       json={"action": {"type": "progress", "typed": game["passage"][:1]}})
        assert early.status_code == 400 and "not started" in early.json()["detail"]
        paste = {"type": "progress", "typed": game["passage"]}

        skip_countdown(monkeypatch, engine, seconds=COUNTDOWN_MS / 1000 + 0.5)
        cheat = a.post(f"/api/rooms/{room_id}/actions", json={"action": paste})
        assert cheat.status_code == 400 and "Too fast" in cheat.json()["detail"]

        skip_countdown(monkeypatch, engine)
        moves = 0
        for _ in range(10):
            states = [p.get("/api/state").json() for p in (a, b)]
            if states[0]["room"]["status"] == "COMPLETED":
                break
            for player, s in zip((a, b), states, strict=True):
                move = api_move(s["game"])
                if move is None:
                    continue
                response = player.post(f"/api/rooms/{room_id}/actions", json={"action": move})
                assert response.status_code == 200, (move, response.text)
                moves += 1
                break
            else:
                pytest.fail("no player could move")
        message = receive_until(sockets[1], lambda m: (m.get("room") or {}).get("status")
                                == "COMPLETED", limit=50)
        result = message["room"]["result"]
        assert moves == 2 and result["outcome"] == "WIN" and result["winners"] == ["Alpha"]
        assert result["reason"].startswith("Finished first at")
        assert [(s["nickname"], s["place"]) for s in result["standings"]] == [
            ("Alpha", 1), ("Beta", 2)]
        assert all(s["detail"].endswith(" WPM") for s in result["standings"])
        assert message["game"]["phase"] == "over" and message["game"]["results"][0]["place"] == 1
