"""Final placings (#1, #2, #3…) computed by each engine when a game ends."""

from __future__ import annotations

import random

from app.games.base import Placing, rank
from app.games.registry import GAMES


def places(placings: list[Placing]) -> list[tuple[str, int, str]]:
    return [(p.player, p.place, p.detail) for p in placings]


def test_rank_uses_competition_ranking() -> None:
    ranked = rank([("a", (1,), ""), ("b", (3,), ""), ("c", (3,), ""), ("d", (0,), "")])
    assert [(p.player, p.place) for p in ranked] == [("b", 1), ("c", 1), ("a", 3), ("d", 4)]


def test_uno_ranks_by_cards_left() -> None:
    engine = GAMES["uno"]
    state = engine.new_game(["a", "b", "c"], random.Random(1))
    state["hands"] = {"a": [], "b": [1, 2, 3], "c": [4]}
    state["winner"] = "a"
    assert places(engine.standings(state)) == [
        ("a", 1, "Winner"), ("c", 2, "1 card left"), ("b", 3, "3 cards left")]


def test_snakes_ranks_by_square() -> None:
    engine = GAMES["snakes"]
    state = engine.new_game(["a", "b", "c", "d"], random.Random(1))
    state["positions"] = {"a": 40, "b": 100, "c": 77, "d": 40}
    state["winner"] = "b"
    assert places(engine.standings(state)) == [
        ("b", 1, "Winner"), ("c", 2, "Square 77"), ("a", 3, "Square 40"), ("d", 3, "Square 40")]


def test_ludo_ranks_by_tokens_home_then_distance() -> None:
    engine = GAMES["ludo"]
    state = engine.new_game(["a", "b", "c"], random.Random(1))
    state["tokens"] = {"a": [56, 56, 56, 56], "b": [56, 10, -1, -1], "c": [50, 50, 50, 50]}
    state["winner"] = "a"
    assert places(engine.standings(state)) == [
        ("a", 1, "Winner"), ("b", 2, "1/4 home"), ("c", 3, "0/4 home")]


def test_two_player_games_put_the_winner_first() -> None:
    chess = GAMES["chess"]
    state = chess.apply(chess.new_game(["w", "b"], random.Random(1)), "b", {"type": "resign"},
                        random.Random(1))
    assert places(chess.standings(state)) == [("w", 1, "Winner"), ("b", 2, "")]
    drawn = chess.apply(chess.apply(chess.new_game(["w", "b"], random.Random(1)), "w",
                                    {"type": "offer_draw"}, random.Random(1)),
                        "b", {"type": "accept_draw"}, random.Random(1))
    assert [p.place for p in chess.standings(drawn)] == [1, 1]


def test_every_engine_ranks_every_remaining_player() -> None:
    for engine in GAMES.values():
        players = [f"p{i}" for i in range(engine.info.max_players)]
        state = engine.new_game(players, random.Random(2))
        assert sorted(p.player for p in engine.standings(state)) == sorted(players)
