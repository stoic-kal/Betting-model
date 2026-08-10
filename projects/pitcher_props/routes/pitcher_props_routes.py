import json
import logging
from datetime import date, datetime, timezone
from typing import Optional
from flask import Blueprint, jsonify, render_template, request, Response

from services.pitcher_outs_service import analyze_pitcher_outs
from services.pitcher_strikeouts_service import analyze_pitcher_strikeouts
from services.pitcher_hits_service import analyze_pitcher_hits
from services.pitcher_walks_service import analyze_pitcher_walks
from services.pitcher_prop_grader_service import grade_all_pending, grade_game
from services.pitcher_prop_analytics_service import get_pitcher_prop_analytics, export_csv
from services.pitcher_prop_db import migrate

logger = logging.getLogger(__name__)

pitcher_props_bp = Blueprint("pitcher_props", __name__)


migrate()


@pitcher_props_bp.route("/pitcher-props")
def pitcher_props_page():
    return render_template("pitcher_props.html")


@pitcher_props_bp.route("/api/pitcher-props")
def api_pitcher_props():

    try:
        player_id = int(request.args.get("player_id", 0))
        player_name = request.args.get("player_name", "")
        team = request.args.get("team", "")
        opp = request.args.get("opp", "")
        game_pk = request.args.get("game_pk")
        event_id = request.args.get("event_id")
        game_id = request.args.get("game_id")
        lineup_confirmed = request.args.get("lineup_confirmed", "false").lower() == "true"
        opp_ops = float(request.args.get("opp_lineup_ops", 0.720))
        rest_days = int(request.args.get("rest_days", 4))
        bullpen_ok = request.args.get("bullpen_available", "true").lower() == "true"
        injury_return = request.args.get("is_injury_return", "false").lower() == "true"
        inj_verified = request.args.get("injury_return_verified", "false").lower() == "true"
        stage = request.args.get("stage", "preview")
        create_lock = request.args.get("create_lock", "false").lower() == "true"

        if not player_id or not player_name:
            return (
                jsonify({"status": "error", "message": "player_id and player_name required"}),
                400,
            )

        parlay_lines_for_outs: Optional[list[float]] = None
        parlay_market_override: dict = {}
        try:
            from services.parlayapi_service import get_all_pitcher_props_cached

            all_props = get_all_pitcher_props_cached()
            name_lower = player_name.lower()
            for pname, props in all_props.items():
                if name_lower in pname.lower() or pname.lower() in name_lower:
                    outs_odds = props.get("outs_recorded", {})
                    if outs_odds:
                        parlay_lines_for_outs = sorted(float(k) for k in outs_odds)
                        parlay_market_override = {
                            float(ln): {
"over_odds_dec": q.get("over_dec"),
"under_odds_dec": q.get("under_dec"),
"market_prob_over": q.get("market_prob_over"),
"market_prob_under": q.get("market_prob_under"),
"bookmaker": q.get("best_over_book", "parlayapi"),
                            }
                            for ln, q in outs_odds.items()
                        }
                    break
        except Exception:
            pass

        outs = analyze_pitcher_outs(
            player_id=player_id,
            pitcher_name=player_name,
            team_abbr=team,
            opp_abbr=opp,
            opp_lineup_ops=opp_ops,
            lineup_confirmed=lineup_confirmed,
            bullpen_available=bullpen_ok,
            rest_days=rest_days,
            is_injury_return=injury_return,
            injury_return_verified=inj_verified,
            game_pk=int(game_pk) if game_pk else None,
            game_id=game_id,
            event_id=event_id,
            scheduled_start=None,
            lines_to_evaluate=parlay_lines_for_outs or None,
            stage=stage,
            create_lock=create_lock,
        )

        if parlay_market_override and not outs.get("market"):
            outs["market"] = parlay_market_override

            bp = outs.get("best_pick")
            if bp:
                mkt = parlay_market_override.get(bp["line"], {})
                if mkt:
                    direction = bp["direction"].lower()
                    bp["market_prob"] = mkt.get(f"market_prob_{direction}")
                    bp["odds_dec"] = mkt.get(f"{direction}_odds_dec")
                    bp["sportsbook"] = mkt.get("bookmaker", "parlayapi")
                    if bp["market_prob"] and bp["model_prob"]:
                        bp["edge_pp"] = round((bp["model_prob"] - bp["market_prob"]) * 100, 2)
                    if bp["odds_dec"] and bp["model_prob"]:
                        mp = bp["model_prob"]
                        bp["ev_pct"] = round((mp * (bp["odds_dec"] - 1) - (1 - mp)) * 100, 2)

        k_res = analyze_pitcher_strikeouts(player_id, player_name, opp)
        h_res = analyze_pitcher_hits(player_id, player_name, team, opp)
        bb_res = analyze_pitcher_walks(player_id, player_name, opp)

        return jsonify(
            {
"status": "success",
"player_id": player_id,
"player_name": player_name,
"primary": {
"outs_recorded": _serialize(outs),
                },
"research": {
"strikeouts": _serialize(k_res),
"hits_allowed": _serialize(h_res),
"walks_allowed": _serialize(bb_res),
                },
            }
        )

    except Exception as e:
        logger.exception("Pitcher props API error")
        return jsonify({"status": "error", "message": str(e)}), 500


