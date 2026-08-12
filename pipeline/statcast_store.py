import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.features_common import (
    FIP_CONSTANT,
    LEAGUE_AVG_BAT_ISO,
    LEAGUE_AVG_BAT_WOBA,
    LEAGUE_AVG_BB_RATE,
    LEAGUE_AVG_FIP,
    LEAGUE_AVG_HARD_HIT_PCT,
    LEAGUE_AVG_HR_RATE,
    LEAGUE_AVG_K_RATE,
)

STATCAST_PATH = "data/statcast_raw.csv"
DERIVED_DIR = Path("data/statcast_derived")
PITCHER_GAME_LOG = DERIVED_DIR / "pitcher_game_log.csv"
TEAM_BULLPEN_DAILY = DERIVED_DIR / "team_bullpen_daily.csv"
BATTER_PLATOON_GAME = DERIVED_DIR / "batter_platoon_game.csv"
BATTER_PITCHGROUP_GAME = DERIVED_DIR / "batter_pitchgroup_game.csv"
PITCHER_PITCHGROUP_GAME = DERIVED_DIR / "pitcher_pitchgroup_game.csv"
LINEUP_GAME = DERIVED_DIR / "lineup_game.csv"
BATTER_STAND = DERIVED_DIR / "batter_stand.csv"
LEAGUE_CONSTANTS = DERIVED_DIR / "league_constants.json"
GAME_INDEX = DERIVED_DIR / "game_index.csv"

CHUNK_SIZE = 200000
EXCLUDED_GAME_TYPES = {"S", "E"}

HIT_EVENTS = {"single", "double", "triple", "home_run"}
WALK_EVENTS = {"walk", "intent_walk"}
STRIKEOUT_EVENTS = {"strikeout", "strikeout_double_play"}
FLYBALL_TYPES = {"fly_ball", "popup"}

PITCH_GROUPS = {
    "FF": "fastball", "SI": "fastball", "FC": "fastball", "FA": "fastball",
    "SL": "breaking", "ST": "breaking", "SV": "breaking", "CU": "breaking",
    "KC": "breaking", "CS": "breaking", "SC": "breaking", "KN": "breaking",
    "CH": "offspeed", "FS": "offspeed", "FO": "offspeed",
}
PITCH_GROUP_NAMES = ("fastball", "breaking", "offspeed")

HARD_HIT_MPH = 95.0
CLOSE_GAME_MARGIN = 2
LINEUP_SIZE = 9

MIN_BULLPEN_IP = 3.0
MIN_BULLPEN_BF = 15
MIN_PLATOON_PA = 25
MIN_PITCHGROUP_PA = 15
MIN_STARTER_BIP = 30
MIN_STARTER_STARTS = 3

_TERMINAL_COLUMNS = [
    "game_pk", "game_date", "game_type", "home_team", "away_team", "inning", "inning_topbot",
    "at_bat_number", "pitcher", "batter", "p_throws", "stand", "events", "bb_type", "launch_speed",
    "woba_value", "woba_denom", "iso_value", "outs_when_up", "bat_score", "post_bat_score",
    "fld_score", "pitch_type",
]

_ALL_ROW_COLUMNS = ["game_pk", "game_date", "game_type", "inning_topbot", "home_team", "away_team", "pitcher", "pitch_type"]


def _pitch_group(series):
    return series.map(PITCH_GROUPS)


def _pitching_team(frame):
    return np.where(frame["inning_topbot"] == "Top", frame["home_team"], frame["away_team"])


def _batting_team(frame):
    return np.where(frame["inning_topbot"] == "Top", frame["away_team"], frame["home_team"])


def _stream_source():
    usecols = sorted(set(_TERMINAL_COLUMNS) | set(_ALL_ROW_COLUMNS))
    for chunk in pd.read_csv(STATCAST_PATH, usecols=usecols, chunksize=CHUNK_SIZE, low_memory=False):
        yield chunk[~chunk["game_type"].isin(EXCLUDED_GAME_TYPES)]


