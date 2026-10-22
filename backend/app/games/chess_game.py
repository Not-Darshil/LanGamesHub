"""Chess engine on top of python-chess. Rules: docs/games/chess.md."""

from __future__ import annotations

import random
from typing import Any

import chess

from app.games.base import Action, GameEngine, GameError, GameInfo, Outcome, State, log, who

TERMINATION_REASONS = {
    chess.Termination.CHECKMATE: "Checkmate",
    chess.Termination.STALEMATE: "Stalemate",
    chess.Termination.INSUFFICIENT_MATERIAL: "Insufficient material",
    chess.Termination.SEVENTYFIVE_MOVES: "Seventy-five-move rule",
    chess.Termination.FIVEFOLD_REPETITION: "Fivefold repetition",
}


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


class ChessEngine(GameEngine):
    info = GameInfo("chess", "Chess", 2, 2, "Classic chess with full FIDE move rules.")

    def new_game(self, players: list[str], rng: random.Random) -> State:
        return {
            "players": list(players),       # [white, black]
            "colors": {players[0]: "white", players[1]: "black"},
            "initial_fen": chess.STARTING_FEN,
            "moves": [],
            "san": [],
            "draw_offer": None,
            "result": None,                 # {"winners": [...], "draw": bool, "reason": str}
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
        kind = action["type"]
        if kind == "move":
            self._move(state, board, player, action)
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

    def _move(self, state: State, board: chess.Board, player: str, action: Action) -> None:
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
        board.push(move)
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
            "log": state["log"],
        }
