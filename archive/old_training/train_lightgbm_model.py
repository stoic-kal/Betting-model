import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import accuracy_score, roc_auc_score
import pickle

print("⏳ Loading data...\n")

X_train = pd.read_csv("data/X_train.csv")
y_train = pd.read_csv("data/y_train.csv")["home_win"].values

print(f"Training set: {X_train.shape[0]} games, {X_train.shape[1]} features")
print(f"Win rate: {y_train.mean():.1%}")

print(f"\nTraining LightGBM model...\n")


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


train_data = lgb.Dataset(X_train, label=y_train)
model = lgb.train(params, train_data, num_boost_round=300)


y_pred_proba = model.predict(X_train)
y_pred = (y_pred_proba > 0.5).astype(int)

accuracy = accuracy_score(y_train, y_pred)
auc = roc_auc_score(y_train, y_pred_proba)

print(f"Training Results:")
print(f"   Accuracy: {accuracy:.1%}")
print(f"   AUC: {auc:.3f}")


with open("models/lightgbm_90pct_model.pkl", "wb") as f:
    pickle.dump(model, f)

print(f"\nModel saved to models/lightgbm_90pct_model.pkl")