def _outs_recorded(terminal):
    terminal = terminal.sort_values(["game_pk", "inning", "inning_topbot", "at_bat_number"]).reset_index(drop=True)
    half = terminal.groupby(["game_pk", "inning", "inning_topbot"])
    next_outs = half["outs_when_up"].shift(-1)
    outs_end = next_outs.fillna(3.0)
    recorded = (outs_end - terminal["outs_when_up"]).clip(lower=0.0, upper=3.0)
    terminal["outs_recorded"] = recorded.astype(float)
    return terminal


_GAME_INDEX_COLUMNS = [
    "game_pk", "game_date", "game_type", "home_team", "away_team",
    "inning_topbot", "at_bat_number", "pitcher", "player_name",
]


def build_game_index(force=False):
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    if not force and GAME_INDEX.exists():
        return GAME_INDEX
    parts = []
    for chunk in pd.read_csv(STATCAST_PATH, usecols=_GAME_INDEX_COLUMNS, chunksize=CHUNK_SIZE, low_memory=False):
        chunk = chunk.dropna(subset=["game_pk", "at_bat_number", "inning_topbot"])
        idx = chunk.groupby(["game_pk", "inning_topbot"])["at_bat_number"].idxmin()
        parts.append(chunk.loc[idx])
    frame = pd.concat(parts, ignore_index=True)
    idx = frame.groupby(["game_pk", "inning_topbot"])["at_bat_number"].idxmin()
    frame = frame.loc[idx]
    frame["game_pk"] = frame["game_pk"].astype(int)
    meta = frame.groupby("game_pk").agg(
        game_date=("game_date", "first"),
        game_type=("game_type", "first"),
        home_team=("home_team", "first"),
        away_team=("away_team", "first"),
    )
    home = frame[frame["inning_topbot"] == "Top"].set_index("game_pk")["player_name"].rename("home_sp_name")
    away = frame[frame["inning_topbot"] == "Bot"].set_index("game_pk")["player_name"].rename("away_sp_name")
    index = meta.join(home).join(away).reset_index()
    index = index.sort_values(["game_date", "game_pk"]).reset_index(drop=True)
    index.to_csv(GAME_INDEX, index=False)
    return GAME_INDEX


def load_game_index():
    build_game_index()
    return pd.read_csv(GAME_INDEX, dtype={"game_date": str})


