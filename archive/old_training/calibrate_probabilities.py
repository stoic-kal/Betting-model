import pandas as pd
import numpy as np
import pickle
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

print("⏳ Loading model and training data...\n")

with open("models/lightgbm_90pct_model.pkl", "rb") as f:
    model = pickle.load(f)

X_train = pd.read_csv("data/X_train.csv")
y_train = pd.read_csv("data/y_train.csv")["home_win"].values

print(f"Training Platt scaling calibration...\n")


y_pred_proba = model.predict(X_train)


calibrator = LogisticRegression()
calibrator.fit(y_pred_proba.reshape(-1, 1), y_train)


y_calibrated = calibrator.predict_proba(y_pred_proba.reshape(-1, 1))[:, 1]


brier_before = brier_score_loss(y_train, y_pred_proba)
brier_after = brier_score_loss(y_train, y_calibrated)

print(f"Calibration Results:")
print(f"   Brier Score Before: {brier_before:.4f}")
print(f"   Brier Score After: {brier_after:.4f}")
print(f"   Improvement: {(brier_before - brier_after):.4f}")


with open("models/calibrator.pkl", "wb") as f:
    pickle.dump(calibrator, f)

print(f"\nCalibrator saved to models/calibrator.pkl")


print(f"\nSample calibration:")
for raw_prob in [0.55, 0.60, 0.65, 0.70, 0.75]:
    cal_prob = calibrator.predict_proba([[raw_prob]])[0, 1]
    print(f"   Raw {raw_prob:.2f} → Calibrated {cal_prob:.2f}")
