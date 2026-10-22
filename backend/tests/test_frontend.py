from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def _client(dist: Path) -> TestClient:
    return TestClient(create_app(make_settings(frontend_dist_dir=dist)))


def test_serves_index_at_root(dist_dir: Path) -> None:
    response = _client(dist_dir).get("/")
    assert response.status_code == 200
    assert "<title>LanGamesHub</title>" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_client_side_routes_fall_back_to_index(dist_dir: Path) -> None:
    response = _client(dist_dir).get("/lobby/room/42")
    assert response.status_code == 200
    assert "<title>LanGamesHub</title>" in response.text


def test_hashed_assets_are_cached(dist_dir: Path) -> None:
    response = _client(dist_dir).get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


def test_missing_asset_is_404_not_index(dist_dir: Path) -> None:
    assert _client(dist_dir).get("/assets/missing.js").status_code == 404


def test_top_level_static_file(dist_dir: Path) -> None:
    response = _client(dist_dir).get("/favicon.svg")
    assert response.status_code == 200
    assert response.text == "<svg/>"


def test_unknown_api_path_is_json_404(dist_dir: Path) -> None:
    client = _client(dist_dir)
    for path in ("/api/does-not-exist", "/api", "/ws/anything"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"] == "application/json"


def test_path_traversal_does_not_escape_dist(dist_dir: Path) -> None:
    client = _client(dist_dir)
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        response = client.get(path)
        assert "outside dist" not in response.text, path


def test_placeholder_when_frontend_not_built(tmp_path: Path) -> None:
    client = _client(tmp_path / "missing")
    response = client.get("/")
    assert response.status_code == 503
    assert "has not been built" in response.text
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/nope").status_code == 404
