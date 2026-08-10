import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import mean_poisson_deviance, mean_absolute_error
import pickle

print("⏳ Training Poisson regression models...\n")

X = pd.read_csv("data/X_totals.csv")
y_home = pd.read_csv("data/y_home_runs.csv")["home_runs"].values
y_away = pd.read_csv("data/y_away_runs.csv")["away_runs"].values

print(f"Data loaded:")
print(f"   X: {X.shape}")
print(f"   Home runs mean: {y_home.mean():.2f}")
print(f"   Away runs mean: {y_away.mean():.2f}")


params = {
    "objective": "poisson",
    "metric": "poisson",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "verbose": -1,
}

print(f"\nTraining HOME runs model...\n")

train_home = lgb.Dataset(X, label=y_home)
model_home = lgb.train(params, train_home, num_boost_round=300)

y_home_pred = model_home.predict(X)
mae_home = mean_absolute_error(y_home, y_home_pred)

print(f"HOME model results:")
print(f"   MAE: {mae_home:.3f}")
print(f"   Predicted avg: {y_home_pred.mean():.2f}")
print(f"   Actual avg: {y_home.mean():.2f}")

print(f"\nTraining AWAY runs model...\n")

train_away = lgb.Dataset(X, label=y_away)
model_away = lgb.train(params, train_away, num_boost_round=300)

y_away_pred = model_away.predict(X)
mae_away = mean_absolute_error(y_away, y_away_pred)

print(f"AWAY model results:")
print(f"   MAE: {mae_away:.3f}")
print(f"   Predicted avg: {y_away_pred.mean():.2f}")
print(f"   Actual avg: {y_away.mean():.2f}")


with open("models/poisson_home_runs.pkl", "wb") as f:
    pickle.dump(model_home, f)

with open("models/poisson_away_runs.pkl", "wb") as f:
    pickle.dump(model_away, f)

print(f"\nModels saved:")
print(f"   - models/poisson_home_runs.pkl")
print(f"   - models/poisson_away_runs.pkl")
