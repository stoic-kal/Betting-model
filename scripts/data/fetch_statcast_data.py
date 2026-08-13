"""Incrementally update the local pitch-level Statcast archive.

This script deliberately leaves downstream feature/model tables alone. It only
updates data/statcast_raw.csv, fetching dates that are newer than the latest
stored game_date (or a user-supplied --start date), then deduplicating and
atomically replacing the archive after validation.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from pybaseball import statcast


DEFAULT_OUTPUT = Path("data/statcast_raw.csv")
DEFAULT_SEASON_START = date(2026, 3, 1)
DEFAULT_CHUNK_DAYS = 3
DEFAULT_RETRIES = 3

# Stable pitch identifiers supplied by Baseball Savant. Together these identify
# a pitch without relying on dataframe row order.
PITCH_KEY = ["game_pk", "at_bat_number", "pitch_number"]
REQUIRED_COLUMNS = ["game_date", "game_pk", "batter", "pitcher", "pitch_type"]


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_chunks(start: date, end: date, chunk_days: int):
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def validate_frame(df: pd.DataFrame, label: str) -> None:
    if df.empty:
        return
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(f"{label} is missing required Statcast columns: {missing}")


def fetch_chunk(start: date, end: date, retries: int) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            print(f"  Fetching {start} -> {end} (attempt {attempt}/{retries})")
            frame = statcast(start_dt=start.isoformat(), end_dt=end.isoformat())
            validate_frame(frame, f"download {start}..{end}")
            print(f"    received {len(frame):,} rows")
            return frame
        except Exception as exc:  # network/upstream errors vary by pybaseball version
            last_error = exc
            if attempt < retries:
                wait = 2 ** attempt
                print(f"    error: {exc}; retrying in {wait}s")
                time.sleep(wait)
    raise RuntimeError(f"Failed to fetch Statcast {start}..{end}: {last_error}")


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    available_key = [c for c in PITCH_KEY if c in df.columns]
    if len(available_key) == len(PITCH_KEY):
        return df.drop_duplicates(subset=PITCH_KEY, keep="last")

    # This should only matter for an unexpected/older schema. Preserve safety by
    # deduplicating complete rows rather than guessing a weaker pitch identity.
    print("WARNING: pitch identity columns incomplete; falling back to full-row dedupe")
    return df.drop_duplicates(keep="last")


def atomic_write_csv(df: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally update Statcast pitch data")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start", type=parse_date, help="Override first date to fetch (YYYY-MM-DD)")
    parser.add_argument("--end", type=parse_date, default=date.today(), help="Last date to fetch")
    parser.add_argument("--chunk-days", type=int, default=DEFAULT_CHUNK_DAYS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    args = parser.parse_args()

    if args.chunk_days < 1:
        raise SystemExit("--chunk-days must be >= 1")
    if args.retries < 1:
        raise SystemExit("--retries must be >= 1")

    existing = pd.DataFrame()
    latest: date | None = None

    if args.output.exists():
        print(f"Loading existing archive: {args.output}")
        existing = pd.read_csv(args.output, low_memory=False)
        validate_frame(existing, "existing archive")
        if not existing.empty:
            dates = pd.to_datetime(existing["game_date"], errors="coerce")
            if dates.notna().any():
                latest = dates.max().date()
            print(f"Existing rows: {len(existing):,}")
            print(f"Existing coverage: {dates.min().date()} -> {latest}")

    if args.start:
        fetch_start = args.start
    elif latest:
        fetch_start = latest + timedelta(days=1)
    else:
        fetch_start = DEFAULT_SEASON_START

    if fetch_start > args.end:
        print(f"Archive is already current through requested end date {args.end}.")
        return

    print(f"Updating Statcast: {fetch_start} -> {args.end}")
    print(f"Chunk size: {args.chunk_days} day(s)")

    downloads: list[pd.DataFrame] = []
    for chunk_start, chunk_end in iter_chunks(fetch_start, args.end, args.chunk_days):
        frame = fetch_chunk(chunk_start, chunk_end, args.retries)
        if not frame.empty:
            downloads.append(frame)

    if not downloads:
        print("No new Statcast rows returned; existing archive was not modified.")
        return

    new_data = pd.concat(downloads, ignore_index=True)
    validate_frame(new_data, "combined download")

    before = len(existing) + len(new_data)
    combined = pd.concat([existing, new_data], ignore_index=True, sort=False)
    combined = dedupe(combined)
    combined["game_date"] = pd.to_datetime(combined["game_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    combined = combined.sort_values(
        [c for c in ["game_date", "game_pk", "at_bat_number", "pitch_number"] if c in combined.columns],
        kind="stable",
    ).reset_index(drop=True)
    validate_frame(combined, "final archive")

    duplicates_removed = before - len(combined)
    final_dates = pd.to_datetime(combined["game_date"], errors="coerce")

    print("\nValidation")
    print(f"  downloaded: {len(new_data):,}")
    print(f"  duplicates removed: {duplicates_removed:,}")
    print(f"  final rows: {len(combined):,}")
    print(f"  final coverage: {final_dates.min().date()} -> {final_dates.max().date()}")
    print("  rows by year:")
    print(final_dates.dt.year.value_counts().sort_index().to_string())

    atomic_write_csv(combined, args.output)
    print(f"\nSaved atomically to {args.output}")


if __name__ == "__main__":
    main()