@pitcher_props_bp.route("/api/pitcher-props/analytics")
def api_pitcher_props_analytics():

    try:
        result = get_pitcher_prop_analytics(
            prop_type=request.args.get("prop_type"),
            classification=request.args.get("classification"),
            since_date=request.args.get("since_date"),
            model_version=request.args.get("model_version"),
        )
        return jsonify({"status": "success", **result})
    except Exception as e:
        logger.exception("Pitcher props analytics error")
        return jsonify({"status": "error", "message": str(e)}), 500


@pitcher_props_bp.route("/api/pitcher-props/analytics/csv")
def api_pitcher_props_csv():

    prop_type = request.args.get("prop_type")
    csv_str = export_csv(prop_type=prop_type)
    fname = f"pitcher_props_{prop_type or 'all'}_{date.today().isoformat()}.csv"
    return Response(
        csv_str,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@pitcher_props_bp.route("/api/pitcher-props/schedule")
def api_pitcher_props_schedule():

    import requests as req

    target_date = request.args.get("date", date.today().isoformat())
    try:
        url = "https://statsapi.mlb.com/api/v1/schedule"
        params = {
"sportId": 1,
"date": target_date,
"hydrate": "probablePitcher,team,venue",
        }
        r = req.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        games = []
        for date_block in data.get("dates", []):
            for g in date_block.get("games", []):
                home = g.get("teams", {}).get("home", {})
                away = g.get("teams", {}).get("away", {})
                hp = home.get("probablePitcher")
                ap = away.get("probablePitcher")
                games.append(
                    {
"gamePk": g.get("gamePk"),
"gameDate": g.get("gameDate"),
"status": g.get("status", {}).get("abstractGameState"),
"homeTeam": home.get("team", {}).get("abbreviation", ""),
"awayTeam": away.get("team", {}).get("abbreviation", ""),
"homeTeamName": home.get("team", {}).get("name", ""),
"awayTeamName": away.get("team", {}).get("name", ""),
"venue": g.get("venue", {}).get("name", ""),
"homePitcher": {"id": hp["id"], "name": hp["fullName"]} if hp else None,
"awayPitcher": {"id": ap["id"], "name": ap["fullName"]} if ap else None,
                    }
                )
        return jsonify({"status": "success", "date": target_date, "games": games})
    except Exception as e:
        logger.exception("Schedule proxy error")
        return jsonify({"status": "error", "message": str(e)}), 500


@pitcher_props_bp.route("/api/player-props/odds")
def api_player_props_odds():

    pitcher_name = request.args.get("pitcher_name", "").strip()
    target_date = request.args.get("date") or date.today().isoformat()
    sources_str = request.args.get("sources", "")
    sources = [s.strip() for s in sources_str.split(",") if s.strip()] or None
    force_refresh = request.args.get("refresh", "").lower() == "true"

    try:
        from services.player_props_odds_service import (
            get_pitcher_prop_odds,
            get_all_pitcher_props_today,
        )
        from services.pitcher_prop_db import market_cache_age

        if pitcher_name:
            odds = get_pitcher_prop_odds(
                pitcher_name=pitcher_name,
                target_date=target_date,
                sources=sources,
            )
            return jsonify(
                {
"status": "success",
"pitcher": pitcher_name,
"date": target_date,
"odds": _serialize(odds),
"has_odds": bool(odds),
                }
            )
        else:
            odds = get_all_pitcher_props_today(
                target_date=target_date,
                sources=sources,
                force_refresh=force_refresh,
            )
            age_min = market_cache_age(target_date)
            return jsonify(
                {
"status": "success",
"date": target_date,
"odds": _serialize(odds),
"count": len(odds),
"cache_age_min": age_min,
"from_cache": age_min is not None and not force_refresh,
                }
            )
    except Exception as e:
        logger.exception("Player props odds error")
        return jsonify({"status": "error", "message": str(e)}), 500


@pitcher_props_bp.route("/api/player-props/sources")
def api_player_props_sources():

    try:
        from services.player_props_odds_service import check_sources
        from services.dk_props_scraper import check_dk_connectivity

        status = check_sources()
        dk_conn = check_dk_connectivity()
        if "dk" in status:
            status["dk"]["connectivity"] = dk_conn
        return jsonify({"status": "success", "sources": status})
    except Exception as e:
        logger.exception("Player props sources check error")
        return jsonify({"status": "error", "message": str(e)}), 500


@pitcher_props_bp.route("/api/pitcher-props/grade", methods=["POST"])
def api_grade():

    try:
        data = request.get_json(force=True) or {}
        game_pk = data.get("game_pk")
        if game_pk:
            result = grade_game(int(game_pk))
        else:
            result = grade_all_pending()
        return jsonify({"status": "success", "result": result})
    except Exception as e:
        logger.exception("Grading error")
        return jsonify({"status": "error", "message": str(e)}), 500


def _serialize(obj):

    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    return obj