def build_derived_tables(force=False):
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    outputs = [
        PITCHER_GAME_LOG, TEAM_BULLPEN_DAILY, BATTER_PLATOON_GAME,
        BATTER_PITCHGROUP_GAME, PITCHER_PITCHGROUP_GAME, LINEUP_GAME, BATTER_STAND, LEAGUE_CONSTANTS,
    ]
    if not force and all(p.exists() for p in outputs):
        return

    terminal_parts = []
    pitch_count_parts = []
    pitcher_group_parts = []
    for chunk in _stream_source():
        pitch_counts = chunk.groupby(["game_pk", "pitcher"], observed=True).size().rename("pitches").reset_index()
        pitch_count_parts.append(pitch_counts)

        grouped = chunk.assign(pitch_group=_pitch_group(chunk["pitch_type"]))
        grouped = grouped[grouped["pitch_group"].notna()]
        pitcher_group_parts.append(
            grouped.groupby(["game_pk", "pitcher", "pitch_group"], observed=True).size().rename("pitches").reset_index()
        )

        terminal_parts.append(chunk.loc[chunk["events"].notna(), _TERMINAL_COLUMNS].copy())

    terminal = pd.concat(terminal_parts, ignore_index=True)
    del terminal_parts
    terminal["game_date"] = pd.to_datetime(terminal["game_date"])
    terminal = _outs_recorded(terminal)

    terminal["pitch_team"] = _pitching_team(terminal)
    terminal["bat_team"] = _batting_team(terminal)
    terminal["runs_allowed"] = (terminal["post_bat_score"] - terminal["bat_score"]).clip(lower=0.0)
    terminal["is_close"] = (terminal["bat_score"] - terminal["fld_score"]).abs() <= CLOSE_GAME_MARGIN
    terminal["is_k"] = terminal["events"].isin(STRIKEOUT_EVENTS)
    terminal["is_bb"] = terminal["events"].isin(WALK_EVENTS)
    terminal["is_hbp"] = terminal["events"] == "hit_by_pitch"
    terminal["is_hr"] = terminal["events"] == "home_run"
    terminal["is_hit"] = terminal["events"].isin(HIT_EVENTS)
    terminal["is_fb"] = terminal["bb_type"].isin(FLYBALL_TYPES)
    terminal["is_bip"] = terminal["bb_type"].notna()
    terminal["is_hard"] = terminal["launch_speed"] >= HARD_HIT_MPH
    terminal["pitch_group"] = _pitch_group(terminal["pitch_type"])

    pitcher_log = terminal.groupby(["game_pk", "pitcher"], observed=True).agg(
        game_date=("game_date", "first"),
        team=("pitch_team", "first"),
        first_ab=("at_bat_number", "min"),
        bf=("events", "size"),
        k=("is_k", "sum"),
        bb=("is_bb", "sum"),
        hbp=("is_hbp", "sum"),
        hr=("is_hr", "sum"),
        hits=("is_hit", "sum"),
        fb=("is_fb", "sum"),
        bip=("is_bip", "sum"),
        outs=("outs_recorded", "sum"),
        runs=("runs_allowed", "sum"),
    ).reset_index()

    close_outs = (
        terminal[terminal["is_close"]]
        .groupby(["game_pk", "pitcher"], observed=True)["outs_recorded"].sum().rename("close_outs").reset_index()
    )
    pitcher_log = pitcher_log.merge(close_outs, on=["game_pk", "pitcher"], how="left")
    pitcher_log["close_outs"] = pitcher_log["close_outs"].fillna(0.0)

    pitch_counts = pd.concat(pitch_count_parts, ignore_index=True).groupby(["game_pk", "pitcher"], as_index=False)["pitches"].sum()
    del pitch_count_parts
    pitcher_log = pitcher_log.merge(pitch_counts, on=["game_pk", "pitcher"], how="left")
    pitcher_log["pitches"] = pitcher_log["pitches"].fillna(0.0)

    starter_ab = pitcher_log.groupby(["game_pk", "team"], observed=True)["first_ab"].transform("min")
    pitcher_log["is_starter"] = pitcher_log["first_ab"] == starter_ab
    pitcher_log = pitcher_log.drop(columns=["first_ab"])
    pitcher_log.to_csv(PITCHER_GAME_LOG, index=False)

    relievers = pitcher_log[~pitcher_log["is_starter"]]
    bullpen_daily = relievers.groupby(["team", "game_date"], observed=True).agg(
        appearances=("pitcher", "size"),
        pitches=("pitches", "sum"),
        bf=("bf", "sum"),
        k=("k", "sum"),
        bb=("bb", "sum"),
        hbp=("hbp", "sum"),
        hr=("hr", "sum"),
        hits=("hits", "sum"),
        fb=("fb", "sum"),
        outs=("outs", "sum"),
        runs=("runs", "sum"),
        close_outs=("close_outs", "sum"),
    ).reset_index()
    bullpen_daily.to_csv(TEAM_BULLPEN_DAILY, index=False)

    platoon = terminal.groupby(["batter", "p_throws", "game_pk"], observed=True).agg(
        game_date=("game_date", "first"),
        woba_sum=("woba_value", "sum"),
        woba_denom=("woba_denom", "sum"),
        iso_sum=("iso_value", "sum"),
        iso_n=("iso_value", "count"),
        pa=("events", "size"),
        k=("is_k", "sum"),
        bb=("is_bb", "sum"),
        hard=("is_hard", "sum"),
        bip=("is_bip", "sum"),
    ).reset_index()
    platoon.to_csv(BATTER_PLATOON_GAME, index=False)

    grouped_terminal = terminal[terminal["pitch_group"].notna()]
    batter_group = grouped_terminal.groupby(["batter", "pitch_group", "game_pk"], observed=True).agg(
        game_date=("game_date", "first"),
        woba_sum=("woba_value", "sum"),
        woba_denom=("woba_denom", "sum"),
        pa=("events", "size"),
    ).reset_index()
    batter_group.to_csv(BATTER_PITCHGROUP_GAME, index=False)

    pitcher_group = pd.concat(pitcher_group_parts, ignore_index=True).groupby(
        ["game_pk", "pitcher", "pitch_group"], as_index=False
    )["pitches"].sum()
    del pitcher_group_parts
    game_dates = terminal.groupby("game_pk", observed=True)["game_date"].first().rename("game_date").reset_index()
    pitcher_group = pitcher_group.merge(game_dates, on="game_pk", how="left")
    pitcher_group = pitcher_group[pitcher_group["game_date"].notna()]
    pitcher_group.to_csv(PITCHER_PITCHGROUP_GAME, index=False)

    lineup = (
        terminal.sort_values("at_bat_number")
        .groupby(["game_pk", "bat_team", "batter"], observed=True)
        .agg(game_date=("game_date", "first"), first_ab=("at_bat_number", "min"))
        .reset_index()
        .sort_values(["game_pk", "bat_team", "first_ab"])
    )
    lineup["batting_order"] = lineup.groupby(["game_pk", "bat_team"], observed=True).cumcount() + 1
    lineup = lineup[lineup["batting_order"] <= LINEUP_SIZE].drop(columns=["first_ab"])
    lineup = lineup.rename(columns={"bat_team": "team"})
    lineup.to_csv(LINEUP_GAME, index=False)

    stand_counts = terminal.groupby(["batter", "stand"], observed=True).size().rename("pa").reset_index()
    stand_counts = stand_counts.sort_values("pa", ascending=False).drop_duplicates("batter")
    stand_counts.rename(columns={"stand": "primary_stand"}).to_csv(BATTER_STAND, index=False)

    league_hr = float(terminal["is_hr"].sum())
    league_fb = float(terminal["is_fb"].sum())
    constants = {
        "league_hr_fb_rate": league_hr / league_fb if league_fb > 0 else None,
        "league_hr_count": league_hr,
        "league_fb_count": league_fb,
        "source": "data/statcast_raw.csv batted-ball outcomes (bb_type in fly_ball/popup)",
        "date_min": str(terminal["game_date"].min().date()),
        "date_max": str(terminal["game_date"].max().date()),
    }
    with open(LEAGUE_CONSTANTS, "w") as f:
        json.dump(constants, f, indent=2)


