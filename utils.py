import os
import pickle
import pandas as pd
import numpy as np
from config import SETTINGS_FILE, SELECTED_METRICS_FILE

def safe_int(val):
    if pd.isna(val) or val is None:
        return 0
    try:
        return int(float(val))
    except:
        return 0

def frac(total, accuracy_pct):
    t = safe_int(total)
    if t == 0:
        return ''
    acc = safe_int(accuracy_pct) if not pd.isna(accuracy_pct) else 0
    succ = int(round(t * acc / 100))
    return f"{t}/{succ}"

def clean_value(v):
    if pd.isna(v) or str(v).strip() in ('', '-'):
        return None
    try:
        return float(v)
    except:
        return None

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'rb') as f:
                data = pickle.load(f)
            if data and isinstance(next(iter(data.values())), list):
                return {pos: {m: 1.0 for m in metrics} for pos, metrics in data.items()}
            return data
        except:
            pass
    from config import DEFAULT_METRICS_WEIGHTS
    return {pos: weights.copy() for pos, weights in DEFAULT_METRICS_WEIGHTS.items()}

def save_settings(settings_dict):
    with open(SETTINGS_FILE, 'wb') as f:
        pickle.dump(settings_dict, f)

def load_selected_metrics():
    if os.path.exists(SELECTED_METRICS_FILE):
        try:
            with open(SELECTED_METRICS_FILE, 'rb') as f:
                return pickle.load(f)
        except:
            pass
    return None

def save_selected_metrics(metrics):
    with open(SELECTED_METRICS_FILE, 'wb') as f:
        pickle.dump(metrics, f)
