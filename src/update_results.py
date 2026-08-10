import sqlite3
from datetime import datetime

import requests

try:
    from .matchup_normalizer import MatchupNormalizer
except ImportError:
    from matchup_normalizer import MatchupNormalizer


class ResultsUpdater:

    def __init__(self, db_path="database/picks.db"):
        self.db_path = db_path
        self.base_url = "https://statsapi.mlb.com/api/v1"
        self.normalizer = MatchupNormalizer()

    def extract_line(self, pick_str):

        try:
            parts = pick_str.split()
            if len(parts) >= 2:
                return float(parts[-1])
        except:
            pass
        return None

    def convert_home_away_to_team(self, matchup, pick_choice):

        if pick_choice not in ("HOME", "AWAY"):
            return self.normalizer.extract_team(pick_choice)

        parts = matchup.split(" @ ")
        if len(parts) != 2:
            return pick_choice

        away_team = self.normalizer.extract_team(parts[0])
        home_team = self.normalizer.extract_team(parts[1])

        return home_team if pick_choice == "HOME" else away_team

    def get_final_scores(self, target_date):

        url = f"{self.base_url}/schedule"
        params = {"startDate": target_date, "endDate": target_date, "sportId": 1}

        try:
            resp = requests.get(url, params=params, timeout=10)
            final_games = {}

            for date_obj in resp.json()["dates"]:
                for game in date_obj["games"]:
                    if game["status"]["abstractGameState"] == "Final":
                        try:
                            home_runs = game["teams"]["home"].get("score", 0)
                            away_runs = game["teams"]["away"].get("score", 0)

                            home_team = game["teams"]["home"]["team"]["name"]
                            away_team = game["teams"]["away"]["team"]["name"]

                            matchup_full = f"{away_team} @ {home_team}"
                            norm_matchup = self.normalizer.normalize_matchup(matchup_full)

                            final_games[norm_matchup] = {
                                "home_runs": home_runs,
                                "away_runs": away_runs,
                                "total_runs": home_runs + away_runs,
                                "home_won": home_runs > away_runs,
                                "home_team": self.normalizer.extract_team(home_team),
                                "away_team": self.normalizer.extract_team(away_team),
                            }
                        except:
                            continue

            return final_games
        except Exception as e:
            print(f"Error fetching scores: {e}")
            return {}

    def update_all_results(self, target_date):

        final_games = self.get_final_scores(target_date)

        if not final_games:
            print(f"Updating results for {target_date}...\nNo final games found")
            return 0

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        score_columns = {row[1] for row in c.execute("PRAGMA table_info(picks)").fetchall()}
        stores_scores = {"home_score", "away_score", "actual_total"} <= score_columns

        if stores_scores:
            c.execute(
                """SELECT id, matchup, pick, pick_type, status, odds FROM picks
                         WHERE date=? AND (status="pending" OR actual_total IS NULL)""",
                (target_date,),
            )
        else:
            c.execute(
                'SELECT id, matchup, pick, pick_type, status, odds FROM picks WHERE date = ? AND status = "pending"',
                (target_date,),
            )
        picks = c.fetchall()

        if not picks:
            print(f"No pending picks for {target_date}")
            conn.close()
            return 0

        print(f"Updating results for {target_date}...\nFound {len(final_games)} final games")
        print(f"Found {len(picks)} pending picks for {target_date}\n")

        updated_count = 0
        api_matchups = list(final_games.keys())

        graded_for_notification = []

        for pick_id, matchup, pick_choice, pick_type, existing_status, pick_odds in picks:
            best_match = self.normalizer.find_best_match(matchup, api_matchups)

            if not best_match:
                continue

            game_result = final_games[best_match]
            if existing_status == "void" and stores_scores:
                c.execute(
                    """UPDATE picks SET updated_at=?, home_score=?, away_score=?, actual_total=? WHERE id=?""",
                    (
                        datetime.now().isoformat(),
                        game_result["home_runs"],
                        game_result["away_runs"],
                        game_result["total_runs"],
                        pick_id,
                    ),
                )
                updated_count += 1
                continue

            actual_pick = self.convert_home_away_to_team(matchup, pick_choice)

            if pick_type == "moneyline":
                home_team = game_result["home_team"]
                away_team = game_result["away_team"]

                pick_lower = actual_pick.lower()

                if pick_lower == home_team:
                    won = 1 if game_result["home_won"] else 0
                elif pick_lower == away_team:
                    won = 1 if not game_result["home_won"] else 0
                else:
                    continue

            elif pick_type == "totals":
                line = self.extract_line(pick_choice)
                total = game_result["total_runs"]

                if line is None:
                    continue

                if total == line:
                    status = "push"
                    if stores_scores:
                        c.execute(
                            """UPDATE picks SET status=?, updated_at=?, home_score=?, away_score=?, actual_total=? WHERE id=?""",
                            (
                                status,
                                datetime.now().isoformat(),
                                game_result["home_runs"],
                                game_result["away_runs"],
                                total,
                                pick_id,
                            ),
                        )
                    else:
                        c.execute(
                            "UPDATE picks SET status = ?, updated_at = ? WHERE id = ?",
                            (status, datetime.now().isoformat(), pick_id),
                        )
                    updated_count += 1
                    graded_for_notification.append(
                        {
                            "pick_id": pick_id,
                            "matchup": matchup,
                            "pick": pick_choice,
                            "pick_type": pick_type,
                            "status": status,
                            "odds": pick_odds,
                        }
                    )
                    continue
                if "OVER" in pick_choice:
                    won = 1 if total > line else 0
                else:
                    won = 1 if total < line else 0
            else:
                continue

            status = "won" if won else "lost"
            if stores_scores:
                c.execute(
                    """UPDATE picks SET status=?, updated_at=?, home_score=?, away_score=?, actual_total=? WHERE id=?""",
                    (
                        status,
                        datetime.now().isoformat(),
                        game_result["home_runs"],
                        game_result["away_runs"],
                        game_result["total_runs"],
                        pick_id,
                    ),
                )
            else:
                c.execute(
                    "UPDATE picks SET status = ?, updated_at = ? WHERE id = ?",
                    (status, datetime.now().isoformat(), pick_id),
                )
            updated_count += 1
            graded_for_notification.append(
                {
                    "pick_id": pick_id,
                    "matchup": matchup,
                    "pick": pick_choice,
                    "pick_type": pick_type,
                    "status": status,
                    "odds": pick_odds,
                }
            )

        conn.commit()

        if graded_for_notification:
            try:
                from services import discord_service

                overall_record, ml_record, tot_record = self._current_records(conn)
                for g in graded_for_notification:
                    try:
                        odds = g["odds"]
                        if g["status"] == "won":
                            profit_units = (float(odds) - 1) if odds is not None else None
                        elif g["status"] == "lost":
                            profit_units = -1.0
                        else:
                            profit_units = 0.0
                        print(f"  Sending result notification for pick {g['pick_id']}...")
                        discord_service.send_results(
                            {
                                "matchup": g["matchup"],
                                "pick": g["pick"],
                                "pick_type": g["pick_type"],
                                "status": g["status"],
                                "profit_units": profit_units,
                                "overall_record": overall_record,
                                "moneyline_record": ml_record,
                                "totals_record": tot_record,
                            }
                        )
                        print(f"  Result notification sent for pick {g['pick_id']}")
                    except Exception as e:
                        print(f"  Discord notification failed: {e}")
            except Exception as e:
                print(f"  Discord notification failed: {e}")

        conn.close()

        print(f"\nUpdated {updated_count} picks!")
        return updated_count

    def _current_records(self, conn):

        def _record(pick_type=None):
            q = "SELECT status, COUNT(*) FROM picks WHERE status IN ('won','lost')"
            params = []
            if pick_type:
                q += " AND pick_type=?"
                params.append(pick_type)
            q += " GROUP BY status"
            counts = dict(conn.execute(q, params).fetchall())
            return f"{counts.get('won', 0)}-{counts.get('lost', 0)}"

        return _record(), _record("moneyline"), _record("totals")

    def update_pending_results(self, through_date):

        conn = sqlite3.connect(self.db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(picks)").fetchall()}
        if "actual_total" in columns:
            query = """SELECT DISTINCT date FROM picks
                       WHERE date<=? AND (status="pending" OR actual_total IS NULL)
                       ORDER BY date"""
        else:
            query = (
                'SELECT DISTINCT date FROM picks WHERE status="pending" AND date<=? ORDER BY date'
            )
        dates = [row[0] for row in conn.execute(query, (through_date,)).fetchall()]
        conn.close()
        return sum(self.update_all_results(date_str) or 0 for date_str in dates)


if __name__ == "__main__":
    from config import today_et

    updater = ResultsUpdater()
    updater.update_pending_results(today_et())