class _WindowIndex:
    def __init__(self, frame, key_columns, date_column, value_columns):
        self.value_columns = list(value_columns)
        self._keys = {}
        key_columns = list(key_columns)
        single_key = len(key_columns) == 1
        frame = frame.sort_values(key_columns + [date_column])
        for key, group in frame.groupby(key_columns, observed=True, sort=False):
            if single_key and isinstance(key, tuple):
                key = key[0]
            dates = group[date_column].values.astype("datetime64[D]").astype(np.int64)
            values = group[self.value_columns].to_numpy(dtype=np.float64)
            cumulative = np.vstack([np.zeros((1, values.shape[1])), np.cumsum(values, axis=0)])
            self._keys[key] = (dates, cumulative)

    def sum(self, key, as_of_day, days=None):
        entry = self._keys.get(key)
        if entry is None:
            return None
        dates, cumulative = entry
        high = int(np.searchsorted(dates, as_of_day, side="left"))
        low = 0 if days is None else int(np.searchsorted(dates, as_of_day - days, side="left"))
        if high <= low:
            return None
        totals = cumulative[high] - cumulative[low]
        return dict(zip(self.value_columns, totals))


def _to_day(value):
    return int(pd.Timestamp(value).to_datetime64().astype("datetime64[D]").astype(np.int64))


