from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV


def build_model(spec, seed):
    params = dict(spec.parameters)
    family = spec.family
    if family == "extra_trees":
        model = ExtraTreesClassifier(random_state=seed, n_jobs=-1, **params)
    elif family == "random_forest":
        model = RandomForestClassifier(random_state=seed, n_jobs=-1, **params)
    elif family == "hist_gradient_boosting":
        model = HistGradientBoostingClassifier(random_state=seed, **params)
    elif family == "logistic_regression":
        model = Pipeline([("scale", StandardScaler()), ("classifier", LogisticRegression(max_iter=2000, random_state=seed, **params))])
    else:
        raise ValueError(f"Unsupported research model family: {family}")
    return Pipeline([("impute", SimpleImputer(strategy="median")), ("model", model)])


def fit_model(spec, seed, X, y):
    model=build_model(spec,seed)
    if not spec.calibration:
        return model.fit(X,y)
    if spec.calibration not in {"sigmoid","isotonic"}:
        raise ValueError(f"Unsupported research calibration: {spec.calibration}")
    split=max(1,int(len(X)*.8))
    if split>=len(X) or y.iloc[:split].nunique()<2 or y.iloc[split:].nunique()<2:
        raise ValueError("Insufficient chronological data for calibration holdout")
    model.fit(X.iloc[:split],y.iloc[:split])
    calibrated=CalibratedClassifierCV(model,method=spec.calibration,cv="prefit")
    calibrated.fit(X.iloc[split:],y.iloc[split:])
    calibrated._replay_base_model=model
    return calibrated


def feature_importance(model, features):
    if hasattr(model,"_replay_base_model"):
        model=model._replay_base_model
    fitted = model.named_steps["model"]
    if hasattr(fitted, "feature_importances_"):
        values = fitted.feature_importances_
    elif hasattr(fitted, "named_steps") and hasattr(fitted.named_steps.get("classifier"), "coef_"):
        values = abs(fitted.named_steps["classifier"].coef_[0])
    else:
        return {}
    return {name: float(value) for name, value in sorted(zip(features, values), key=lambda x: -x[1])}
