# Existing-Data Feature Discovery

## Scope and decision rule

This pass used only `data/platform/historical_features.csv` and the existing
`player_game_history` table. No external data was queried or added. The current
platform Extra Trees champion was the baseline for both targets. Each candidate
was evaluated on four expanding chronological folds (50/10, 60/10, 70/10, and
80/10 percent train/test). A feature was retained only when its incremental
log-loss improvement was positive on average and in at least three of four
folds. The final joint feature sets also satisfy that rule.

The prior diagnostic audit remains the audit of the 49 moneyline and 50 totals
baseline inputs. This pass tested 122 transformations of those inputs for each
target (244 target-feature decisions) and records every decision and fold result
in `candidate_feature_verdicts.csv`.

## Candidate families and point-in-time guarantees

| Family | Why it could add information | Point-in-time construction |
|---|---|---|
| Rolling/trend | Differences between short and long windows can separate a level from a recent acceleration or decline. | All source team windows were already shifted before the current game; candidates only subtract those pregame windows. |
| Recent form | Offense, prevention, and combined run environment may describe different paths to the same team-level average. | Uses only shifted 5/10/30-game aggregates and pregame rest days. |
| Market-derived | Log-odds, favorite strength, price asymmetry, juice skew, and a season-relative total can express nonlinear market state. | Uses the recorded pregame market observation. The season-relative total mean and standard deviation use `shift(1)` before expanding aggregation. |
| Bullpen | Reliever workload and outcomes can expose fatigue and current relief quality not present in team averages. | A reliever is `P_G > 0` and `P_GS == 0`; every rolling sum is shifted by one completed game before 3/7/14-game aggregation. |
| Interactions | Market, form, rest, total, and bullpen effects may be conditional rather than additive. | Products and differences combine only the point-in-time-safe inputs above. |

## Features added

### Moneyline

| Feature | New information | Mean log-loss gain | Fold gains |
|---|---|---:|---|
| `home_runs_accel_5v10` | Home scoring over the last five games relative to its ten-game level. | 0.000286 | +0.000164, +0.000130, -0.000036, +0.000888 |
| `away_walks_accel_5v10` | Recent away-team plate-discipline movement after accounting for its ten-game level. | 0.000037 | +0.000033, +0.000316, +0.000808, -0.001009 |

Joint result: mean log loss improved from **0.670858 to 0.670534**
(+0.000323; 0.048% relative), mean AUC improved from **0.612879 to
0.613120** (+0.000241), and log loss improved in three of four folds.

### Total

| Feature | New information | Mean log-loss gain | Fold gains |
|---|---|---:|---|
| `home_runs_accel_10v30` | Medium-term home scoring movement relative to the longer baseline. | 0.000077 | +0.000377, +0.000178, -0.000290, +0.000041 |
| `home_hits_accel_5v10` | Very recent home contact/output movement that is not identical to runs. | 0.000141 | +0.000121, +0.000432, +0.000212, -0.000202 |
| `away_bp_er_14g` | Runs allowed by away relievers over their prior 14 team games, preserving both quality and exposure. | 0.000133 | +0.000100, -0.000049, +0.000001, +0.000480 |

Joint result: mean log loss improved from **0.693255 to 0.692904**
(+0.000351; 0.051% relative), mean AUC improved from **0.510450 to
0.517939** (+0.007489), and log loss improved in three of four folds.

## Features rejected

For moneyline, 120 of 122 candidates failed the consistency gate. For totals,
119 of 122 failed. This includes all new market transformations, all interaction
terms, all recent-form composites, all moneyline bullpen candidates, and all
other rolling/trend and totals bullpen candidates. They were not added to the
accepted dataset. Exact per-feature verdicts and all four fold deltas are in
`candidate_feature_verdicts.csv`; family bundle results are in
`feature_discovery_report.json`.

## Remaining opportunities using current data

- Build starter-lineup-only hitter form from `player_game_history.B_XI`, then
  aggregate the nine known starters using prior player appearances only.
- Derive bullpen availability rather than generic quality: reliever-level pitches
  in the prior one to three calendar days, consecutive-use days, and the quality
  of relievers not fatigued.
- Replace fixed 5/10/30 windows with half-life-weighted summaries, but validate
  half-lives inside each training fold rather than globally.
- Add season-to-date shrinkage toward prior history for early-season normalization.
- Test market movement only if multiple pregame snapshots already stored for the
  same game have adequate coverage; do not infer movement from closing lines.

## Highest-impact remaining improvement

The strongest remaining opportunity without new data is a **confirmed-starting-
lineup strength feature built from prior player performance**. The warehouse
already contains player game histories and the `B_XI` starter indicator, while
the current platform baseline is largely team-level. A strictly shifted,
recency-weighted aggregation of the nine starters can represent personnel changes
that team rolling averages cannot. Historical substitutes and postgame-only
participants must be excluded, and the feature should be emitted only when a
pregame-confirmed lineup is available.
