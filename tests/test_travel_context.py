from datetime import date
from unittest.mock import Mock, patch

from services import advanced_context_service as service
from services.totals_model_v3 import _fip_from_mlb_stat, _parse_wind
from services.baseball_metrics import baseball_innings


def _response(payload):
    response = Mock()
    response.json.return_value = payload
    return response


def test_venue_info_requests_required_hydration():
    service._CACHE.clear()
    payload = {
        "venues": [{
            "location": {"defaultCoordinates": {"latitude": 40.8, "longitude": -73.9}},
            "timeZone": {"id": "America/New_York"},
        }]
    }
    with patch.object(service.requests, "get", return_value=_response(payload)) as get:
        venue = service._venue_info(3313)

    assert venue == {"lat": 40.8, "lon": -73.9, "timezone": "America/New_York"}
    assert get.call_args.kwargs["params"] == {"hydrate": "location,timezone"}


def test_team_travel_uses_game_date_and_produces_timezone_delta():
    service._CACHE.clear()
    schedule = {
        "dates": [{"games": [{
            "status": {"codedGameState": "F"},
            "venue": {"id": 1},
        }]}]
    }
    venues = {
        1: {"lat": 33.8, "lon": -117.9, "timezone": "America/Los_Angeles"},
        3313: {"lat": 40.8, "lon": -73.9, "timezone": "America/New_York"},
    }
    with patch.object(service.requests, "get", return_value=_response(schedule)) as get, patch.object(
        service, "_venue_info", side_effect=lambda venue_id: venues[venue_id]
    ):
        result = service.team_travel_context("LAA", 3313, game_date="2026-08-11")

    assert result["available"] is True
    assert result["timezone_delta"] == 3.0
    assert result["miles"] > 2000
    assert get.call_args.kwargs["params"]["endDate"] == "2026-08-10"


def test_fip_uses_mlb_home_runs_and_hit_batsmen_fields():
    stat = {
        "inningsPitched": "100.0",
        "homeRuns": 10,
        "baseOnBalls": 30,
        "hitBatsmen": 5,
        "strikeOuts": 100,
    }
    assert _fip_from_mlb_stat(stat) == 3.45


def test_fip_rejects_tiny_samples_for_league_average_fallback():
    assert _fip_from_mlb_stat({"inningsPitched": "19.2", "homeRuns": 2}) is None


def test_mlb_park_relative_wind_is_parsed_without_compass_guessing():
    assert _parse_wind("12 mph, Out To RF") == (12.0, "Out To RF", "out")
    assert _parse_wind("9 mph, In From LF") == (9.0, "In From LF", "in")
    assert _parse_wind("", 14, "SW") == (14.0, "SW", "unknown")


def test_baseball_innings_converts_outs_not_decimal_tenths():
    assert baseball_innings("85.2") == 85 + 2 / 3
