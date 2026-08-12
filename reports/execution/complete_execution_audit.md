# Complete betting execution audit

Scope: complete pick history; never loss-only.

## Model Problems

```json
{
  "moneyline": {
    "n": 148,
    "win_rate": 0.5878,
    "brier": 0.268075,
    "log_loss": 0.792653,
    "verdict": "descriptive complete-history metrics; no causal weakness inferred"
  },
  "totals_all_legacy_and_current": {
    "n": 106,
    "win_rate": 0.5,
    "brier": 0.263448,
    "log_loss": 0.721958,
    "verdict": "descriptive complete-history metrics; no causal weakness inferred"
  },
  "totals_corrected_input_v2": {
    "n": 0,
    "verdict": "insufficient evidence"
  },
  "conclusion": "The corrected totals model cannot yet be evaluated because it has no resolved input-v2 picks. Legacy totals outcomes remain descriptive and are not evidence against the corrected engine."
}
```

## Data Problems

```json
{
  "malformed_locked_odds": 0,
  "missing_feature_snapshots": 90,
  "legacy_totals_rows": 106,
  "conclusion": "Malformed historical locked odds were not observed; legacy totals inputs remain a comparability limitation."
}
```

## Execution Problems

```json
{
  "zero_theoretical_kelly_predictions": 62,
  "legacy_recommendation_rows": 219,
  "realized_stake_rows": 0,
  "conclusion": "Legacy execution did not persist realized stakes separately, so historical bankroll results must not be presented as executed-stake results."
}
```

## Portfolio Management Problems

```json
{
  "scope": "complete picks history; won/lost outcomes for return and correlation metrics",
  "data_quality": {
    "total_picks": 272,
    "resolved_picks": 254,
    "malformed_odds": 0,
    "realized_stake_coverage_resolved": 0.0,
    "note": "legacy realized stakes remain unknown and are not backfilled"
  },
  "simultaneous_wager_correlation": {
    "paired_games": 105,
    "pearson_win_indicator": 0.0305,
    "both_lost_rate": 0.219,
    "both_won_rate": 0.2952
  },
  "theoretical_kelly_portfolio": {
    "active_days": 11,
    "net_units": 5.7105,
    "mean_daily_units": 0.5191,
    "daily_volatility_units": 1.6024,
    "downside_deviation_units": 1.6196,
    "sharpe_per_active_day": 0.324,
    "sortino_per_active_day": 0.3205,
    "historical_var_95_units": -2.0255,
    "historical_cvar_95_units": -3.0495,
    "max_drawdown_units": 3.532,
    "winning_day_rate": 0.6364
  },
  "realized_stake_portfolio": {
    "active_days": 0
  },
  "exposure": {
    "max_theoretical_game_units": 2.0,
    "max_theoretical_day_units": 24.0,
    "max_realized_game_units": null,
    "max_realized_day_units": null,
    "theoretical_stake_hhi": 0.006287
  },
  "conclusion": "Historical theoretical Kelly exposure exceeded the new game limit in some games; future stakes are capped at single-game and daily levels."
}
```
