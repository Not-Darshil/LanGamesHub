"""Chess engine on top of python-chess. Rules: docs/games/chess.md."""

from __future__ import annotations

import copy
import random
import time
from collections.abc import Callable
from typing import Any

import chess

from app.games.base import (
    Action,
    GameEngine,
    GameError,
    GameInfo,
    Options,
    Outcome,
    State,
    log,
    who,
)

TERMINATION_REASONS = {
    chess.Termination.CHECKMATE: "Checkmate",
    chess.Termination.STALEMATE: "Stalemate",
    chess.Termination.INSUFFICIENT_MATERIAL: "Insufficient material",
    chess.Termination.SEVENTYFIVE_MOVES: "Seventy-five-move rule",
    chess.Termination.FIVEFOLD_REPETITION: "Fivefold repetition",
}


# Time controls offered when creating a room: key -> (minutes, increment seconds, label).
TIME_CONTROLS: dict[str, tuple[int, int, str]] = {
    "1+0": (1, 0, "Bullet"),
    "3+2": (3, 2, "Blitz"),
    "5+0": (5, 0, "Blitz"),
    "10+0": (10, 0, "Rapid"),
    "15+10": (15, 10, "Rapid"),
    "30+0": (30, 0, "Classical"),
}


def time_control_label(key: str) -> str:
    minutes, increment, kind = TIME_CONTROLS[key]
    return f"{minutes} min" + (f" + {increment}s" if increment else "") + f" · {kind}"


def claimable_draw(board: chess.Board) -> str | None:
    """A draw the player to move may claim now, based on moves already played.

    Stricter than python-chess's can_claim_draw(), which also counts a repetition the
    claimant could create with their next move (FIDE requires naming that move).
    """
    if board.is_repetition(3):
        return "Threefold repetition"
    if board.halfmove_clock >= 100:
        return "Fifty-move rule"
    return None


def board_for(state: State) -> chess.Board:
    board = chess.Board(state["initial_fen"])
    for uci in state["moves"]:
        board.push_uci(uci)
    return board


def _color_name(color: chess.Color) -> str:
    return "white" if color == chess.WHITE else "black"


