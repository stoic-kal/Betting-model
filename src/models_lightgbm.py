import pickle

import lightgbm as lgb
import numpy as np
from scipy.stats import poisson
from sklearn.preprocessing import StandardScaler


class LightGBMMoneylineModel:

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = None

    def train(self, X_train, y_train, feature_names):

        self.feature_names = feature_names

        X_scaled = self.scaler.fit_transform(X_train)

        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "verbose": -1,
        }

        train_data = lgb.Dataset(X_scaled, label=y_train)
        self.model = lgb.train(params, train_data, num_boost_round=500)

        print(f"LightGBM trained on {len(X_train)} samples")
        return self

    def predict_proba(self, X):

        X_scaled = self.scaler.transform(X)
        probs = self.model.predict(X_scaled)
        return np.clip(probs, 0.001, 0.999)

    def save(self, path):

        with open(path, "wb") as f:
            pickle.dump(
                {"model": self.model, "scaler": self.scaler, "features": self.feature_names}, f
            )

    def load(self, path):

        with open(path, "rb") as f:
            data = pickle.load(f)
            self.model = data["model"]
            self.scaler = data["scaler"]
            self.feature_names = data["features"]
        return self


class PoissonTotalsModel:

    def __init__(self):
        self.home_model = None
        self.away_model = None
        self.scaler = StandardScaler()
        self.feature_names = None

    def train(self, X_train, home_runs, away_runs, feature_names):

        self.feature_names = feature_names

        X_scaled = self.scaler.fit_transform(X_train)

        home_params = {
            "objective": "poisson",
            "metric": "poisson",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "verbose": -1,
        }

        home_data = lgb.Dataset(X_scaled, label=home_runs)
        self.home_model = lgb.train(home_params, home_data, num_boost_round=500)

        away_data = lgb.Dataset(X_scaled, label=away_runs)
        self.away_model = lgb.train(home_params, away_data, num_boost_round=500)

        print(f"Poisson models trained on {len(X_train)} samples")
        return self

    def predict_totals(self, X, line):

        X_scaled = self.scaler.transform(X)

        home_runs = self.home_model.predict(X_scaled)
        away_runs = self.away_model.predict(X_scaled)
        total_runs = home_runs + away_runs

        over_prob = 1.0 - poisson.cdf(int(line), total_runs)

        return np.clip(over_prob, 0.001, 0.999), total_runs

    def save(self, path):

        with open(path, "wb") as f:
            pickle.dump(
                {
                    "home_model": self.home_model,
                    "away_model": self.away_model,
                    "scaler": self.scaler,
                    "features": self.feature_names,
                },
                f,
            )

    def load(self, path):

        with open(path, "rb") as f:
            data = pickle.load(f)
            self.home_model = data["home_model"]
            self.away_model = data["away_model"]
            self.scaler = data["scaler"]
            self.feature_names = data["features"]
        return self


class EnsemblePredictor:

    def __init__(self, ml_model, totals_model):
        self.ml_model = ml_model
        self.totals_model = totals_model

    def predict_ml(self, X):

        return self.ml_model.predict_proba(X)

    def predict_totals(self, X, line):

        return self.totals_model.predict_totals(X, line)

    def save(self, ml_path, totals_path):

        self.ml_model.save(ml_path)
        self.totals_model.save(totals_path)

    def load(self, ml_path, totals_path):

        self.ml_model.load(ml_path)
        self.totals_model.load(totals_path)
        return self
