import pandas as pd
import numpy as np
import pickle
from scipy.stats import poisson

print("⏳ Creating totals predictor...\n")


with open("models/poisson_home_runs.pkl", "rb") as f:
    model_home = pickle.load(f)

with open("models/poisson_away_runs.pkl", "rb") as f:
    model_away = pickle.load(f)


X = pd.read_csv("data/X_totals.csv")
y_total = pd.read_csv("data/y_total_runs.csv")["total_runs"].values

print(f"Generating totals predictions...\n")


y_home_pred = model_home.predict(X)
y_away_pred = model_away.predict(X)
y_total_pred = y_home_pred + y_away_pred


lines = [8.0, 8.5, 9.0, 9.5]
results = []

for line in lines:

    over_probs = 1.0 - poisson.cdf(int(line), y_total_pred)

    over_correct = ((y_total > line) == (over_probs > 0.5)).mean()

    results.append({"line": line, "accuracy": over_correct, "avg_over_prob": over_probs.mean()})

    print(f"Line {line}:")
    print(f"   Accuracy: {over_correct:.1%}")
    print(f"   Avg OVER prob: {over_probs.mean():.1%}")

print(f"\nTotals predictor ready!")
print(f"\nSummary:")
print(f"   Predicted total runs avg: {y_total_pred.mean():.2f}")
print(f"   Actual total runs avg: {y_total.mean():.2f}")
