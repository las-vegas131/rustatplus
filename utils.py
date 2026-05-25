import os
import pickle
import pandas as pd
from config import MATCH_SETTINGS_FILE

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
    except (ValueError, TypeError):
        return None

def load_settings(settings_file):
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'rb') as f:
                data = pickle.load(f)
            if data and isinstance(next(iter(data.values())), list):
                return {pos: {m: 1.0 for m in metrics} for pos, metrics in data.items()}
            return data
        except:
            pass
    return None

def save_settings(settings_dict, settings_file):
    with open(settings_file, 'wb') as f:
        pickle.dump(settings_dict, f)

def load_selected_metrics(metrics_file):
    if os.path.exists(metrics_file):
        try:
            with open(metrics_file, 'rb') as f:
                return pickle.load(f)
        except:
            pass
    return None

def save_selected_metrics(metrics, metrics_file):
    with open(metrics_file, 'wb') as f:
        pickle.dump(metrics, f)

def load_match_selected_metrics():
    from config import MATCH_SELECTED_METRICS_FILE
    if os.path.exists(MATCH_SELECTED_METRICS_FILE):
        try:
            with open(MATCH_SELECTED_METRICS_FILE, 'rb') as f:
                return pickle.load(f)
        except:
            pass
    return None

def save_match_selected_metrics(metrics):
    from config import MATCH_SELECTED_METRICS_FILE
    with open(MATCH_SELECTED_METRICS_FILE, 'wb') as f:
        pickle.dump(metrics, f)

def load_match_settings():
    if os.path.exists(MATCH_SETTINGS_FILE):
        try:
            with open(MATCH_SETTINGS_FILE, 'rb') as f:
                return pickle.load(f)
        except:
            pass
    return None

def save_match_settings(settings_dict):
    with open(MATCH_SETTINGS_FILE, 'wb') as f:
        pickle.dump(settings_dict, f)
