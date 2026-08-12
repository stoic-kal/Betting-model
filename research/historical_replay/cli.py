import argparse
import json
from pathlib import Path

from .config import ModelSpec, ReplayConfig
from .engine import run_replay


def main():
    parser=argparse.ArgumentParser(description="Isolated historical replay research engine")
    parser.add_argument("--config",required=True)
    args=parser.parse_args(); raw=json.loads(Path(args.config).read_text())
    raw["historical_baseline"]=ModelSpec(**raw.get("historical_baseline",{})); raw["candidate"]=ModelSpec(**raw.get("candidate",{}))
    path=run_replay(ReplayConfig(**raw)); print(json.dumps({"status":"complete","run_dir":str(path)},indent=2))


if __name__=="__main__": main()