class StatcastContext:
    def __init__(self):
        build_derived_tables()
        with open(LEAGUE_CONSTANTS) as f:
            self.league_constants = json.load(f)

        bullpen = pd.read_csv(TEAM_BULLPEN_DAILY, parse_dates=["game_date"])
        self._bullpen = _WindowIndex(
            bullpen, ["team"], "game_date",
            ["appearances", "pitches", "bf", "k", "bb", "hbp", "hr", "hits", "fb", "outs", "runs", "close_outs"],
        )

        platoon = pd.read_csv(BATTER_PLATOON_GAME, parse_dates=["game_date"])
        self._platoon = _WindowIndex(
            platoon, ["batter", "p_throws"], "game_date",
            ["woba_sum", "woba_denom", "iso_sum", "iso_n", "pa", "k", "bb", "hard", "bip"],
        )
        platoon_all = platoon.groupby(["batter", "game_pk"], as_index=False).agg(
            game_date=("game_date", "first"),
            woba_sum=("woba_sum", "sum"),
            woba_denom=("woba_denom", "sum"),
            iso_sum=("iso_sum", "sum"),
            iso_n=("iso_n", "sum"),
            pa=("pa", "sum"),
            k=("k", "sum"),
            bb=("bb", "sum"),
            hard=("hard", "sum"),
            bip=("bip", "sum"),
        )
        self._platoon_all = _WindowIndex(
            platoon_all, ["batter"], "game_date",
            ["woba_sum", "woba_denom", "iso_sum", "iso_n", "pa", "k", "bb", "hard", "bip"],
        )

        batter_group = pd.read_csv(BATTER_PITCHGROUP_GAME, parse_dates=["game_date"])
        self._batter_group = _WindowIndex(
            batter_group, ["batter", "pitch_group"], "game_date", ["woba_sum", "woba_denom", "pa"],
        )

        pitcher_group = pd.read_csv(PITCHER_PITCHGROUP_GAME, parse_dates=["game_date"])
        self._pitcher_group = _WindowIndex(
            pitcher_group, ["pitcher", "pitch_group"], "game_date", ["pitches"],
        )

        pitcher_log = pd.read_csv(PITCHER_GAME_LOG, parse_dates=["game_date"])
        starters = pitcher_log[pitcher_log["is_starter"]]
        self._starter = _WindowIndex(
            starters, ["pitcher"], "game_date", ["fb", "bip", "outs", "bf"],
        )
        self._starts = _WindowIndex(
            starters.assign(starts=1.0), ["pitcher"], "game_date", ["starts", "outs"],
        )

        stand = pd.read_csv(BATTER_STAND)
        self._batter_stand = dict(zip(stand["batter"].astype(int), stand["primary_stand"]))

        lineup = pd.read_csv(LINEUP_GAME, parse_dates=["game_date"])
        self._lineup = {
            key: group.sort_values("batting_order")["batter"].astype(int).tolist()
            for key, group in lineup.groupby(["game_pk", "team"], observed=True)
        }

    def lineup_lr_balance(self, batter_ids):
        stands = [self._batter_stand.get(int(b)) for b in batter_ids]
        stands = [s for s in stands if s in ("L", "R")]
        if not stands:
            return None
        return round(sum(1 for s in stands if s == "L") / len(stands), 4)

    def league_hr_fb_rate(self):
        return self.league_constants.get("league_hr_fb_rate")

    def lineup_for_game(self, game_pk, team_abbr):
        return self._lineup.get((int(game_pk), team_abbr), [])

    def bullpen_fatigue(self, team_abbr, as_of, windows=(3, 5, 7)):
        day = _to_day(as_of)
        out = {}
        for w in windows:
            totals = self._bullpen.sum(team_abbr, day, days=w)
            if totals is None:
                return None
            out[f"bullpen_appearances_{w}d"] = float(totals["appearances"])
            out[f"bullpen_pitches_{w}d"] = float(totals["pitches"])
            out[f"bullpen_bf_{w}d"] = float(totals["bf"])
            out[f"bullpen_high_lev_ip_{w}d"] = round(float(totals["close_outs"]) / 3.0, 4)
        return out

    def bullpen_quality(self, team_abbr, as_of, windows=(7, 14, 30, None)):
        day = _to_day(as_of)
        hr_fb = self.league_hr_fb_rate()
        out = {}
        for w in windows:
            label = "season" if w is None else f"{w}d"
            totals = self._bullpen.sum(team_abbr, day, days=w)
            if totals is None:
                continue
            ip = float(totals["outs"]) / 3.0
            bf = float(totals["bf"])
            if ip < MIN_BULLPEN_IP or bf < MIN_BULLPEN_BF:
                continue
            walks = float(totals["bb"])
            hbp = float(totals["hbp"])
            k = float(totals["k"])
            hr = float(totals["hr"])
            fb = float(totals["fb"])
            out[f"bullpen_era_{label}"] = round(float(totals["runs"]) * 9.0 / ip, 4)
            out[f"bullpen_fip_{label}"] = round((13.0 * hr + 3.0 * (walks + hbp) - 2.0 * k) / ip + FIP_CONSTANT, 4)
            out[f"bullpen_whip_{label}"] = round((float(totals["hits"]) + walks) / ip, 4)
            out[f"bullpen_k_rate_{label}"] = round(k / bf, 4)
            out[f"bullpen_bb_rate_{label}"] = round(walks / bf, 4)
            out[f"bullpen_hr_rate_{label}"] = round(hr / bf, 4)
            if hr_fb is not None:
                out[f"bullpen_xfip_{label}"] = round(
                    (13.0 * (fb * hr_fb) + 3.0 * (walks + hbp) - 2.0 * k) / ip + FIP_CONSTANT, 4
                )
        return out

    def _batter_platoon_rates(self, batter_id, hand, day):
        totals = self._platoon.sum((batter_id, hand), day)
        if totals is None or totals["pa"] < MIN_PLATOON_PA:
            totals = self._platoon_all.sum(batter_id, day)
        if totals is None or totals["pa"] < MIN_PLATOON_PA:
            return None
        pa = float(totals["pa"])
        woba_denom = float(totals["woba_denom"])
        iso_n = float(totals["iso_n"])
        bip = float(totals["bip"])
        return {
            "woba": float(totals["woba_sum"]) / woba_denom if woba_denom > 0 else LEAGUE_AVG_BAT_WOBA,
            "iso": float(totals["iso_sum"]) / iso_n if iso_n > 0 else LEAGUE_AVG_BAT_ISO,
            "k_rate": float(totals["k"]) / pa,
            "bb_rate": float(totals["bb"]) / pa,
            "hard_hit": float(totals["hard"]) / bip if bip > 0 else LEAGUE_AVG_HARD_HIT_PCT,
        }

    def lineup_platoon_splits(self, batter_ids, opposing_hand, as_of):
        if not batter_ids or opposing_hand not in ("L", "R"):
            return None
        day = _to_day(as_of)
        rows = [self._batter_platoon_rates(int(b), opposing_hand, day) for b in batter_ids]
        rows = [r for r in rows if r is not None]
        if not rows:
            return None
        frame = pd.DataFrame(rows)
        means = frame.mean()
        woba = float(means["woba"])
        strength = min(1.0, max(0.0, 0.5 + (woba - LEAGUE_AVG_BAT_WOBA) * 4.0))
        overall = [self._batter_platoon_rates(int(b), None, day) for b in batter_ids]
        overall = [r for r in overall if r is not None]
        baseline = float(pd.DataFrame(overall)["woba"].mean()) if overall else LEAGUE_AVG_BAT_WOBA
        advantage = (woba - baseline) / baseline if baseline > 0 else 0.0
        return {
            "lineup_woba_vs_pitcher_hand": round(woba, 4),
            "lineup_iso_vs_pitcher_hand": round(float(means["iso"]), 4),
            "lineup_k_rate_vs_pitcher_hand": round(float(means["k_rate"]), 4),
            "lineup_bb_rate_vs_pitcher_hand": round(float(means["bb_rate"]), 4),
            "lineup_hard_hit_vs_pitcher_hand": round(float(means["hard_hit"]), 4),
            "lineup_strength_vs_pitcher_hand": round(strength, 4),
            "platoon_advantage_score": round(min(1.0, max(-1.0, advantage)), 4),
            "batters_matched": len(rows),
        }

    def starter_fb_rate(self, pitcher_id, as_of):
        totals = self._starter.sum(int(pitcher_id), _to_day(as_of))
        if totals is None or totals["bip"] < MIN_STARTER_BIP:
            return None
        return float(totals["fb"]) / float(totals["bip"])

    def starter_avg_innings(self, pitcher_id, as_of):
        totals = self._starts.sum(int(pitcher_id), _to_day(as_of))
        if totals is None or totals["starts"] < MIN_STARTER_STARTS:
            return None
        return float(totals["outs"]) / 3.0 / float(totals["starts"])

    def pitch_mix_lineup_matchup(self, pitcher_id, batter_ids, as_of):
        if not batter_ids:
            return None
        day = _to_day(as_of)
        usage = {}
        for group in PITCH_GROUP_NAMES:
            totals = self._pitcher_group.sum((int(pitcher_id), group), day)
            usage[group] = float(totals["pitches"]) if totals else 0.0
        total_pitches = sum(usage.values())
        if total_pitches <= 0:
            return None
        score = 0.0
        weight_used = 0.0
        for group in PITCH_GROUP_NAMES:
            share = usage[group] / total_pitches
            if share <= 0:
                continue
            woba_sum = 0.0
            denom = 0.0
            for batter in batter_ids:
                totals = self._batter_group.sum((int(batter), group), day)
                if totals is None or totals["pa"] < MIN_PITCHGROUP_PA:
                    continue
                woba_sum += float(totals["woba_sum"])
                denom += float(totals["woba_denom"])
            if denom <= 0:
                continue
            score += share * (woba_sum / denom - LEAGUE_AVG_BAT_WOBA)
            weight_used += share
        if weight_used <= 0:
            return None
        return round(min(1.0, max(-1.0, score / weight_used)), 4)


