# Historical Replay Engine

An isolated research laboratory for evaluating MLB model and wagering ideas on historical point-in-time data before shadow mode.

## Safety boundary

- Reads only approved existing point-in-time CSV datasets.
- Writes only beneath `research/historical_replay/experiments/`.
- Does not import production inference, registry, shadow, Discord, dashboard, or live-betting services.
- Does not connect to `database/picks.db` or write to `database/mlb_data_platform.db`.
- Never promotes or registers a model.

## Replay semantics

For each historical date, both models train on rows with `game_date < replay_date`. All games on the replay date are predicted from the same prior-only training set. The next date then expands the training history. `feature_as_of > game_date` is rejected, labels and known postgame columns are excluded, and explicit unsafe feature requests fail.

Because the current warehouse does not prove completion order within a date, every game involving a team with multiple games on that date is excluded from both training and evaluation. The exclusion count is persisted. Comparisons use a configured `Historical Baseline`; this name deliberately does not imply equivalence to the production champion.

The current historical dataset contains closing prices only. The replay instant is therefore interpreted as immediately before first pitch using the stored closing market. True entry-to-close CLV is unavailable and `clv_report.json` says so explicitly.

## Run

```bash
python3 -m research.historical_replay.cli \
  --config research/historical_replay/experiments/example_moneyline/config.json
```

Each run is immutable and stored at:

```text
research/historical_replay/experiments/<experiment>/runs/<UTC run id>/
```

It contains `predictions.csv`, `daily_results.csv`, the nine required JSON reports, and `metadata.json` with the commit, dataset hash, schema, feature list, configuration, windows, runtime, and seed.

## Supported research changes

Use experiment configuration and adapters for new features, model families, calibration, EV filters, Kelly parameters, bankroll rules, and portfolio rules. Do not import this package from production.
