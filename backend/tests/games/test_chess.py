"""Chess rules (docs/games/chess.md) through the engine's action interface."""

from __future__ import annotations

import random

import chess
import pytest

from app.games.chess_game import ChessEngine
from tests.games.helpers import rejects

E = ChessEngine()


def new(fen: str | None = None) -> dict:
    state = E.new_game(["w", "b"], random.Random(1))
    if fen:
        state["initial_fen"] = fen
    return state


def play(state: dict, *sans: str) -> dict:
    """Play SAN moves, alternating players as the engine expects, via UCI actions."""
    for san in sans:
        board = chess.Board(state["initial_fen"])
        for uci in state["moves"]:
            board.push_uci(uci)
        mover = "w" if board.turn == chess.WHITE else "b"
        uci = board.parse_san(san).uci()
        state = E.apply(state, mover, {"type": "move", "uci": uci}, random.Random(1))
    return state


def test_initial_position() -> None:
    view = E.view(new(), "w")
    assert view["fen"] == chess.STARTING_FEN
    assert view["colors"] == {"w": "white", "b": "black"}
    assert len(view["legal_moves"]) == 20
    assert E.view(new(), "b")["legal_moves"] == []  # not black's turn
    assert E.awaiting(new()) == ["w"]


def test_move_validation() -> None:
    state = new()
    rejects(E, state, "b", "not your turn", type="move", uci="e7e5")
    rejects(E, state, "w", "Illegal move", type="move", uci="e2e5")
    rejects(E, state, "w", "Illegal move", type="move", uci="e1e2")
    rejects(E, state, "w", "UCI form", type="move", uci="pawn to e4")
    rejects(E, state, "w", "UCI form", type="move", uci=1234)
    rejects(E, state, "w", "UCI form", type="move", uci="z9z9")
    s = play(state, "e4")
    assert s["san"] == ["e4"] and E.awaiting(s) == ["b"]


def test_cannot_leave_king_in_check() -> None:
    s = play(new(), "e4", "f5", "Qh5+")
    assert E.view(s, "b")["check"] is True
    rejects(E, s, "b", "Illegal move", type="move", uci="a7a6")
    s = play(s, "g6")
    assert E.view(s, "w")["check"] is False


def test_checkmate() -> None:
    s = play(new(), "e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6", "Qxf7#")
    outcome = E.outcome(s)
    assert outcome is not None and outcome.winners == ["w"] and outcome.reason == "Checkmate"
    rejects(E, s, "b", "game is over", type="move", uci="e8f7")


def test_stalemate() -> None:
    # Sam Loyd's ten-move stalemate.
    s = play(new(), "e3", "a5", "Qh5", "Ra6", "Qxa5", "h5", "h4", "Rah6", "Qxc7", "f6",
             "Qxd7+", "Kf7", "Qxb7", "Qd3", "Qxb8", "Qh7", "Qxc8", "Kg6", "Qe6")
    outcome = E.outcome(s)
    assert outcome is not None and outcome.draw and outcome.reason == "Stalemate"


