"""Chess clocks: time controls, server-side timing, increments and flag fall."""

from __future__ import annotations

import random

import pytest

from app.games.base import GameError
from app.games.chess_game import TIME_CONTROLS, ChessEngine


class FakeTime:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def t() -> FakeTime:
    return FakeTime()


@pytest.fixture
def e(t: FakeTime) -> ChessEngine:
    return ChessEngine(clock=t)


def timed(e: ChessEngine, control: str = "3+2", fen: str | None = None) -> dict:
    state = e.start(["w", "b"], random.Random(1), {"time_control": control})
    if fen:
        state["initial_fen"] = fen
    return state


def move(e: ChessEngine, state: dict, player: str, uci: str) -> dict:
    return e.apply(state, player, {"type": "move", "uci": uci}, random.Random(1))


def test_options_validation(e: ChessEngine) -> None:
    for control in TIME_CONTROLS:
        assert e.validate_options({"time_control": control}) == {"time_control": control}
    assert e.validate_options(None) == {}
    assert e.validate_options({"time_control": None}) == {}
    assert e.validate_options({"time_control": "none"}) == {}
    with pytest.raises(GameError, match="time control"):
        e.validate_options({"time_control": "2+1"})
    with pytest.raises(GameError, match="time control"):
        e.validate_options({"time_control": 10})
    with pytest.raises(GameError, match="Unknown chess option"):
        e.validate_options({"variant": "960"})
    assert e.options_label({"time_control": "10+0"}) == "10 min · Rapid"
    assert e.options_label({"time_control": "3+2"}) == "3 min + 2s · Blitz"
    assert e.options_label({}) == "No clock"


def test_other_games_reject_options() -> None:
    from app.games.registry import GAMES

    with pytest.raises(GameError, match="has no options"):
        GAMES["uno"].validate_options({"time_control": "1+0"})
    assert GAMES["uno"].validate_options({}) == {}


def test_untimed_game_has_no_clock(e: ChessEngine) -> None:
    state = e.start(["w", "b"], random.Random(1))
    assert e.view(state, "w")["clock"] is None
    assert e.deadline(move(e, state, "w", "e2e4")) is None


def test_clock_starts_after_whites_first_move(e: ChessEngine, t: FakeTime) -> None:
    state = timed(e)
    view = e.view(state, "w")["clock"]
    assert view["running"] is None and view["remaining"] == {"white": 180_000, "black": 180_000}
    assert e.deadline(state) is None
    t.now += 30  # White thinks for 30 s: the first move is not timed
    state = move(e, state, "w", "e2e4")
    clock = e.view(state, "b")["clock"]
    assert clock["running"] == "black"
    assert clock["remaining"] == {"white": 180_000, "black": 180_000}
    assert e.deadline(state) == pytest.approx(t.now + 180)


def test_time_is_deducted_and_increment_added(e: ChessEngine, t: FakeTime) -> None:
    state = move(e, timed(e), "w", "e2e4")
    t.now += 10
    assert e.view(state, "w")["clock"]["remaining"]["black"] == 170_000  # counting down
    state = move(e, state, "b", "e7e5")
    clock = e.view(state, "w")["clock"]
    assert clock["remaining"] == {"white": 180_000, "black": 172_000}  # -10 s, +2 s
    assert clock["running"] == "white"
    t.now += 5.5
    state = move(e, state, "w", "g1f3")
    assert e.view(state, "b")["clock"]["remaining"]["white"] == 176_500


def test_flag_fall_on_late_move(e: ChessEngine, t: FakeTime) -> None:
    state = move(e, timed(e, "1+0"), "w", "e2e4")
    t.now += 61
    late = move(e, state, "b", "e7e5")  # accepted request, but the game ends on time
    assert late["moves"] == ["e2e4"]
    outcome = e.outcome(late)
    assert outcome is not None and outcome.winners == ["w"] and outcome.reason == "Timeout"
    assert late["clock"]["remaining"]["black"] == 0 and late["clock"]["running"] is None
    assert any("ran out of time" in line for line in late["log"])


def test_expire_without_any_action(e: ChessEngine, t: FakeTime) -> None:
    state = move(e, timed(e, "1+0"), "w", "e2e4")
    t.now += 59.9
    assert e.expire(state) is state  # still has time
    t.now += 0.2
    expired = e.expire(state)
    assert expired is not state and e.outcome(state) is None  # original untouched
    assert e.outcome(expired).reason == "Timeout" and e.outcome(expired).winners == ["w"]
    assert e.deadline(expired) is None
    assert e.expire(expired) is expired


def test_timeout_against_lone_king_is_a_draw(e: ChessEngine, t: FakeTime) -> None:
    # White has only a king left, so Black flagging cannot lose to it.
    state = timed(e, "1+0", fen="4k3/8/8/8/8/8/4p3/4K3 w - - 0 1")
    state = move(e, state, "w", "e1d2")
    t.now += 61
    outcome = e.outcome(e.expire(state))
    assert outcome.draw and outcome.reason == "Timeout vs insufficient material"


def test_clock_stops_when_game_ends(e: ChessEngine, t: FakeTime) -> None:
    state = move(e, timed(e), "w", "e2e4")
    t.now += 20
    resigned = e.apply(state, "b", {"type": "resign"}, random.Random(1))
    assert resigned["clock"]["running"] is None
    assert resigned["clock"]["remaining"]["black"] == 160_000
    assert e.deadline(resigned) is None
    left = e.remove_player(state, "w")
    assert left["clock"]["running"] is None


def test_checkmate_stops_clock(e: ChessEngine, t: FakeTime) -> None:
    state = timed(e)
    for player, uci in [("w", "e2e4"), ("b", "e7e5"), ("w", "f1c4"), ("b", "b8c6"),
                        ("w", "d1h5"), ("b", "g8f6"), ("w", "h5f7")]:
        t.now += 1
        state = move(e, state, player, uci)
    assert e.outcome(state).reason == "Checkmate"
    assert state["clock"]["running"] is None and e.deadline(state) is None


def test_saved_games_without_clock_still_work(e: ChessEngine) -> None:
    state = e.new_game(["w", "b"], random.Random(1))
    del state["clock"]  # a game saved before clocks existed
    state = move(e, state, "w", "e2e4")
    assert e.view(state, "b")["clock"] is None and e.deadline(state) is None
