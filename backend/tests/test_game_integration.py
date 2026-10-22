"""Each real game end-to-end through rooms, REST and WebSockets (not just the engine)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from typing import Any

import pytest

from app.games.registry import GAMES
from tests.conftest import Browser, receive_until
from tests.games.test_business import api_move as business_move
from tests.games.test_typing_race import api_move as typing_move
from tests.games.test_typing_race import skip_countdown


def start_game(admin: Browser, players: list[Browser], game_type: str) -> int:
    room_id = admin.post("/api/admin/rooms", json={
        "game_type": game_type, "name": game_type, "max_players": len(players)}).json()["id"]
    for p in players:
        assert p.post(f"/api/rooms/{room_id}/join").status_code == 200
        p.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
    response = admin.post(f"/api/admin/rooms/{room_id}/start")
    assert response.status_code == 200, response.text
    return room_id


def uno_move(view: dict[str, Any]) -> dict[str, Any] | None:
    if view["current"] != view["you"]:
        return None
    if view["phase"] == "challenge":
        return {"type": "accept"}
    if view["playable"]:
        return {"type": "play", "card": view["playable"][0], "color": "red"}
    return {"type": "pass"} if view["phase"] == "drawn" else {"type": "draw"}


def snakes_move(view: dict[str, Any]) -> dict[str, Any] | None:
    return {"type": "roll"} if view["current"] == view["you"] else None


def ludo_move(view: dict[str, Any]) -> dict[str, Any] | None:
    if view["current"] != view["you"]:
        return None
    if view["phase"] == "roll":
        return {"type": "roll"}
    return {"type": "move", "token": view["legal_tokens"][0]}


def battleship_move(view: dict[str, Any]) -> dict[str, Any] | None:
    if view["phase"] == "placement":
        return None if view["placed"][view["you"]] else {"type": "place_random"}
    if view["current"] != view["you"]:
        return None
    fired = {(s["row"], s["col"]) for s in view["my_shots"]}
    row, col = next((r, c) for r in range(10) for c in range(10) if (r, c) not in fired)
    return {"type": "fire", "row": row, "col": col}


def chess_move(view: dict[str, Any]) -> dict[str, Any] | None:
    if not view["legal_moves"]:
        return None
    return {"type": "move", "uci": sorted(view["legal_moves"])[0]}


def uno_private(view: dict[str, Any]) -> list[Any]:
    return [c["id"] for c in view["hand"]]


MOVES: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]] = {
    "uno": uno_move, "snakes": snakes_move, "ludo": ludo_move,
    "battleship": battleship_move, "chess": chess_move, "typing": typing_move,
    "business": business_move}
PRIVATE: dict[str, Callable[[dict[str, Any]], list[Any]]] = {"uno": uno_private}


def test_every_registered_game_is_covered() -> None:
    assert set(GAMES) == set(MOVES)


@pytest.mark.parametrize("game_type", sorted(MOVES))
def test_game_plays_through_api(game_type: str, admin: Browser, monkeypatch: pytest.MonkeyPatch,
                                approved_player: Callable[[str], Browser]) -> None:
    a, b = approved_player("Alpha"), approved_player("Beta")
    with ExitStack() as stack:
        sockets = [stack.enter_context(p.ws("/ws/player")) for p in (a, b)]
        for ws in sockets:
            ws.receive_json()
        room_id = start_game(admin, [a, b], game_type)
        if game_type == "typing":
            skip_countdown(monkeypatch, GAMES["typing"])  # race in fast-forward
        views = [receive_until(ws, lambda m: m.get("game") is not None)["game"] for ws in sockets]

        # Hidden information: neither player's private items appear in the other's view.
        private = PRIVATE.get(game_type)
        if private is not None:
            mine, theirs = private(views[0]), private(views[1])
            assert mine != theirs
            assert set(map(str, mine)).isdisjoint(set(map(str, theirs)))

        moves = 0
        completed = False
        for _ in range(60):
            state = [p.get("/api/state").json() for p in (a, b)]
            if state[0]["room"]["status"] == "COMPLETED":
                completed = True
                break
            for player, s in zip((a, b), state, strict=True):
                move = MOVES[game_type](s["game"])
                if move is None:
                    continue
                response = player.post(f"/api/rooms/{room_id}/actions", json={"action": move})
                assert response.status_code == 200, (move, response.text)
                moves += 1
                break
            else:
                pytest.fail("no player could move")
        assert moves >= 10 or completed
        # Pushes kept flowing to both players with increasing versions.
        latest = [receive_until(ws, lambda m: m["game"]["version"] > views[0]["version"])
                  for ws in sockets]
        assert all(m["game"]["you"] != latest[0]["game"]["you"] for m in latest[1:])


def test_battleship_fleet_never_reaches_opponent(admin: Browser,
                                                  approved_player: Callable[[str], Browser]
                                                  ) -> None:
    a, b = approved_player("Alpha"), approved_player("Beta")
    with ExitStack() as stack:
        sockets = [stack.enter_context(p.ws("/ws/player")) for p in (a, b)]
        for ws in sockets:
            ws.receive_json()
        room_id = start_game(admin, [a, b], "battleship")
        a.post(f"/api/rooms/{room_id}/actions", json={"action": {"type": "place_random"}})
        a_fleet = a.get("/api/state").json()["game"]["my_fleet"]
        cells = {tuple(c) for ship in a_fleet for c in ship["cells"]}
        b.post(f"/api/rooms/{room_id}/actions", json={"action": {"type": "place_random"}})
        # Everything B receives over REST and WebSocket.
        b_rest = b.get("/api/state").json()
        b_push = receive_until(sockets[1], lambda m: (m.get("game") or {}).get("phase") == "battle")
        for payload in (b_rest, b_push):
            game = payload["game"]
            assert "fleets" not in game and game["my_fleet"] != a_fleet
            own = {tuple(c) for ship in game["my_fleet"] for c in ship["cells"]}
            text = str({k: v for k, v in game.items() if k != "my_fleet"})
            for r, c in cells - own:
                assert f"[{r}, {c}]" not in text
        assert str(a_fleet) not in admin.get("/api/admin/state").text
