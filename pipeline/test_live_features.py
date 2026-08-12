import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.live_features_v2 import compute_v2_features
from pipeline.features_common import ML_FEATURES
from services.shadow_inference_service import TEAM_IDS, VENUE_IDS


DEGRADED_SOURCE_TO_SUFFIXES = {
    "pitcher_rate_stats": ["k_rate", "bb_rate", "hr_rate", "hard_hit_pct", "fb_velo", "xwoba_against", "fip"],
    "fb_velo": ["fb_velo"],
    "xwoba_against": ["xwoba_against"],
    "days_rest": ["days_rest"],
    "is_lefty": ["is_lefty"],
    "team_batting": ["bat_k_rate", "bat_hard_hit_pct", "bat_iso", "bat_woba"],
    "bat_woba": ["bat_woba"],
    "l10_form": ["L10_wr", "L10_rs", "L10_ra"],
    "park_factor": ["park_factor"],
    "weather": ["temp_f", "wind_mph", "wind_out_factor"],
}


def _possibly_degraded_keys(degraded):
    keys = set()
    for source in degraded:
        for suffix in DEGRADED_SOURCE_TO_SUFFIXES.get(source, []):
            keys.add(suffix)
    return keys


def run(home_team, away_team, home_team_id, away_team_id, home_sp_id, away_sp_id, venue_id, days_ahead):
    game_dt = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    print(f"Testing live feature fetch for {away_team} @ {home_team} on {game_dt.date()}")
    print(f"  home_sp_id={home_sp_id} away_sp_id={away_sp_id} venue_id={venue_id}")
    result = compute_v2_features(
        home_team=home_team, away_team=away_team,
        home_team_id=home_team_id, away_team_id=away_team_id,
        home_sp_id=home_sp_id, away_sp_id=away_sp_id,
        venue_id=venue_id, game_datetime=game_dt,
    )
    features = result["features"]
    degraded = result["degraded"]

    print(f"\n{len(features)} features returned, {len(ML_FEATURES)} expected")
    missing = set(ML_FEATURES) - set(features.keys())
    extra = set(features.keys()) - set(ML_FEATURES)
    if missing:
        print(f"  MISSING: {missing}")
    if extra:
        print(f"  EXTRA: {extra}")

    print(f"\nDegraded (fell back to league average): {len(degraded)} of {len(ML_FEATURES)}")
    for d in degraded:
        print(f"  FALLBACK: {d}")

    possibly_degraded = _possibly_degraded_keys(degraded)

    print("\nFeature values:")
    for k in ML_FEATURES:
        suffix = k[5:] if k.startswith("home_") or k.startswith("away_") else k
        flag = "  <- FALLBACK" if suffix in possibly_degraded else ""
        print(f"  {k:<25} {features.get(k)}{flag}")

    flagged_count = sum(1 for k in ML_FEATURES if (k[5:] if k.startswith("home_") or k.startswith("away_") else k) in possibly_degraded)
    live_count = len(ML_FEATURES) - flagged_count
    print(f"\nSummary: {live_count}/{len(ML_FEATURES)} feature values likely live, {flagged_count} likely fell back to league-average")
    if not degraded:
        print("PASS: full live fetch succeeded with zero fallbacks")
    elif live_count > 0:
        print("PARTIAL: some live data reached, some fell back — check network/API access above")
    else:
        print("FAIL: everything fell back — no live data was reachable")


def find_real_matchup():
    from services.schedule_service import get_today_games

    for offset in range(0, 3):
        date_str = (datetime.now(timezone.utc) + timedelta(days=offset)).strftime("%Y-%m-%d")
        games = get_today_games(date_str=date_str, include_odds=False)
        for g in games:
            if g.get("home_sp_id") and g.get("away_sp_id"):
                return g, offset
    return None, None


if __name__ == "__main__":
    game, offset = None, None
    try:
        game, offset = find_real_matchup()
    except Exception as exc:
        print(f"Could not auto-discover a real matchup ({exc}), using example IDs instead.\n")

    if game:
        run(
            home_team=game["home_abbr"], away_team=game["away_abbr"],
            home_team_id=TEAM_IDS.get(game["home_abbr"]), away_team_id=TEAM_IDS.get(game["away_abbr"]),
            home_sp_id=game["home_sp_id"], away_sp_id=game["away_sp_id"],
            venue_id=VENUE_IDS.get(game["home_abbr"]), days_ahead=offset,
        )
    else:
        print("No upcoming game with confirmed probable pitchers found in the next 3 days, using example IDs.\n")
        run(
            home_team="BOS", away_team="NYY", home_team_id=111, away_team_id=147,
            home_sp_id=605483, away_sp_id=592789, venue_id=3, days_ahead=1,
        )
