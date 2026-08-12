# Historical Replay Engine - trust remediation report

## Scope

Only the critical audit findings were addressed. No model was trained, no replay was run, and nothing was integrated with production.

## Changes

1. **Doubleheader leakage:** all games involving a team that appears more than once on the same calendar date are excluded from both training and evaluation when completion order is unavailable. Exclusions are counted and saved in run metadata. The loader asserts that no same-team/same-date ambiguity remains.
2. **Wager selection:** positive-side and negative-side EV are calculated independently. The replay selects the side with the higher EV and places no wager unless that EV is positive and the configured edge requirement is satisfied.
3. **Integrity assertions:** replay aborts on duplicate `(model, canonical_game_id)` predictions, missing model coverage, unexpected or silently excluded games, missing feature provenance, insufficient training history, one-class training history, or training/evaluation date overlap.
4. **Naming:** the configured comparator is now `Historical Baseline`, not `Champion`. Existing immutable old run artifacts retain their historical labels and are not rewritten.

## Minimal verification

- 16 focused tests passed.
- No model fitting or historical replay was performed.
- 654 ambiguous same-day games are excluded from the current source dataset.
- Remaining same-team/same-date duplicates: 0.
- Moneyline features with provenance: 49/49.
- Totals features with provenance: 50/50.
- Tests verify higher-EV side selection even when it is the lower-probability side.
- Tests verify no wager when both sides have non-positive EV.
- Tests verify duplicate prediction and mismatched coverage failures.
- Existing tests verify strict prior-date training selection and future timestamp rejection.

## Remaining limitations

- Excluding all ambiguous same-day games is conservative. It sacrifices valid doubleheader observations because verified completion timestamps are unavailable.
- The engine remains a closing-time replay because the historical platform contains closing prices only.
- Feature provenance is categorical at the dataset-column level; it does not replace immutable event-level source timestamps.
- The Historical Baseline is not the modern production champion and must not be described as such.
- Old replay runs were produced before these trust fixes and must not be used for screening decisions.

## Trust decision

The replay engine is now trustworthy enough for **historical model screening within its stated closing-time, non-doubleheader scope**. It is not evidence of live deployability. Any candidate that succeeds here still requires feature-equivalence review and shadow validation.
