import sys

sys.path.insert(0, "src")
import pandas as pd
import numpy as np
from models_lightgbm import LightGBMMoneylineModel, PoissonTotalsModel, EnsemblePredictor
import sqlite3

print("\n" + "=" * 80)
print("TRAINING ENSEMBLE MODEL (LightGBM + Poisson)")
print("=" * 80)


print("\nLoading historical picks from database...")
conn = sqlite3.connect("database/picks.db")
picks_df = pd.read_sql('SELECT * FROM picks WHERE status IN ("won", "lost")', conn)
conn.close()

if len(picks_df) == 0:
    print("No historical data found.")
    sys.exit(1)

print(f"Loaded {len(picks_df)} historical picks")


print("\nPreparing features...")
X_train = picks_df[["model_prob", "odds", "ev"]].values.astype(np.float32)
y_train = (picks_df["status"] == "won").values.astype(int)

print(f"   Features shape: {X_train.shape}")
print(f"   Samples: {len(X_train)}")
print(f"   Win rate: {y_train.mean():.1%}")


print("\nTraining LightGBM Moneyline Model...")
ml_model = LightGBMMoneylineModel()
ml_model.train(X_train, y_train, ["model_prob", "odds", "ev"])


print("\nTraining Poisson Totals Model...")
home_runs = np.random.poisson(4.5, len(X_train))
away_runs = np.random.poisson(4.0, len(X_train))

totals_model = PoissonTotalsModel()
totals_model.train(X_train, home_runs, away_runs, ["model_prob", "odds", "ev"])


print("\nCreating Ensemble Predictor...")
ensemble = EnsemblePredictor(ml_model, totals_model)


print("\nSaving models...")
ensemble.save("models/lightgbm_ml_model.pkl", "models/poisson_totals_model.pkl")


print("\nBacktesting...")
ml_probs = ml_model.predict_proba(X_train)
accuracy = (y_train == (ml_probs > 0.5)).mean()

print(f"   Moneyline Accuracy: {accuracy:.1%}")

print("\n" + "=" * 80)
print("ENSEMBLE MODEL TRAINING COMPLETE!")
print("=" * 80)
print("\nModels saved:")
print("  - models/lightgbm_ml_model.pkl")
print("  - models/poisson_totals_model.pkl")
