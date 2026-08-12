# Totals Disagreement Taxonomy

## Cohort definition

Large disagreement was defined without an outcome-tuned percentage threshold.
For each of OOF folds 2–4, `X` was the 80th percentile of absolute disagreement
observed in earlier OOF blocks. The resulting cutoffs were 2.64, 2.51, and 2.50
percentage points. Outcomes were not used to select games, features, cluster count,
or cluster membership.

The cohort contains 1,100 games. K-means models with 2–8 clusters were compared by
silhouette score; two clusters won at 0.194. That low score means the taxonomy is
useful descriptively but the games do not form sharply separated natural groups.

## What large-disagreement games have in common

Across the complete cohort:

- Home favorites represented 71.5% of games versus 63.2% in the reference set.
- Houston home contexts were 1.70× as common, the Yankees 1.62×, Boston 1.45×,
  Baltimore 1.41×, Cleveland 1.41×, and Washington 1.34×.
- June was only mildly enriched at 1.10×. There was no dominant month effect.
- Average absolute disagreement was 3.45 percentage points.
- The signed average was −1.64 points: most disagreement came from the model being
  less bullish on the Over than the market, not more bullish.
- Across this broad cohort the base model narrowly beat the market: 0.693239 versus
  0.693744 Log Loss. Therefore “large disagreement” by itself is not the failure.

Home-team labels are a combined team/park context. Reliable venue metadata exists
for only 404 historical games, so these must not be interpreted as isolated causal
park effects.

## Cluster 0: strong-form home favorites

This group contains 683 games.

- 88.4% were home favorites.
- Home form was +0.77 standard deviations above the reference average.
- Run-form edge was +0.79 standard deviations.
- Away-bullpen ER was +0.23 standard deviations.
- Houston was 2.52× as common, the Yankees 2.14×, the Dodgers 2.06×, Cleveland
  1.86×, and the Cubs 1.63×.
- The model was below the market in 87.6% of games; median signed disagreement was
  −3.11 percentage points.
- The model beat the market by 0.000831 Log Loss.

Interpretation: the market appears more willing than the model to translate strong
home-team form and weak away-bullpen results into Over probability. The model's
relative conservatism was slightly beneficial in this sample.

## Cluster 1: negative-form, road-favorite, higher-total contexts

This group contains 417 games.

- 56.1% were road favorites, 1.52× the reference share.
- Home form was −0.91 standard deviations below average.
- Run-form edge was −0.97 standard deviations.
- Closing total was +0.26 standard deviations above average.
- Away-bullpen ER was −0.39 standard deviations, indicating better recent away
  bullpen results.
- Baltimore home contexts were 2.93× as common, Detroit 2.32×, and Kansas City
  1.59×.
- Disagreement direction was mixed: the model was more bullish in 47.2% of games.
- Model and market were effectively tied: market advantage was only 0.000028.

Interpretation: this cluster is created by conflicting signals—higher market totals
against negative home/run form and better away-bullpen results. Neither model nor
market resolved that conflict reliably.

## Cutoff sensitivity

| Prior-OOF quantile | Mean X | Games | Model LL | Market LL | Model advantage |
|---|---:|---:|---:|---:|---:|
| 75th percentile | 2.27 pp | 1,429 | 0.693062 | 0.693918 | +0.000856 |
| 80th percentile | 2.55 pp | 1,100 | 0.693239 | 0.693744 | +0.000505 |
| 90th percentile | 3.27 pp | 492 | 0.697233 | 0.695469 | −0.001763 |

The actual failure mode is concentrated in the most extreme tail. Moderate
disagreements favor the model slightly; only the top 10% favor the market. This is
a descriptive result, not authorization for a production threshold.

## Unavailable taxonomy dimensions

Temperature, wind, starter quality, pitcher handedness, lineup quality, division
status, and interleague status cannot be evaluated on this 2012–2021 market cohort.
They are absent or lack point-in-time historical coverage. Bullpen taxonomy is
limited to the accepted away-bullpen ER feature. No missing dimension was imputed
or silently proxied.

## Answer

Large-disagreement games most often involve home favorites—especially strong-form
home teams—where the market is more bullish on scoring than the model. That broad
group is not harmful; the model is marginally better. The harmful games are the
far extreme of the disagreement distribution, and the available context fields do
not form a strong, stable cluster explaining them. Weather, starters, and verified
lineups are the most important missing dimensions needed to explain that tail.