_CONTEXT = None


def get_context():
    global _CONTEXT
    if _CONTEXT is None:
        _CONTEXT = StatcastContext()
    return _CONTEXT


def league_average_platoon_fallbacks():
    return {
        "lineup_woba_vs_pitcher_hand": LEAGUE_AVG_BAT_WOBA,
        "lineup_iso_vs_pitcher_hand": LEAGUE_AVG_BAT_ISO,
        "lineup_k_rate_vs_pitcher_hand": LEAGUE_AVG_K_RATE,
        "lineup_bb_rate_vs_pitcher_hand": LEAGUE_AVG_BB_RATE,
        "lineup_hard_hit_vs_pitcher_hand": LEAGUE_AVG_HARD_HIT_PCT,
    }


def league_average_bullpen_fallbacks():
    return {
        "era": LEAGUE_AVG_FIP,
        "fip": LEAGUE_AVG_FIP,
        "xfip": LEAGUE_AVG_FIP,
        "k_rate": LEAGUE_AVG_K_RATE,
        "bb_rate": LEAGUE_AVG_BB_RATE,
        "hr_rate": LEAGUE_AVG_HR_RATE,
    }


if __name__ == "__main__":
    build_derived_tables(force=True)
    with open(LEAGUE_CONSTANTS) as f:
        print(json.dumps(json.load(f), indent=2))