class ChessEngine(GameEngine):
    info = GameInfo("chess", "Chess", 2, 2, "Classic chess with full FIDE move rules.")
    timed = True

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock  # wall-clock seconds; injectable for tests

    def now(self) -> float:
        return self.clock()

    def _now_ms(self) -> int:
        return int(self.clock() * 1000)

    # -- options and clock -------------------------------------------------------------

    def validate_options(self, options: Options | None) -> Options:
        options = dict(options or {})
        control = options.pop("time_control", None)
        if options:
            raise GameError("Unknown chess option")
        if control in (None, "", "none"):
            return {}
        if not isinstance(control, str) or control not in TIME_CONTROLS:
            raise GameError("Unknown time control")
        return {"time_control": control}

    def options_label(self, options: Options) -> str | None:
        control = (options or {}).get("time_control")
        return time_control_label(control) if control in TIME_CONTROLS else "No clock"

    def configure(self, state: State, options: Options) -> None:
        control = options.get("time_control")
        if control not in TIME_CONTROLS:
            return
        minutes, increment, _ = TIME_CONTROLS[control]
        initial = minutes * 60_000
        # Clocks start once White has made the first move.
        state["clock"] = {
            "control": control,
            "initial_ms": initial,
            "increment_ms": increment * 1000,
            "remaining": {"white": initial, "black": initial},
            "running": None,
            "since": None,
        }

    @staticmethod
    def _left(clock: dict[str, Any], color: str, now: int) -> int:
        """Milliseconds ``color`` has left at ``now`` (may be negative once flagged)."""
        left = clock["remaining"][color]
        if clock["running"] == color:
            left -= now - clock["since"]
        return left

    def _stop_clock(self, state: State, now: int) -> None:
        clock = state.get("clock")
        if clock and clock["running"]:
            clock["remaining"][clock["running"]] = max(0, self._left(clock, clock["running"], now))
            clock["running"] = None
            clock["since"] = None

    def _flag(self, state: State, board: chess.Board, now: int) -> bool:
        """End the game if the side to move has run out of time. Returns True if so."""
        clock = state.get("clock")
        if not clock or not clock["running"] or state["result"] is not None:
            return False
        color = clock["running"]
        if self._left(clock, color, now) > 0:
            return False
        clock["remaining"][color] = 0
        clock["running"] = None
        clock["since"] = None
        loser = state["players"][0] if color == "white" else state["players"][1]
        winner = self._opponent(state, loser)
        winner_color = chess.BLACK if color == "white" else chess.WHITE
        if board.has_insufficient_material(winner_color):
            state["result"] = {"winners": [], "draw": True,
                               "reason": "Timeout vs insufficient material"}
        else:
            state["result"] = {"winners": [winner], "draw": False, "reason": "Timeout"}
        log(state, f"{who(loser)} ran out of time")
        return True

    def deadline(self, state: State) -> float | None:
        clock = state.get("clock")
        if state["result"] is not None or not clock or not clock["running"]:
            return None
        return (clock["since"] + clock["remaining"][clock["running"]]) / 1000

    def expire(self, state: State) -> State:
        due = self.deadline(state)
        if due is None or self.now() < due:
            return state
        new_state = copy.deepcopy(state)
        self._flag(new_state, board_for(new_state), self._now_ms())
        return new_state

    # -- game --------------------------------------------------------------------------

    def new_game(self, players: list[str], rng: random.Random) -> State:
        return {
            "players": list(players),       # [white, black]
            "colors": {players[0]: "white", players[1]: "black"},
            "initial_fen": chess.STARTING_FEN,
            "moves": [],
            "san": [],
            "draw_offer": None,
            "result": None,                 # {"winners": [...], "draw": bool, "reason": str}
            "clock": None,                  # see configure(); None = no time control
            "log": [],
        }

    @staticmethod
    def _to_move(state: State, board: chess.Board) -> str:
        return state["players"][0] if board.turn == chess.WHITE else state["players"][1]

    @staticmethod
    def _opponent(state: State, player: str) -> str:
        return next(p for p in state["players"] if p != player)

    def _apply(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        board = board_for(state)
        now = self._now_ms()
        if self._flag(state, board, now):
            return  # time ran out before this action arrived; the game is over
        self._dispatch(state, board, player, action, now)
        if state["result"] is not None:
            self._stop_clock(state, now)

    def _dispatch(self, state: State, board: chess.Board, player: str, action: Action,
                  now: int) -> None:
        kind = action["type"]
        if kind == "move":
            self._move(state, board, player, action, now)
        elif kind == "resign":
            winner = self._opponent(state, player)
            state["result"] = {"winners": [winner], "draw": False, "reason": "Resignation"}
            log(state, f"{who(player)} resigned")
        elif kind == "offer_draw":
            if state["draw_offer"] is not None:
                raise GameError("A draw offer is already pending")
            state["draw_offer"] = player
            log(state, f"{who(player)} offered a draw")
        elif kind in ("accept_draw", "decline_draw"):
            if state["draw_offer"] in (None, player):
                raise GameError("There is no draw offer from your opponent")
            state["draw_offer"] = None
            if kind == "accept_draw":
                state["result"] = {"winners": [], "draw": True, "reason": "Draw by agreement"}
                log(state, f"{who(player)} accepted the draw")
            else:
                log(state, f"{who(player)} declined the draw")
        elif kind == "claim_draw":
            if self._to_move(state, board) != player:
                raise GameError("You can only claim a draw on your turn")
            reason = claimable_draw(board)
            if reason is None:
                raise GameError("The position does not allow a draw claim")
            state["result"] = {"winners": [], "draw": True, "reason": reason}
            log(state, f"{who(player)} claimed a draw ({reason.lower()})")
        else:
            raise GameError("Unknown action")

    def _move(self, state: State, board: chess.Board, player: str, action: Action,
              now: int) -> None:
        if self._to_move(state, board) != player:
            raise GameError("It is not your turn")
        uci = action.get("uci")
        if not isinstance(uci, str) or not 4 <= len(uci) <= 5:
            raise GameError("Send the move in UCI form, e.g. e2e4")
        try:
            move = chess.Move.from_uci(uci.lower())
        except (ValueError, chess.InvalidMoveError) as exc:
            raise GameError("Send the move in UCI form, e.g. e2e4") from exc
        if move not in board.legal_moves:
            promotion = chess.Move(move.from_square, move.to_square, promotion=chess.QUEEN)
            if move.promotion is None and promotion in board.legal_moves:
                raise GameError("Choose a promotion piece (q, r, b or n)")
            raise GameError("Illegal move")
        san = board.san(move)
        mover = _color_name(board.turn)
        board.push(move)
        clock = state.get("clock")
        if clock:
            if clock["running"] == mover:
                clock["remaining"][mover] = (self._left(clock, mover, now)
                                             + clock["increment_ms"])
            clock["running"] = _color_name(board.turn)
            clock["since"] = now
        state["moves"].append(move.uci())
        state["san"].append(san)
        state["draw_offer"] = None
        log(state, f"{who(player)} played {san}")
        outcome = board.outcome(claim_draw=False)
        if outcome is not None:
            reason = TERMINATION_REASONS.get(outcome.termination, outcome.termination.name)
            winners = [] if outcome.winner is None else [
                state["players"][0] if outcome.winner == chess.WHITE else state["players"][1]]
            state["result"] = {"winners": winners, "draw": outcome.winner is None,
                               "reason": reason}
            log(state, f"{reason}" + (f": {who(winners[0])} wins" if winners else ": draw"))

    def _remove_player(self, state: State, player: str) -> None:
        self._stop_clock(state, self._now_ms())
        state["result"] = {"winners": [self._opponent(state, player)], "draw": False,
                           "reason": "Opponent left"}
        log(state, f"{who(player)} left the game")

    def awaiting(self, state: State) -> list[str]:
        if state["result"] is not None:
            return []
        return [self._to_move(state, board_for(state))]

    def outcome(self, state: State) -> Outcome | None:
        result = state["result"]
        if result is None:
            return None
        return Outcome(winners=list(result["winners"]), draw=result["draw"],
                       reason=result["reason"])

    def view(self, state: State, player: str | None) -> dict[str, Any]:
        board = board_for(state)
        to_move = self._to_move(state, board)
        my_turn = player == to_move and state["result"] is None
        return {
            "players": state["players"],
            "colors": state["colors"],
            "fen": board.fen(),
            "san": state["san"],
            "turn": "white" if board.turn == chess.WHITE else "black",
            "to_move": to_move,
            "check": board.is_check(),
            "last_move": state["moves"][-1] if state["moves"] else None,
            "legal_moves": [m.uci() for m in board.legal_moves] if my_turn else [],
            "draw_offer": state["draw_offer"],
            "can_claim_draw": my_turn and claimable_draw(board) is not None,
            "result": state["result"],
            "clock": self._clock_view(state),
            "log": state["log"],
        }

    def _clock_view(self, state: State) -> dict[str, Any] | None:
        clock = state.get("clock")
        if not clock:
            return None
        now = self._now_ms()
        return {
            "control": clock["control"],
            "label": time_control_label(clock["control"]),
            "initial_ms": clock["initial_ms"],
            "increment_ms": clock["increment_ms"],
            # Time left as of this view; the browser counts the running side down from here.
            "remaining": {c: max(0, self._left(clock, c, now)) for c in ("white", "black")},
            "running": clock["running"],
        }
