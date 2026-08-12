# Lineup/Trend Feasibility and Segment/Market Diagnostics

## Executive decision

The requested historical lineup experiment cannot be run point-in-time correctly
with the current platform. It was therefore not repeated and no lineup feature was
added or promoted.

The repository already implements lineup wOBA, ISO, OPS proxy, left/right balance,
platoon wOBA/ISO/K/BB/hard-hit rates, and pitch-mix matchup features in
`pipeline/feature_store.py` and `pipeline/statcast_store.py`. The historical lineup
table behind those features is reconstructed from the first nine players observed
in postgame Statcast plate appearances. It is not a timestamped pregame lineup
archive. Treating it as known before first pitch would violate the platform's
point-in-time policy and repeat an existing implementation rather than produce a
new validated feature.

## Coverage audit

| Data area | Coverage | Decision |
|---|---:|---|
| 2012–2021 market/platform games | 22,764 games | Suitable for market and team-form validation |
| Retrosplits `B_XI` starter flag | 385 marked rows across 23,132 games | Insufficient for lineup reconstruction |
| Statcast-derived lineup rows | 89,082 rows, 2024-03-20 through 2025-11-01 | Postgame-derived; prohibited as pregame evidence |
| Statcast batter platoon rows | 143,390 | Supports live calculations when a genuine pregame lineup is supplied |
| Statcast batter/pitch-group rows | 198,527 | Supports live pitch-mix matchups when a genuine pregame lineup is supplied |
| Statcast pitcher/pitch-group rows | 105,698 | Supports live pitch-mix matchups |
| Historical lineup publication timestamp | None | Blocking requirement |
| Overlapping 2012–2021 player IDs/lineups and market games | None | Prevents comparison with the historical platform champion |

The raw 2024–2025 Statcast file supports wOBA, estimated wOBA, ISO, exit velocity,
launch-speed angle (barrel classification input), handedness, pitch type, velocity,
zone, swing/whiff descriptions, and player age. Exact OPS can be derived from event
outcomes. These fields can support the requested trend engine after a valid pregame
lineup identity is available. Bench/rest penalty cannot be reconstructed safely
from postgame participants.

## Segment analysis

Diagnostics use the accepted-feature Extra Trees platform champion and four
expanding chronological test folds. Predictions cover 9,091 moneyline games and
8,648 non-push totals games.

Unavailable segments were not inferred: all 2012–2021 games lack scheduled start
times; roof classification is absent; starter handedness is absent; league/division
membership is absent. Therefore day/night, dome/outdoor, starter-hand, division,
and interleague results are explicitly unavailable.

### Moneyline

- Overall model log loss was 0.670534 versus 0.670041 for the closing market. The
  market was better in three of four folds.
- May was the only material favorable model segment: +0.002226 log-loss advantage
  over the market and positive in all three folds with enough May observations.
- June was consistently unfavorable: -0.002077 and the model beat the market in
  zero of four folds.
- Road-favorite/home-underdog games were weaker than home-favorite games, but the
  model did not beat the market consistently in either role.
- The largest model/market disagreement quartile favored the market by 0.001905;
  the model won only one of four folds. Large moneyline disagreement is not an edge.

### Totals

- Overall model log loss was 0.692904 versus 0.692967 for the closing market, a
  negligible +0.000063 advantage that occurred in only two of four folds.
- When the market's over probability exceeded the model by at least three points,
  the model held a +0.002459 log-loss advantage in three of four folds. This is the
  clearest repeatable disagreement pattern, but it is diagnostic evidence—not yet
  a betting rule.
- When the model's over probability exceeded the market by at least three points,
  the market was better by 0.009919 and won three of four folds. The model is
  systematically overconfident on these over disagreements.
- Low-total games favored the market by 0.000751; the model won one of four folds.
- June and September totals favored the model in three of four folds; July favored
  the market and the model won one of four folds.

## Market-learning conclusion

The market is consistently smarter when the totals model is materially more
bullish on the over. The appropriate next experiment is not a hardcoded segment
adjustment: add a fold-fitted shrinkage/calibration term conditional on signed
model-minus-market disagreement and test it on untouched future folds. Moneyline
disagreement contains no demonstrated edge and should not receive a larger stake.

True CLV cannot be calculated from this historical source because it contains a
closing observation only. Entry-to-close movement must not be invented.

## Exact blocker and required next input

To unlock lineup intelligence, the platform needs an immutable historical table
containing `game_pk`, team, player ID, batting order, lineup status, and a
`published_at` timestamp earlier than scheduled first pitch. Once available, the
existing Statcast histories can generate shifted 3/5/10/20-game, 15/30-day, EWMA,
acceleration, season-z, platoon, and pitch-mix features without adding another
performance dataset.
