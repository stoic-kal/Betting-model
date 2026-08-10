import pickle
from pathlib import Path

import pandas as pd
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier


class AdvancedMLBBettingModel:

    def __init__(self):

        self.moneyline_model = XGBClassifier(
            n_estimators=200,
            max_depth=7,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=0,
        )

        self.totals_model = XGBClassifier(
            n_estimators=200,
            max_depth=7,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=0,
        )

        self.scaler = StandardScaler()
        self.feature_names = None

    def create_advanced_features(self, home_features, away_features):

        feature_row = {
            "home_win_pct_all": home_features.get("win_pct_all", 0.5),
            "home_win_pct_l3": home_features.get("win_pct_l3", 0.5),
            "home_win_pct_l7": home_features.get("win_pct_l7", 0.5),
            "home_runs_pg_all": home_features.get("runs_pg_all", 5.0),
            "home_runs_pg_l3": home_features.get("runs_pg_l3", 5.0),
            "home_runs_pg_l7": home_features.get("runs_pg_l7", 5.0),
            "home_consistency": home_features.get("consistency", 0.33),
            "home_trend": home_features.get("trend", 0.0),
            "home_streak": home_features.get("current_streak", 0),
            "away_win_pct_all": away_features.get("win_pct_all", 0.5),
            "away_win_pct_l3": away_features.get("win_pct_l3", 0.5),
            "away_win_pct_l7": away_features.get("win_pct_l7", 0.5),
            "away_runs_pg_all": away_features.get("runs_pg_all", 5.0),
            "away_runs_pg_l3": away_features.get("runs_pg_l3", 5.0),
            "away_runs_pg_l7": away_features.get("runs_pg_l7", 5.0),
            "away_consistency": away_features.get("consistency", 0.33),
            "away_trend": away_features.get("trend", 0.0),
            "away_streak": away_features.get("current_streak", 0),
            "runs_diff_all": home_features.get("runs_pg_all", 5.0)
            - away_features.get("runs_pg_all", 5.0),
            "runs_diff_l7": home_features.get("runs_pg_l7", 5.0)
            - away_features.get("runs_pg_l7", 5.0),
            "consistency_diff": home_features.get("consistency", 0.33)
            - away_features.get("consistency", 0.33),
            "total_expected_runs": home_features.get("runs_pg_all", 5.0)
            + away_features.get("runs_pg_all", 5.0),
        }

        return feature_row

    def predict_moneyline(self, home_features, away_features):

        feature_row = self.create_advanced_features(home_features, away_features)
        feature_df = pd.DataFrame([feature_row])
        feature_scaled = self.scaler.transform(feature_df)

        prob = self.moneyline_model.predict_proba(feature_scaled)[0][1]
        return float(prob)

    def predict_totals(self, home_features, away_features):

        feature_row = self.create_advanced_features(home_features, away_features)
        feature_df = pd.DataFrame([feature_row])
        feature_scaled = self.scaler.transform(feature_df)

        prob = self.totals_model.predict_proba(feature_scaled)[0][1]
        return float(prob)

    def save(self, path="models/advanced_model.pkl"):

        Path("models").mkdir(exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)
        print(f"Advanced model saved: {path}")

    @staticmethod
    def load(path="models/advanced_model.pkl"):

        with open(path, "rb") as f:
            return pickle.load(f)
