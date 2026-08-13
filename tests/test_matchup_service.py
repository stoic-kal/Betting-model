import json

from services import matchup_service


def test_missing_slate_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(matchup_service, "SLATE_FILE", tmp_path / "missing.json")
    slate = matchup_service.get_slate("2026-08-13")
    assert slate["date"] == "2026-08-13"
    assert slate["games"] == []
    assert "not been built" in slate["message"]


def test_get_game_reads_precomputed_slate(monkeypatch, tmp_path):
    path = tmp_path / "slate.json"
    path.write_text(json.dumps({"date":"2026-08-13","games":[{"game_pk":123,"home_team":"DET","away_team":"CLE"}]}))
    monkeypatch.setattr(matchup_service, "SLATE_FILE", path)
    game = matchup_service.get_game(123, "2026-08-13")
    assert game["home_team"] == "DET"
    assert matchup_service.get_game(999, "2026-08-13") is None
