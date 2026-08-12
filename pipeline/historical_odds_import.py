"""Import normalized or Odds-API-shaped historical snapshots without mutation."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.data_platform import american_to_decimal, begin_run, connect, finish_run, sha256_file, stable_hash

SOURCE = "historical_odds_json"


def _events(payload):
    if isinstance(payload, dict):
        payload = payload.get("data", payload.get("events", []))
    return payload


def ingest(path, db_path=None):
    path = Path(path)
    payload = json.loads(path.read_text())
    conn = connect(db_path) if db_path else connect()
    digest = sha256_file(path)
    run_id = begin_run(conn, SOURCE, "odds_api_v4:v1", digest)
    inserted = 0
    try:
        with conn:
            for event in _events(payload):
                event_id = str(event.get("id") or event.get("event_id"))
                commence = event.get("commence_time")
                for book in event.get("bookmakers", event.get("books", [])):
                    bookmaker = book.get("key") or book.get("title") or "unknown"
                    for market in book.get("markets", [book]):
                        market_key = market.get("key") or market.get("market")
                        captured = market.get("last_update") or book.get("last_update")
                        for outcome in market.get("outcomes", []):
                            price = outcome.get("price")
                            if price is None:
                                continue
                            raw = {"event": event_id, "bookmaker": bookmaker, "market": market_key,
                                   "outcome": outcome, "captured_at": captured}
                            row_hash = stable_hash({"source": SOURCE, **raw})
                            conn.execute("""INSERT OR IGNORE INTO historical_market_snapshots
                              (source,source_event_id,captured_at,commence_time,bookmaker,market,outcome,
                               price_american,price_decimal,point,is_closing,ingestion_run_id,row_sha256,raw_json)
                              VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?)""",
                              (SOURCE,event_id,captured,commence,bookmaker,market_key,outcome.get("name",""),
                               float(price),american_to_decimal(price),outcome.get("point"),run_id,row_hash,json.dumps(raw,sort_keys=True)))
                            inserted += conn.execute("SELECT changes()").fetchone()[0]
        report = {"events": len(_events(payload)), "market_rows_inserted": inserted, "source_sha256": digest}
        finish_run(conn, run_id, "complete", inserted, report)
        return report
    except Exception as exc:
        finish_run(conn, run_id, "failed", inserted, {"error": str(exc)})
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()
    print(json.dumps(ingest(args.path, args.db), indent=2))


if __name__ == "__main__":
    main()
