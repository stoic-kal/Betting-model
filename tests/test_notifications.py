import sys
import time

from services import discord_service as ds
from services.notifications import embeds

TEST_PREFIX = "🧪 TEST ONLY — "


def _tag(embed: dict) -> dict:

    embed["title"] = TEST_PREFIX + embed.get("title", "")
    return embed


def _send(label: str, channel_key: str, embed: dict) -> bool:
    ok = ds._engine.post_to_channel(channel_key, embed=_tag(embed))
    print(
        f'  {"OK" if ok else "FAIL"} {label:<22} -> #{channel_key:<13} {"sent" if ok else "FAILED"}'
    )
    return ok


def main():
    print("Discord notification health check — sending one TEST ONLY message per type.\n")
    print(f"is_enabled(): {ds.is_enabled()}")
    for key in ("picks", "results", "health", "model_output"):
        transport = ds._engine._channels.get(key, [None])[0]
        configured = transport.is_configured() if transport else False
        print(f'  channel "{key}" configured: {configured}')
    print()

    results = {}

    results["Model Output"] = _send(
        "Model Output",
        "model_output",
        embeds.build_moneyline_output_embed(
            {
                "pick_type": "moneyline",
                "matchup": "TEST @ TEAM",
                "prediction": "TEST Team ML",
                "model_prob": 0.611,
                "market_prob": 0.580,
                "model_version": "v3.3-advanced (test)",
            }
        ),
    )

    results["Moneyline Pick"] = _send(
        "Moneyline Pick",
        "picks",
        embeds.build_pick_embed(
            {
                "pick_type": "moneyline",
                "matchup": "TEST @ TEAM",
                "pick": "TEST Team ML",
                "model_prob": 0.611,
                "kelly_units": 1.0,
                "odds_dec": 1.85,
                "sportsbook": "Test Book",
            }
        ),
    )

    results["Totals Pick"] = _send(
        "Totals Pick",
        "picks",
        embeds.build_pick_embed(
            {
                "pick_type": "totals",
                "matchup": "TEST @ TEAM",
                "pick": "UNDER 7.5",
                "model_prob": 0.640,
                "expected_total": 6.10,
                "market_line": 7.5,
                "kelly_units": 0.75,
                "odds_dec": 1.91,
                "sportsbook": "Test Book",
            }
        ),
    )

    results["Game Result"] = _send(
        "Game Result",
        "results",
        embeds.build_result_embed(
            {
                "matchup": "TEST @ TEAM",
                "pick": "TEST Team ML",
                "pick_type": "moneyline",
                "status": "won",
                "profit_units": 0.85,
                "overall_record": "0-0 (test)",
                "moneyline_record": "0-0 (test)",
                "totals_record": "0-0 (test)",
            }
        ),
    )

    results["Daily Summary"] = _send(
        "Daily Summary",
        "results",
        embeds.build_daily_summary_embed(
            {
                "moneyline_picks": 0,
                "totals_picks": 0,
                "highest_probability_pick": "TEST Team ML (test data)",
                "highest_kelly_pick": "TEST Team ML (test data)",
            }
        ),
    )

    results["Weekly Summary"] = _send(
        "Weekly Summary",
        "results",
        embeds.build_weekly_summary_embed(
            {
                "moneyline_record": "0-0 (test)",
                "totals_record": "0-0 (test)",
                "overall_record": "0-0 (test)",
                "roi": 0.0,
                "profit": 0.0,
                "model_version": "v3.3-advanced (test)",
            }
        ),
    )

    results["Model Health"] = _send(
        "Model Health",
        "health",
        embeds.build_model_health_embed(
            {
                "health_score": "N/A (test)",
                "moneyline_roi": 0.0,
                "totals_roi": 0.0,
                "calibration_grade": "N/A",
                "recommendation": "This is a test message — no action needed.",
            }
        ),
    )

    results["Diagnostics"] = _send(
        "Diagnostics",
        "health",
        embeds.build_diagnostics_embed(
            {
                "runs_checked": 0,
                "issues_found": 0,
                "note": "test run",
            }
        ),
    )

    print()
    passed = sum(results.values())
    total = len(results)
    print(f"{passed}/{total} notifications delivered.")
    if passed < total:
        print("One or more channels are unconfigured or unreachable — see warnings above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
