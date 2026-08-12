# MLB data platform engineering report

Generated: 2026-08-11

## Executive decision

The historical platform is operational, reproducible, and leakage-gated. No new model was promoted to the live betting application. The new benchmarks cover a different historical dataset and lack graded shadow predictions, so they are not a safe drop-in champion comparison.

## Ingestion summary

- Kaggle Vegas: 45,530 source team rows, 22,764 canonical candidate games, 91,056 immutable closing-market outcomes.
- Retrosplits 2012–2021: 46,264 team-game rows and 673,377 player-game rows.
- Every source file is SHA-256 hashed; 21 ingestion runs are recorded in SQLite.
- Two source rows for PIT–STL on 2020-09-18 remain quarantined because the two Kaggle files disagree on the moneyline identity. No guess was made.
- The originally generated warehouses were removed and reproducibly rebuilt after validation identified incorrect adjacency and Washington alias assumptions.

## Database and identity coverage

- Warehouse: `database/mlb_data_platform.db`.
- Canonical games: 23,168.
- Vegas games with an exact Retrosplits performance join: 22,728 / 22,764 (99.84%).
- Normalization covers historical Retrosheet aliases, Washington `WAS`, franchise renames, ordinary games, and doubleheaders.
- Suspended games retain original game date and player appearance/resume date.
- Unresolved records are stored in `identity_quarantine`; fuzzy joins are prohibited.

## Point-in-time dataset

- Output: `data/platform/historical_features.csv`.
- Version: `0b59827638c7b459`.
- SHA-256: `983a0f630985445206091adab1a3722779c7ae99e76bcb7bd3406ade423e628e`.
- Rows: 22,764; moneyline labels: 22,728; non-push totals labels: 21,621.
- All rolling performance features are shifted by one completed game. Current-game results are labels only.
- Included: rolling team run/hit/walk/strikeout form, rest, win form, moneyline and total implied probabilities, vig, form edges, and market×form interactions.
- Excluded for insufficient point-in-time evidence: historical confirmed lineups, historical weather forecasts, available-reliever rosters, and within-game market movement.

## Feature validation

Four expanding walk-forward folds were evaluated using permutation importance, LOFO ablation, SHAP, stability, correlation, and redundancy.

- Moneyline: 49 features — 19 KEEP, 27 INVESTIGATE, 3 REMOVE.
- Totals: 50 features — 10 KEEP, 34 INVESTIGATE, 6 REMOVE.
- Moneyline fold AUCs: 0.5991, 0.6119, 0.6128, 0.6274.
- Totals fold AUCs: 0.5008, 0.5107, 0.5145, 0.5156.

The generated CSV verdict files contain per-feature evidence; no feature is recommended from a canned rule without measured permutation and LOFO behavior.

## Model and calibration comparison

All families used the same chronological 70/15/15 split and independently selected sigmoid or isotonic calibration on the validation period.

Moneyline best log loss: Extra Trees — AUC 0.6129, log loss 0.6703, Brier 0.2387, ECE 0.0239. The three-model ensemble had slightly higher AUC (0.6144) and positive test-period flat ROI on 128 gated bets, but slightly worse log loss/Brier and no shadow validation.

Totals best log loss: ensemble — AUC 0.5203, log loss 0.6926, Brier 0.2497, ECE 0.0052. This is too close to random discrimination for promotion. ROI results are threshold-sensitive and based on small selected-bet counts; they are reported, not treated as promotion evidence.

Temperature scaling and beta calibration are explicitly marked not implemented. They were not simulated or mislabeled as tested.

## Champion decision

KEEP THE EXISTING LIVE CHAMPION.

Reasons:

1. The platform candidates were trained on 2012–2021 team/market features, while the current champion uses a different modern feature schema.
2. There are zero graded shadow predictions for the candidates.
3. Moneyline calibration improves materially in the historical benchmark, but the ensemble does not consistently dominate Extra Trees across log loss, Brier, and ROI.
4. Totals discrimination remains weak despite restored historical closing lines.

## Remaining blockers

- Historical official pregame lineup snapshots with publication timestamps.
- Historical weather forecasts captured before first pitch, not observed game weather.
- Multi-timestamp odds snapshots for genuine movement and CLV features; Vegas contains closing only.
- Reliable historical active-reliever/availability snapshots.
- MLB `game_pk` backfill for the 2012–2021 source aliases. Current canonical source identities are deterministic but not all are MLB ids.
- At least 30 graded shadow predictions per target before any production promotion decision.

## Technical debt

- Replace deprecated scikit-learn `cv='prefit'` calibration with `FrozenEstimator` before scikit-learn 1.8.
- Add temperature and beta calibration implementations with held-out selection.
- Convert large JSON statistic payloads to typed columnar tables or Parquet to reduce the SQLite warehouse size.
- Add automatic MLB schedule reconciliation for the remaining 36 non-joined games.
- Add a formal migration framework for warehouse schema versions.

## Future opportunities

- Acquire timestamped pregame lineup and weather archives.
- Extend Retrosplits ingestion outside the Vegas overlap only when a defined modeling use requires it.
- Build a shadow inference adapter that recreates the same platform features for current games.
- Promote only after chronological backtests and live shadow outcomes agree on calibration and economic metrics.
