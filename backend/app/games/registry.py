"""All playable games, keyed by game type, in catalog order."""

from __future__ import annotations

from app.games.base import GameEngine, GameInfo
from app.games.battleship import BattleshipEngine
from app.games.chess_game import ChessEngine
from app.games.ludo import LudoEngine
from app.games.snakes import SnakesEngine
from app.games.uno import UnoEngine

GAMES: dict[str, GameEngine] = {}


def register(engine: GameEngine) -> GameEngine:
    GAMES[engine.info.game_type] = engine
    return engine


def get_engine(game_type: str) -> GameEngine | None:
    return GAMES.get(game_type)


def catalog() -> list[GameInfo]:
    return [engine.info for engine in GAMES.values()]


register(UnoEngine())
register(SnakesEngine())
register(LudoEngine())
register(BattleshipEngine())
register(ChessEngine())
