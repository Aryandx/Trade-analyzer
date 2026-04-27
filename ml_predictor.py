"""
ML inference layer.
Loads the trained LightGBM + XGBoost ensemble and returns a probability
score (0–1) for any stock given its df_ind + signals + scoring context.

Designed to be imported by stock_scorer.py with zero latency impact:
  - Models are loaded once into module-level cache on first call.
  - Falls back gracefully (returns 0.5 = neutral) if models not found.
"""

import os
import pickle
import json
import numpy as np
from typing import Optional

from config import RESULTS_DIR
from ml_feature_extractor import extract_features, N_FEATURES

MODEL_DIR  = os.path.join(RESULTS_DIR, "models")
LGBM_PATH  = os.path.join(MODEL_DIR, "lgbm_model.pkl")
XGB_PATH   = os.path.join(MODEL_DIR, "xgb_model.pkl")
STATS_PATH = os.path.join(MODEL_DIR, "training_stats.json")

# Module-level model cache (loaded once per process)
_lgbm = None
_xgb  = None
_ready = False


def _load_models() -> bool:
    global _lgbm, _xgb, _ready
    if _ready:
        return True
    if not (os.path.exists(LGBM_PATH) and os.path.exists(XGB_PATH)):
        return False
    try:
        with open(LGBM_PATH, "rb") as f:
            _lgbm = pickle.load(f)
        with open(XGB_PATH, "rb") as f:
            _xgb = pickle.load(f)
        _ready = True
        return True
    except Exception:
        return False


def is_ready() -> bool:
    """True if trained models exist and can be loaded."""
    return _load_models()


def predict_proba(
    df_ind,
    signals: Optional[dict] = None,
    stats52: Optional[dict] = None,
    regime_str: str = "SIDEWAYS",
    vix: float = 15.0,
    rule_score: Optional[float] = None,
) -> float:
    """
    Returns ensemble probability (0.0–1.0) that the stock will hit +3% in 10 days.
    Returns 0.5 (neutral) if models are not trained yet.
    """
    if not _load_models():
        return 0.5

    try:
        feat = extract_features(
            df_ind,
            signals=signals,
            stats52=stats52,
            regime_str=regime_str,
            vix=vix,
            rule_score=rule_score,
        ).reshape(1, -1)

        lgbm_p = float(_lgbm.predict_proba(feat)[0][1])
        xgb_p  = float(_xgb.predict_proba(feat)[0][1])

        # Weighted ensemble: LightGBM leads (typically better AUC on tabular data)
        return round(0.60 * lgbm_p + 0.40 * xgb_p, 4)

    except Exception:
        return 0.5


def ml_adjust_score(rule_score: float, ml_prob: float) -> int:
    """
    Blend rule-based score (0-150) with ML probability.
    ML can shift the score by up to ±20 points.
    At ml_prob=0.5 (neutral) → zero adjustment.
    At ml_prob=0.8 → +9 pts; at ml_prob=0.2 → -9 pts.
    At ml_prob=1.0 → +20 pts; at ml_prob=0.0 → -20 pts.
    """
    adjustment = (ml_prob - 0.5) * 40   # range: -20 to +20
    return int(np.clip(rule_score + adjustment, 0, 150))


def reload_models() -> None:
    """Force reload from disk (call after retraining)."""
    global _lgbm, _xgb, _ready
    _lgbm, _xgb, _ready = None, None, False
    _load_models()


def get_model_stats() -> dict:
    """Returns the last training stats dict, or {} if not trained."""
    if not os.path.exists(STATS_PATH):
        return {}
    try:
        with open(STATS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def get_feature_vector(
    df_ind,
    signals: Optional[dict] = None,
    stats52: Optional[dict] = None,
    regime_str: str = "SIDEWAYS",
    vix: float = 15.0,
    rule_score: Optional[float] = None,
) -> list:
    """
    Returns the raw 40-element feature vector as a plain Python list.
    Used by accuracy_tracker to save features alongside each prediction
    so future retraining can use them without re-extraction.
    """
    try:
        feat = extract_features(
            df_ind,
            signals=signals,
            stats52=stats52,
            regime_str=regime_str,
            vix=vix,
            rule_score=rule_score,
        )
        return feat.tolist()
    except Exception:
        return []