def test_castling_both_sides() -> None:
    s = play(new(), "e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "O-O")
    assert "e1g1" in s["moves"] and s["san"][-1] == "O-O"
    s = play(new(), "d4", "d5", "Nc3", "Nc6", "Bf4", "Bf5", "Qd2", "Qd7", "O-O-O")
    assert s["moves"][-1] == "e1c1"


def test_castling_refused_through_check_or_after_king_moved() -> None:
    # The black bishop on c4 attacks f1, a square the king would pass through.
    s = new("r3k2r/8/8/8/2b5/8/8/R3K2R w KQkq - 0 1")
    rejects(E, s, "w", "Illegal move", type="move", uci="e1g1")  # f1 attacked
    s = play(new("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"), "Ke2", "Ke7", "Ke1", "Ke8")
    rejects(E, s, "w", "Illegal move", type="move", uci="e1g1")


def test_en_passant() -> None:
    s = play(new(), "e4", "a6", "e5", "d5")
    assert "e5d6" in E.view(s, "w")["legal_moves"]
    s = play(s, "exd6")
    board = chess.Board(s["initial_fen"])
    for uci in s["moves"]:
        board.push_uci(uci)
    assert board.piece_at(chess.D5) is None and s["san"][-1] == "exd6"


def test_en_passant_only_immediately() -> None:
    s = play(new(), "e4", "a6", "e5", "d5", "Nf3", "a5")
    rejects(E, s, "w", "Illegal move", type="move", uci="e5d6")


def test_promotion_requires_piece_and_underpromotion_works() -> None:
    s = play(new(), "h4", "g5", "hxg5", "h6", "gxh6", "Nf6", "h7", "Ng8")
    rejects(E, s, "w", "promotion piece", type="move", uci="h7g8")
    queen = E.apply(s, "w", {"type": "move", "uci": "h7g8q"}, random.Random(1))
    assert queen["san"][-1].startswith("hxg8=Q")
    knight = E.apply(s, "w", {"type": "move", "uci": "h7g8n"}, random.Random(1))
    assert knight["san"][-1].startswith("hxg8=N")


def test_insufficient_material_is_automatic_draw() -> None:
    s = play(new("8/8/8/4k3/8/8/3nK3/8 w - - 0 1"), "Kxd2")
    outcome = E.outcome(s)
    assert outcome is not None and outcome.draw and outcome.reason == "Insufficient material"


def test_threefold_repetition_claim() -> None:
    s = new()
    rejects(E, s, "w", "does not allow", type="claim_draw")
    s = play(s, "Nf3", "Nf6", "Ng1", "Ng8", "Nf3", "Nf6", "Ng1", "Ng8")
    assert E.view(s, "w")["can_claim_draw"] is True
    rejects(E, s, "b", "on your turn", type="claim_draw")
    s = E.apply(s, "w", {"type": "claim_draw"}, random.Random(1))
    assert E.outcome(s).reason == "Threefold repetition"


def test_claim_requires_repetition_to_have_happened() -> None:
    # After 7 plies Black could repeat the position a third time, but has not yet.
    s = play(new(), "Nf3", "Nf6", "Ng1", "Ng8", "Nf3", "Nf6", "Ng1")
    assert E.view(s, "b")["can_claim_draw"] is False
    rejects(E, s, "b", "does not allow", type="claim_draw")


def test_fifty_move_claim() -> None:
    s = play(new("8/8/8/4k3/8/8/4K3/R7 w - - 99 80"), "Ra2")
    s = E.apply(s, "b", {"type": "claim_draw"}, random.Random(1))
    assert E.outcome(s).reason == "Fifty-move rule"


def test_draw_offer_accept_decline_and_withdrawal() -> None:
    s = E.apply(new(), "w", {"type": "offer_draw"}, random.Random(1))
    rejects(E, s, "w", "no draw offer from your opponent", type="accept_draw")
    rejects(E, s, "b", "already pending", type="offer_draw")
    declined = E.apply(s, "b", {"type": "decline_draw"}, random.Random(1))
    assert declined["draw_offer"] is None and E.outcome(declined) is None
    moved = play(s, "e4")
    assert moved["draw_offer"] is None
    accepted = E.apply(s, "b", {"type": "accept_draw"}, random.Random(1))
    assert E.outcome(accepted).draw and E.outcome(accepted).reason == "Draw by agreement"


def test_resign_and_leave() -> None:
    s = E.apply(new(), "b", {"type": "resign"}, random.Random(1))
    assert E.outcome(s).winners == ["w"] and E.outcome(s).reason == "Resignation"
    s = E.remove_player(new(), "w")
    assert E.outcome(s).winners == ["b"]


def test_state_is_json_round_trippable() -> None:
    import json

    s = play(new(), "e4", "c5", "Nf3")
    restored = json.loads(json.dumps(s))
    assert E.view(restored, "b")["fen"] == E.view(s, "b")["fen"]


@pytest.mark.parametrize("seed", range(15))
def test_random_games_stay_legal(seed: int) -> None:
    rng = random.Random(seed)
    state = new()
    for _ in range(300):
        if E.outcome(state):
            break
        mover = E.awaiting(state)[0]
        moves = E.view(state, mover)["legal_moves"]
        state = E.apply(state, mover, {"type": "move", "uci": rng.choice(moves)}, rng)
    assert len(state["san"]) == len(state["moves"])
