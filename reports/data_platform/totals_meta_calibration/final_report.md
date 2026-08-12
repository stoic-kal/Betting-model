# Totals Meta-Calibration Experiment

## Protocol

The second stage was trained exclusively on chronological out-of-fold predictions
from the accepted-feature Extra Trees totals model. Base fold 1 trained the first
meta model and meta-tested on base fold 2; folds 1–2 meta-trained the next model
and tested on fold 3; folds 1–3 trained the final model and tested on fold 4.
Neither base-model in-sample predictions nor future meta-test labels entered a
meta-training window.

Inputs were base probability, market implied probability, their signed difference,
closing total, base confidence, `home_runs_accel_10v30`,
`home_hits_accel_5v10`, and `away_bp_er_14g`.

The comparison market blend selected a continuous market weight from 0.00 to 1.00
using log loss on the preceding meta-training blocks. It contains no disagreement
threshold. Selected weights were 0.54, 0.27, and 0.53 for test folds 2–4.

Promotion required lower mean Log Loss, Brier, and ECE; lower Log Loss and Brier
in all three folds; and lower ECE in at least two folds.

## Calibration comparison

| Method | Log Loss | Brier | ECE | LL folds better | Brier folds better | ECE folds better | Promote |
|---|---:|---:|---:|---:|---:|---:|---|
| Train-fitted market blend | 0.692650 | 0.249751 | 0.018533 | 1/3 | 1/3 | 1/3 | No |
| Current base model | 0.692678 | 0.249764 | 0.017799 | — | — | — | Keep |
| Market | 0.692787 | 0.249820 | 0.018601 | — | — | — | No |
| Platt | 0.693449 | 0.250151 | 0.023224 | 0/3 | 0/3 | 1/3 | No |
| Low-depth gradient boosting | 0.693659 | 0.250256 | 0.021017 | 0/3 | 0/3 | 1/3 | No |
| Multivariate logistic meta | 0.693904 | 0.250365 | 0.022772 | 1/3 | 1/3 | 0/3 | No |
| Isotonic | 0.695330 | 0.250726 | 0.027531 | 0/3 | 0/3 | 0/3 | No |

The market blend's average Log Loss improvement was only 0.000028 and it worsened
ECE. Its fold weights were also unstable. This is not consistent evidence for
shrinkage.

## Walk-forward behavior

- Fold 2: the base model was best among the tested candidates at 0.691698 Log Loss.
- Fold 3: the market was best at 0.692922; the blend helped relative to base but
  did not reach the market.
- Fold 4: multivariate logistic was narrowly best at 0.692433, but its earlier
  folds were materially worse.
- No learned calibrator improved Log Loss or Brier in more than one fold.

## Disagreement analysis

Disagreement was divided into five equal-frequency signed bins; no percentage
threshold was used. In the most model-bullish quintile, the market achieved
0.691414 Log Loss versus 0.693361 for the base model. The market blend improved
that quintile to 0.692159 but did not fully correct it. Every learned calibrator
was worse than both the market and blend there.

In the most market-bullish quintile, the base model was best at 0.692155 versus
0.693781 for the market. This opposing behavior explains why a global learned
calibrator or blend failed to improve consistently.

## Meta-model feature importance

The low-depth gradient model concentrated importance in closing total (0.291),
away bullpen earned runs over 14 games (0.243), base probability (0.182), signed
disagreement (0.146), and confidence (0.129). Hitter accelerations contributed
almost nothing. The logistic model likewise ranked closing total and bullpen
quality first, but its coefficients did not generalize across folds.

Importance indicates what the failed candidates used; it is not evidence that
these relationships should be promoted.

## Recommendation

Keep the current totals model unchanged. A learned meta calibrator does **not**
outperform either the current model or simple market shrinkage consistently. The
train-fitted market blend has the best average Log Loss by a negligible margin,
but fails every consistency requirement and worsens calibration error.

The disagreement failure is real, but the available out-of-fold history does not
support a stable correction. Accumulate additional chronological OOF seasons and
rerun this exact protocol; do not introduce a threshold or production shrinkage
rule now.
