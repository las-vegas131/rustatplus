import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import io
import os
import pickle
from pathlib import Path
import warnings
import psycopg2
from dotenv import load_dotenv

# -------------------- ПРОВЕРКА ПОДКЛЮЧЕНИЯ К БД --------------------
def check_db_connection():
    required_vars = ["SUPABASE_HOST", "SUPABASE_PORT", "SUPABASE_DBNAME", 
                     "SUPABASE_USER", "SUPABASE_PASSWORD"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        st.error(f"❌ Отсутствуют переменные окружения: {', '.join(missing)}. "
                 f"Добавьте их в файл `.env`.")
        st.stop()
    try:
        conn = psycopg2.connect(
            host=os.getenv("SUPABASE_HOST"),
            port=os.getenv("SUPABASE_PORT"),
            dbname=os.getenv("SUPABASE_DBNAME"),
            user=os.getenv("SUPABASE_USER"),
            password=os.getenv("SUPABASE_PASSWORD"),
        )
        conn.close()
    except Exception as e:
        st.error(f"❌ Не удалось подключиться к базе данных: {e}")
        st.stop()

warnings.filterwarnings('ignore')
load_dotenv()
check_db_connection()  


# -------------------- ГЛОБАЛЬНЫЕ КОНСТАНТЫ --------------------
MIN_MINUTES = 90
TOP_N_FOR_PLOTS = 8
SETTINGS_FILE = os.path.expanduser('~/InStatAnalyst_settings.pkl')

ALL_POSSIBLE_METRICS = [
    'goals_p90', 'assists_p90', 'shots_p90', 'shots_on_target_p90',
    'key_passes_p90', 'dribbles_p90', 'dribbles_success_pct',
    'tackles_p90', 'tackles_success_pct', 'interceptions_p90',
    'pass_accuracy', 'passes_p90', 'crosses_p90', 'crosses_accuracy',
    'xG_p90', 'challenges_p90', 'challenges_won_pct',
    'air_challenges_p90', 'air_challenges_won_pct',
    'fouls_suffered_p90', 'progressive_passes_p90',
    'progressive_passes_accuracy', 'passes_final_third_p90',
    'passes_final_third_accuracy', 'chances_p90',
    'chances_successful_p90', 'involvement_scoring_p90',
    'actions_opp_box_p90', 'actions_opp_box_success_p90',
    'final_third_entries_p90', 'final_third_carry_p90',
    'ball_recoveries_p90', 'ball_recoveries_opp_half_p90',
    'loose_ball_recoveries_p90', 'actions_successful_p90',
    'lost_balls_p90', 'lost_balls_own_half_p90',
    'individual_ball_losses_p90', 'yellow_cards_p90',
    'red_cards_p90', 'mistakes_goals_p90', 'mistakes_chances_p90',
    'fouls_p90', 'actions_unsuccessful_p90',
]

DEFAULT_METRICS_WEIGHTS = {
    'FW': {
        'goals_p90': 3.0, 'xG_p90': 2.5, 'shots_on_target_p90': 2.0,
        'assists_p90': 1.5, 'dribbles_p90': 1.2, 'actions_opp_box_p90': 1.2,
        'chances_successful_p90': 1.0, 'key_passes_p90': 1.0, 'pass_accuracy': 0.5,
        'lost_balls_p90': -2.0, 'individual_ball_losses_p90': -1.5,
        'yellow_cards_p90': -0.5, 'red_cards_p90': -3.0, 'mistakes_goals_p90': -2.5,
        'mistakes_chances_p90': -1.0, 'fouls_p90': -0.5,
    },
    'AM': {
        'key_passes_p90': 3.0, 'assists_p90': 2.5, 'progressive_passes_p90': 2.0,
        'pass_accuracy': 1.5, 'dribbles_p90': 1.5, 'goals_p90': 1.0,
        'xG_p90': 1.0, 'shots_on_target_p90': 1.0, 'chances_p90': 1.0,
        'lost_balls_p90': -1.5, 'individual_ball_losses_p90': -1.0,
        'yellow_cards_p90': -0.5, 'red_cards_p90': -3.0, 'mistakes_goals_p90': -1.5,
        'mistakes_chances_p90': -1.0, 'fouls_p90': -0.5,
    },
    'CM': {
        'pass_accuracy': 3.0, 'progressive_passes_p90': 2.5, 'interceptions_p90': 2.0,
        'tackles_p90': 1.5, 'key_passes_p90': 1.5, 'progressive_passes_accuracy': 1.5,
        'challenges_won_pct': 1.0, 'ball_recoveries_p90': 1.0,
        'lost_balls_own_half_p90': -2.0, 'lost_balls_p90': -1.5,
        'individual_ball_losses_p90': -1.0, 'yellow_cards_p90': -1.0,
        'red_cards_p90': -3.0, 'mistakes_goals_p90': -2.0, 'mistakes_chances_p90': -1.5,
        'fouls_p90': -0.5,
    },
    'FB': {
        'tackles_p90': 2.5, 'interceptions_p90': 2.0, 'crosses_accuracy': 2.0,
        'pass_accuracy': 1.5, 'tackles_success_pct': 1.5, 'dribbles_p90': 1.2,
        'key_passes_p90': 1.2, 'progressive_passes_p90': 1.0,
        'mistakes_goals_p90': -2.5, 'mistakes_chances_p90': -1.5,
        'lost_balls_own_half_p90': -2.0, 'lost_balls_p90': -1.0,
        'yellow_cards_p90': -1.0, 'red_cards_p90': -3.0, 'fouls_p90': -0.5,
    },
    'CB': {
        'interceptions_p90': 3.0, 'tackles_p90': 2.5, 'air_challenges_won_pct': 2.5,
        'tackles_success_pct': 2.0, 'challenges_won_pct': 1.5, 'ball_recoveries_p90': 1.5,
        'loose_ball_recoveries_p90': 1.5, 'pass_accuracy': 1.0,
        'mistakes_goals_p90': -3.0, 'mistakes_chances_p90': -2.0,
        'lost_balls_own_half_p90': -2.5, 'individual_ball_losses_p90': -1.5,
        'yellow_cards_p90': -1.0, 'red_cards_p90': -3.5, 'fouls_p90': -1.0,
    },
}

NEGATIVE_METRICS = [
    'lost_balls_p90', 'lost_balls_own_half_p90', 'individual_ball_losses_p90',
    'yellow_cards_p90', 'red_cards_p90', 'mistakes_goals_p90', 'mistakes_chances_p90',
    'fouls_p90', 'actions_unsuccessful_p90',
]

METRIC_NAMES_RU = {
    'goals_p90': 'Голы', 'assists_p90': 'Голевые передачи', 'shots_p90': 'Удары',
    'shots_on_target_p90': 'Удары в створ', 'key_passes_p90': 'Ключевые передачи',
    'dribbles_p90': 'Обводки', 'dribbles_success_pct': 'Обводки успешные %',
    'tackles_p90': 'Отборы', 'tackles_success_pct': 'Отборы успешные %',
    'interceptions_p90': 'Перехваты', 'pass_accuracy': 'Точность передач %',
    'passes_p90': 'Передачи', 'crosses_p90': 'Кроссы', 'crosses_accuracy': 'Кроссы точные %',
    'xG_p90': 'xG (ожидаемые голы)', 'challenges_p90': 'Единоборства',
    'challenges_won_pct': 'Единоборства выигранные %',
    'air_challenges_p90': 'Верховые единоборства', 'air_challenges_won_pct': 'Верховые единоборства %',
    'fouls_suffered_p90': 'Фолы на игроке', 'progressive_passes_p90': 'Продвигающие передачи',
    'progressive_passes_accuracy': 'Продвигающие передачи точные %',
    'passes_final_third_p90': 'Передачи в финальную треть',
    'passes_final_third_accuracy': 'Передачи в финальную треть %',
    'chances_p90': 'Голевые моменты', 'chances_successful_p90': 'Реализованные моменты',
    'involvement_scoring_p90': 'Участие в голевых атаках',
    'actions_opp_box_p90': 'Действия в штрафной соперника',
    'actions_opp_box_success_p90': 'Успешные действия в штрафной',
    'final_third_entries_p90': 'Входы в финальную треть',
    'final_third_carry_p90': 'Входы в финальную треть (дриблинг)',
    'ball_recoveries_p90': 'Возвраты мяча', 'ball_recoveries_opp_half_p90': 'Возвраты мяча на чужой половине',
    'loose_ball_recoveries_p90': 'Подборы', 'actions_successful_p90': 'Успешные действия',
    'lost_balls_p90': 'Потери мяча', 'lost_balls_own_half_p90': 'Потери на своей половине',
    'individual_ball_losses_p90': 'Индивидуальные потери', 'yellow_cards_p90': 'Жёлтые карточки',
    'red_cards_p90': 'Красные карточки', 'mistakes_goals_p90': 'Ошибки, приведшие к голам',
    'mistakes_chances_p90': 'Ошибки, приведшие к моментам', 'fouls_p90': 'Фолы',
    'actions_unsuccessful_p90': 'Неуспешные действия',
}

# -------------------- ПАРАМЕТРЫ ПОДКЛЮЧЕНИЯ К БД --------------------
def get_db_config():
    return {
        "host": os.getenv("SUPABASE_HOST"),
        "port": os.getenv("SUPABASE_PORT"),
        "dbname": os.getenv("SUPABASE_DBNAME"),
        "user": os.getenv("SUPABASE_USER"),
        "password": os.getenv("SUPABASE_PASSWORD"),
    }

# -------------------- ФУНКЦИИ АНАЛИЗА --------------------
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
    return {pos: weights.copy() for pos, weights in DEFAULT_METRICS_WEIGHTS.items()}

def save_settings(settings_dict):
    with open(SETTINGS_FILE, 'wb') as f:
        pickle.dump(settings_dict, f)

@st.cache_data
def load_and_clean_data(uploaded_file_content):
    try:
        df = pd.read_excel(io.BytesIO(uploaded_file_content), sheet_name='Main statistics', header=0)
    except ValueError:
        xls = pd.ExcelFile(io.BytesIO(uploaded_file_content))
        first_sheet = xls.sheet_names[0]
        df = pd.read_excel(io.BytesIO(uploaded_file_content), sheet_name=first_sheet, header=0)
    df = df.dropna(subset=['№'])

    rename_dict = {
        'Player': 'player', 'Position': 'position', 'Minutes played': 'minutes',
        'Goals': 'goals', 'Assists': 'assists', 'Shots': 'shots',
        'Shots on target': 'shots_on_target', 'Key passes': 'key_passes',
        'Dribbles': 'dribbles', 'Dribbles successful, %': 'dribbles_success_pct',
        'Tackles': 'tackles', 'Tackles successful, %': 'tackles_success_pct',
        'Interceptions': 'interceptions', 'Passes accurate, %': 'pass_accuracy',
        'Passes': 'passes', 'Crosses': 'crosses', 'Crosses accurate, %': 'crosses_accuracy',
        'xG (expected goals)': 'xG', 'Challenges': 'challenges',
        'Challenges won, %': 'challenges_won_pct', 'Air challenges': 'air_challenges',
        'Air challenges won, %': 'air_challenges_won_pct', 'Fouls': 'fouls',
        'Fouls suffered': 'fouls_suffered', 'Yellow cards': 'yellow_cards',
        'Red cards': 'red_cards', 'Loose ball recoveries': 'loose_ball_recoveries',
        'Actions in opponent\'s box': 'actions_opp_box',
        'Actions in opponent\'s box successful': 'actions_opp_box_success',
        'Chances': 'chances', 'Chances successful': 'chances_successful',
        'Involvement in scoring attacks': 'involvement_scoring',
        'Progressive passes': 'progressive_passes',
        'Progressive passes accurate, %': 'progressive_passes_accuracy',
        'Passes forward to the final third': 'passes_final_third',
        'Passes forward to the final third accurate, %': 'passes_final_third_accuracy',
        'Final third entries': 'final_third_entries',
        'Final third entries through carry': 'final_third_carry',
        'Lost balls': 'lost_balls', 'Lost balls in own half': 'lost_balls_own_half',
        'Individual ball losses': 'individual_ball_losses',
        'Ball recoveries': 'ball_recoveries',
        'Ball recoveries in opponent\'s half': 'ball_recoveries_opp_half',
        'Matches played': 'matches_played', 'Starting lineup appearances': 'starting_lineup',
        'Mistakes leading to goals': 'mistakes_goals',
        'Mistakes leading to chances': 'mistakes_chances',
        'Actions': 'actions', 'Actions successful': 'actions_successful',
        'Actions unsuccessful': 'actions_unsuccessful',
    }
    existing_renames = {k: v for k, v in rename_dict.items() if k in df.columns}
    df = df.rename(columns=existing_renames)

    pct_columns = ['pass_accuracy', 'dribbles_success_pct', 'tackles_success_pct',
                   'crosses_accuracy', 'challenges_won_pct', 'air_challenges_won_pct',
                   'progressive_passes_accuracy', 'passes_final_third_accuracy']
    for col in pct_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if df[col].max() <= 1.0:
                df[col] = df[col] * 100

    minutes = pd.to_numeric(df['minutes'], errors='coerce').fillna(0)
    stats_to_normalize = [
        'goals', 'assists', 'shots', 'shots_on_target', 'key_passes',
        'dribbles', 'tackles', 'interceptions', 'challenges',
        'air_challenges', 'crosses', 'progressive_passes', 'passes_final_third',
        'chances', 'chances_successful', 'involvement_scoring',
        'actions_opp_box', 'actions_opp_box_success',
        'final_third_entries', 'final_third_carry',
        'lost_balls', 'lost_balls_own_half', 'individual_ball_losses',
        'ball_recoveries', 'ball_recoveries_opp_half',
        'loose_ball_recoveries', 'fouls', 'fouls_suffered',
        'yellow_cards', 'red_cards', 'mistakes_goals', 'mistakes_chances',
        'actions', 'actions_successful', 'actions_unsuccessful',
        'passes', 'xG'
    ]
    for col in stats_to_normalize:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            df[f'{col}_p90'] = np.where(minutes > 0, (df[col] / minutes) * 90, 0)

    if 'position' in df.columns:
        df = df[~df['position'].str.upper().str.contains('GK', na=False)]
    return df

def get_position_group(pos):
    if not isinstance(pos, str):
        return 'CM'
    pos = pos.upper().strip()
    if pos in ['CF', 'FW', 'ST']: return 'FW'
    if pos in ['CAM', 'LAM', 'RAM', 'AM']: return 'AM'
    if pos in ['CDM', 'LCDM', 'RCDM', 'CM']: return 'CM'
    if pos in ['LD', 'RD', 'LWB', 'RWB']: return 'FB'
    if pos in ['CD', 'LCD', 'RCD', 'CB']: return 'CB'
    return 'CM'

def minmax_normalize(series):
    s = series.fillna(0)
    min_val, max_val = s.min(), s.max()
    if max_val - min_val == 0:
        return pd.Series(0.5, index=s.index)
    return (s - min_val) / (max_val - min_val)

@st.cache_data
def calculate_ratings(df, position_weights):
    all_used = set()
    for pos_weights in position_weights.values():
        for m, w in pos_weights.items():
            if w != 0:
                all_used.add(m)
    valid_metrics = [m for m in all_used if m in df.columns]
    if not valid_metrics:
        df['rating'] = 50.0
        return df
    norm_cols = {}
    for m in valid_metrics:
        df[f'{m}_norm'] = minmax_normalize(df[m])
        norm_cols[m] = f'{m}_norm'

    def calc_row(row):
        pos = get_position_group(row.get('position', ''))
        weights = position_weights.get(pos, {})
        if not weights:
            return 50.0
        pos_sum = 0.0
        pos_weight_sum = 0.0
        neg_sum = 0.0
        neg_weight_sum = 0.0
        for m, w in weights.items():
            if w == 0 or m not in valid_metrics:
                continue
            col = norm_cols.get(m)
            if col and pd.notna(row[col]):
                if m in NEGATIVE_METRICS:
                    neg_sum += (1.0 - row[col]) * abs(w)
                    neg_weight_sum += abs(w)
                else:
                    pos_sum += row[col] * w
                    pos_weight_sum += w
        pos_score = pos_sum / pos_weight_sum if pos_weight_sum > 0 else 0.5
        neg_score = neg_sum / neg_weight_sum if neg_weight_sum > 0 else 0.5
        rating = 100 * (pos_score + neg_score) / 2
        return rating

    df['rating'] = df.apply(calc_row, axis=1).round(1)
    return df

def format_metric_with_detail(metric, value, player_row):
    if metric.endswith('_pct') or metric == 'pass_accuracy':
        base_col = None
        if metric == 'pass_accuracy': base_col = 'passes'
        elif metric == 'dribbles_success_pct': base_col = 'dribbles'
        elif metric == 'tackles_success_pct': base_col = 'tackles'
        elif metric == 'challenges_won_pct': base_col = 'challenges'
        elif metric == 'air_challenges_won_pct': base_col = 'air_challenges'
        elif metric == 'crosses_accuracy': base_col = 'crosses'
        elif metric == 'progressive_passes_accuracy': base_col = 'progressive_passes'
        elif metric == 'passes_final_third_accuracy': base_col = 'passes_final_third'
        if base_col and base_col in player_row:
            total = player_row[base_col]
            if pd.notna(total) and total > 0:
                successful = int(round(total * value / 100))
                return f"{value:.1f}% ({successful}/{int(total)})"
        return f"{value:.1f}%"
    else:
        return f"{value:.2f}"

def build_position_tables(df, position_weights):
    tables = {}
    positions = ['FW', 'AM', 'CM', 'FB', 'CB']
    for pos in positions:
        pos_df = df[df['position'].map(get_position_group) == pos].copy()
        if pos_df.empty:
            tables[pos] = ([], [])
            continue
        metrics = [m for m, w in position_weights.get(pos, {}).items() if w != 0 and m in df.columns]
        if not metrics:
            tables[pos] = ([], [])
            continue

        for m in metrics:
            col = pos_df[m]
            min_val, max_val = col.min(), col.max()
            if max_val - min_val == 0:
                pos_df[f'{m}_norm_pos'] = 0.5
            else:
                pos_df[f'{m}_norm_pos'] = (col - min_val) / (max_val - min_val)
            if m in NEGATIVE_METRICS:
                pos_df[f'{m}_norm_pos'] = 1.0 - pos_df[f'{m}_norm_pos']

        max_vals = {m: pos_df[f'{m}_norm_pos'].max() for m in metrics}
        min_vals = {m: pos_df[f'{m}_norm_pos'].min() for m in metrics}

        rows = []
        for _, player_row in pos_df.iterrows():
            row_data = [player_row['player'], int(player_row['minutes']), f"{player_row['rating']:.1f}"]
            for m in metrics:
                val = player_row[m]
                formatted = format_metric_with_detail(m, val, player_row)
                norm_val = player_row[f'{m}_norm_pos']
                is_max = (norm_val == max_vals[m])
                is_min = (norm_val == min_vals[m])
                if is_max and not is_min:
                    formatted = f"🟢 {formatted}"
                elif is_min and not is_max:
                    formatted = f"🔴 {formatted}"
                row_data.append(formatted)
            rows.append(row_data)

        headers = ['Игрок', 'Мин', 'Рейтинг'] + [METRIC_NAMES_RU.get(m, m) for m in metrics]
        tables[pos] = (rows, headers)
    return tables

def build_main_table(df, selected_metrics):
    metrics = [m for m in selected_metrics if m in df.columns]
    if not metrics:
        return pd.DataFrame(columns=['№','Игрок','Поз','Мин','Рейтинг'])

    norm_cols = {}
    for m in metrics:
        col = df[m]
        min_val, max_val = col.min(), col.max()
        if max_val - min_val == 0:
            norm_cols[m] = pd.Series(0.5, index=df.index)
        else:
            norm_cols[m] = (col - min_val) / (max_val - min_val)
        if m in NEGATIVE_METRICS:
            norm_cols[m] = 1.0 - norm_cols[m]

    max_vals = {m: norm_cols[m].max() for m in metrics}
    min_vals = {m: norm_cols[m].min() for m in metrics}

    main_headers = ['№','Игрок','Поз','Мин','Рейтинг'] + [METRIC_NAMES_RU.get(m, m) for m in metrics]
    main_data = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        row_data = [i, row['player'], row['position'], int(row['minutes']), f"{row['rating']:.1f}"]
        for m in metrics:
            val = row[m]
            detail = format_metric_with_detail(m, val, row)
            norm_val = norm_cols[m].loc[row.name]
            is_max = (norm_val == max_vals[m])
            is_min = (norm_val == min_vals[m])
            if is_max and not is_min:
                detail = f"🟢 {detail}"
            elif is_min and not is_max:
                detail = f"🔴 {detail}"
            row_data.append(detail)
        main_data.append(row_data)
    return pd.DataFrame(main_data, columns=main_headers)

# -------------------- ВИЗУАЛИЗАЦИЯ --------------------
def plot_radar_on_axis(ax, player_row, team_avg, radar_metrics, df, title=None, color='blue', show_legend=True):
    labels = []
    for m in radar_metrics:
        name = METRIC_NAMES_RU.get(m, m)
        val = player_row[m]
        if m.endswith('_pct') or m == 'pass_accuracy':
            detail = format_metric_with_detail(m, val, player_row)
            labels.append(f"{name}\n{detail}")
        else:
            labels.append(f"{name}\n{val:.2f}")

    player_vals = []
    for m in radar_metrics:
        max_val = df[m].max()
        min_val = df[m].min()
        if max_val - min_val == 0:
            player_norm = 0.5
        else:
            player_norm = (player_row[m] - min_val) / (max_val - min_val)
        if m in NEGATIVE_METRICS:
            player_norm = 1.0 - player_norm
        player_vals.append(player_norm)

    angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]
    player_vals += player_vals[:1]

    ax.fill(angles, player_vals, alpha=0.25, color=color)
    ax.plot(angles, player_vals, color=color, linewidth=2, label=player_row['player'])
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=6)
    ax.set_ylim(0, 1)
    if show_legend:
        ax.legend(loc='upper right', fontsize=6, bbox_to_anchor=(1.3, 1.1))

def create_player_radar_figure(player_row, df, position_weights):
    pos = get_position_group(player_row['position'])
    weights = position_weights.get(pos, {})
    sorted_metrics = sorted(weights.items(), key=lambda x: -abs(x[1]))
    radar_metrics = [m for m, _ in sorted_metrics if m in df.columns][:8]
    if not radar_metrics:
        radar_metrics = [c for c in df.columns if c.endswith('_p90') or c.endswith('_pct')][:8]
    team_avg = {m: df[m].mean() for m in radar_metrics}
    fig, ax = plt.subplots(figsize=(4, 4), subplot_kw=dict(polar=True))
    plot_radar_on_axis(ax, player_row, team_avg, radar_metrics, df, show_legend=False)
    plt.tight_layout(pad=0.2)
    return fig

def create_compare_figure(p1, p2, radar_metrics, df):
    fig, ax = plt.subplots(figsize=(4, 4), subplot_kw=dict(polar=True))
    labels = [METRIC_NAMES_RU.get(m, m) for m in radar_metrics]
    vals1, vals2 = [], []
    for m in radar_metrics:
        max_v, min_v = df[m].max(), df[m].min()
        if max_v - min_v == 0:
            v1 = v2 = 0.5
        else:
            v1 = (p1[m] - min_v) / (max_v - min_v)
            v2 = (p2[m] - min_v) / (max_v - min_v)
        if m in NEGATIVE_METRICS:
            v1, v2 = 1 - v1, 1 - v2
        vals1.append(v1)
        vals2.append(v2)
    angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]
    vals1 += vals1[:1]
    vals2 += vals2[:1]
    ax.fill(angles, vals1, alpha=0.2, color='blue')
    ax.plot(angles, vals1, color='blue', linewidth=2, label=f'{p1["player"]} ({p1["rating"]:.1f})')
    ax.fill(angles, vals2, alpha=0.2, color='red')
    ax.plot(angles, vals2, color='red', linewidth=2, label=f'{p2["player"]} ({p2["rating"]:.1f})')
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=6)
    ax.set_ylim(0,1)
    ax.set_title('Сравнение лидеров', fontsize=10, weight='bold')
    ax.legend(loc='upper right', fontsize=6, bbox_to_anchor=(1.3, 1.1))
    plt.tight_layout()
    return fig

def create_position_radar(selected_players, df, pos_metrics, colors):
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    for i, player_name in enumerate(selected_players):
        player_row = df[df['player'] == player_name].iloc[0]
        color = colors[i % len(colors)]
        plot_radar_on_axis(ax, player_row, None, pos_metrics[:8], df, color=color, show_legend=False)

    label_colors = []
    for m in pos_metrics[:8]:
        name = METRIC_NAMES_RU.get(m, m)
        value_lines = []
        for i, player_name in enumerate(selected_players):
            player_row = df[df['player'] == player_name].iloc[0]
            val = player_row[m]
            if m.endswith('_pct') or m == 'pass_accuracy':
                detail = format_metric_with_detail(m, val, player_row)
            else:
                detail = f"{val:.2f}"
            value_lines.append(f"{player_name}: {detail}")
        label_colors.append(f"{name}\n" + "\n".join(value_lines))

    for i, m in enumerate(pos_metrics[:8]):
        angle = 2*np.pi * i / len(pos_metrics[:8])
        ax.text(angle, 1.35, label_colors[i], 
                ha='center', va='center', fontsize=6, transform=ax.transData)

    ax.set_xticks([])
    ax.set_ylim(0, 1)

    from matplotlib.lines import Line2D
    legend_elements = [Line2D([0], [0], color=colors[i % len(colors)], lw=2, label=name) 
                       for i, name in enumerate(selected_players)]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=6, bbox_to_anchor=(1.3, 1.1))

    return fig

# -------------------- ЗАГРУЗКА ИЗ БД --------------------
def load_from_db(league_name, season, teams=None):
    conn = psycopg2.connect(**get_db_config())
    query = """
    SELECT 
        p.name AS player, p.position,
        ps.minutes_played AS minutes,
        ps.goals, ps.assists, ps.shots, ps.shots_on_target,
        ps.key_passes, ps.dribbles, ps.dribbles_success_pct,
        ps.tackles, ps.tackles_success_pct, ps.interceptions,
        ps.pass_accuracy, ps.passes, ps.crosses, ps.crosses_accuracy,
        ps.xG, ps.challenges, ps.challenges_won_pct,
        ps.air_challenges, ps.air_challenges_won_pct,
        ps.fouls_suffered, ps.progressive_passes,
        ps.progressive_passes_accuracy, ps.passes_final_third,
        ps.passes_final_third_accuracy, ps.chances,
        ps.chances_successful, ps.involvement_scoring,
        ps.actions_opp_box, ps.actions_opp_box_success,
        ps.final_third_entries, ps.final_third_carry,
        ps.ball_recoveries, ps.ball_recoveries_opp_half,
        ps.loose_ball_recoveries, ps.actions_successful,
        ps.lost_balls, ps.lost_balls_own_half,
        ps.individual_ball_losses, ps.yellow_cards,
        ps.red_cards, ps.mistakes_goals, ps.mistakes_chances,
        ps.fouls, ps.actions_unsuccessful, ps.actions,
        ps.matches_played, ps.starting_lineup,
        t.name AS team
    FROM player_stats ps
    JOIN players p ON ps.player_id = p.id
    JOIN teams t ON ps.team_id = t.id
    JOIN leagues l ON t.league_id = l.id
    WHERE l.name = %s AND ps.season = %s
    """
    params = [league_name, season]
    if teams and len(teams) > 0:
        query += " AND t.name = ANY(%s)"
        params.append(teams)
    df = pd.read_sql(query, conn, params=params)
    conn.close()

    # Удаляем вратарей
    df = df[~df['position'].str.upper().str.contains('GK', na=False)]

    # Проценты
    pct_cols = ['pass_accuracy', 'dribbles_success_pct', 'tackles_success_pct',
                'crosses_accuracy', 'challenges_won_pct', 'air_challenges_won_pct',
                'progressive_passes_accuracy', 'passes_final_third_accuracy']
    for col in pct_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if df[col].max() <= 1.0:
                df[col] = df[col] * 100

    # Нормализация на 90 минут
    minutes = pd.to_numeric(df['minutes'], errors='coerce').fillna(0)
    stats_to_norm = [
        'goals', 'assists', 'shots', 'shots_on_target', 'key_passes',
        'dribbles', 'tackles', 'interceptions', 'challenges',
        'air_challenges', 'crosses', 'progressive_passes', 'passes_final_third',
        'chances', 'chances_successful', 'involvement_scoring',
        'actions_opp_box', 'actions_opp_box_success',
        'final_third_entries', 'final_third_carry',
        'lost_balls', 'lost_balls_own_half', 'individual_ball_losses',
        'ball_recoveries', 'ball_recoveries_opp_half',
        'loose_ball_recoveries', 'fouls', 'fouls_suffered',
        'yellow_cards', 'red_cards', 'mistakes_goals', 'mistakes_chances',
        'actions', 'actions_successful', 'actions_unsuccessful',
        'passes', 'xG'
    ]
    for col in stats_to_norm:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            df[f'{col}_p90'] = np.where(minutes > 0, (df[col] / minutes) * 90, 0)

    return df

# -------------------- ДИНАМИЧЕСКАЯ ЗАГРУЗКА ЛИГ, СЕЗОНОВ, КОМАНД --------------------
@st.cache_data(ttl=60)
def get_leagues():
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("SELECT name FROM leagues ORDER BY name")
        leagues = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return leagues
    except Exception as e:
        st.error(f"Не удалось подключиться к базе данных: {e}")
        return []

@st.cache_data(ttl=60)
def get_seasons(league_name):
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ps.season
            FROM player_stats ps
            JOIN teams t ON ps.team_id = t.id
            JOIN leagues l ON t.league_id = l.id
            WHERE l.name = %s
            ORDER BY ps.season
        """, (league_name,))
        seasons = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return seasons
    except Exception as e:
        return []

@st.cache_data(ttl=60)
def get_teams(league_name, season):
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT t.name
            FROM teams t
            JOIN player_stats ps ON t.id = ps.team_id
            JOIN leagues l ON t.league_id = l.id
            WHERE l.name = %s AND ps.season = %s
            ORDER BY t.name
        """, (league_name, season))
        teams = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return teams
    except Exception as e:
        return []

# -------------------- ИНТЕРФЕЙС STREAMLIT --------------------
st.set_page_config(page_title="InStat Analyst", layout="wide")
st.title("Анализ футболистов InStat")

if 'df_excel' not in st.session_state:
    st.session_state.df_excel = None
if 'df_db' not in st.session_state:
    st.session_state.df_db = None
if 'active_df_type' not in st.session_state:
    st.session_state.active_df_type = None  # 'excel' или 'db'
if 'position_tables_excel' not in st.session_state:
    st.session_state.position_tables_excel = {}
if 'position_tables_db' not in st.session_state:
    st.session_state.position_tables_db = {}
if 'current_settings' not in st.session_state:
    st.session_state.current_settings = load_settings()
if 'last_uploaded_name' not in st.session_state:
    st.session_state.last_uploaded_name = None
if 'selected_main_metrics' not in st.session_state:
    st.session_state.selected_main_metrics = []

# Боковая панель
with st.sidebar:
    st.header("📂 Источник данных")
    data_source = st.radio("Загрузка", ["Excel файл", "База данных (Supabase)"], horizontal=True)

    if data_source == "Excel файл":
        st.header("1. Загрузка данных")
        uploaded_file = st.file_uploader("Выберите Excel-файл", type="xlsx", key="file_uploader")
        if uploaded_file is not None:
            if uploaded_file.name != st.session_state.last_uploaded_name:
                with st.spinner("Анализируем файл..."):
                    df_raw = load_and_clean_data(uploaded_file.getvalue())
                    total = len(df_raw)
                    df_filtered = df_raw[df_raw['minutes'] >= MIN_MINUTES].copy()
                    excluded = total - len(df_filtered)
                    if len(df_filtered) == 0:
                        st.error("Нет игроков с достаточным временем.")
                    else:
                        df_filtered = calculate_ratings(df_filtered, st.session_state.current_settings)
                        df_filtered = df_filtered.sort_values('rating', ascending=False).reset_index(drop=True)
                        st.session_state.df_excel = df_filtered
                        st.session_state.position_tables_excel = build_position_tables(df_filtered, st.session_state.current_settings)
                        st.session_state.active_df_type = 'excel'
                        st.session_state.last_uploaded_name = uploaded_file.name
                        st.success(f"Загружено {len(df_filtered)} игроков (исключено {excluded} с менее чем {MIN_MINUTES} мин.)")

    else:  # База данных (Supabase)
        st.header("1. Выбор лиги, сезона и команд")
        leagues_list = get_leagues()
        if not leagues_list:
            st.warning("Нет доступных лиг в базе данных или ошибка подключения.")
            league = None
        else:
            league = st.selectbox("Лига", leagues_list, key="league_db")

        if league:
            seasons_list = get_seasons(league)
            if not seasons_list:
                st.warning(f"Для лиги '{league}' нет данных по сезонам.")
                season = None
            else:
                season = st.selectbox("Сезон", seasons_list, key="season_db")
        else:
            season = None

        if league and season:
            teams_list = get_teams(league, season)
            if teams_list:
                selected_teams = st.multiselect(
                "Команды (оставьте пустым – все)", teams_list, key="teams_db"
                )
            else:
                st.info("Нет команд для выбранной лиги и сезона.")
                selected_teams = []
        else:
            st.caption("Выберите лигу и сезон, чтобы появился фильтр по командам.")
            selected_teams = []

        if league and season:
            if st.button("Загрузить данные", use_container_width=True):
                with st.spinner("Запрос к Supabase..."):
                    try:
                        teams_param = None if len(selected_teams) == 0 else selected_teams
                        df_raw = load_from_db(league, season, teams_param)
                        total = len(df_raw)
                        df_filtered = df_raw[df_raw['minutes'] >= MIN_MINUTES].copy()
                        if len(df_filtered) == 0:
                            st.error("Нет игроков с достаточным игровым временем.")
                        else:
                            df_filtered = calculate_ratings(df_filtered, st.session_state.current_settings)
                            df_filtered = df_filtered.sort_values('rating', ascending=False).reset_index(drop=True)
                            st.session_state.df_db = df_filtered
                            st.session_state.position_tables_db = build_position_tables(df_filtered, st.session_state.current_settings)
                            st.session_state.active_df_type = 'db'
                            st.success(f"Загружено {len(df_filtered)} игроков (исключено {total - len(df_filtered)} с < {MIN_MINUTES} мин.)")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

    # Выбор активного источника для таблиц
    # Выбор активного источника для таблиц (безопасный)
    if st.session_state.df_excel is not None and st.session_state.df_db is not None:
    # Доступны оба источника – показываем radio
        active = st.radio("Показать данные", ["Excel", "База данных"],
                      index=0 if st.session_state.active_df_type == 'excel' else 1,
                      key="active_view_v2")
        st.session_state.active_df_type = 'excel' if active == "Excel" else 'db'
    elif st.session_state.df_excel is not None:
        st.session_state.active_df_type = 'excel'
        st.caption("Активные данные: Excel")
    elif st.session_state.df_db is not None:
        st.session_state.active_df_type = 'db'
        st.caption("Активные данные: База данных")
    else:
        st.session_state.active_df_type = None

    # Общие настройки весов
    st.header("3. Настройки весов")
    if st.button("Открыть редактор весов", use_container_width=True):
        st.session_state.show_weights_editor = True
    if st.button("Сбросить веса по умолчанию", use_container_width=True):
        st.session_state.current_settings = {pos: w.copy() for pos, w in DEFAULT_METRICS_WEIGHTS.items()}
        save_settings(st.session_state.current_settings)
        st.cache_data.clear()
        st.success("Веса сброшены.")
        # Пересчитать, если есть данные
        for attr in ['df_excel', 'df_db']:
            df = getattr(st.session_state, attr)
            if df is not None:
                setattr(st.session_state, attr, calculate_ratings(df, st.session_state.current_settings))
                if attr == 'df_excel':
                    st.session_state.position_tables_excel = build_position_tables(df, st.session_state.current_settings)
                else:
                    st.session_state.position_tables_db = build_position_tables(df, st.session_state.current_settings)

    # Визуализация (сравнение игроков) – доступна, если есть хотя бы один датафрейм
    if st.session_state.df_excel is not None or st.session_state.df_db is not None:
        st.header("4. Визуализация")

        # Формируем общий список игроков с метками источника
        all_players = []
        if st.session_state.df_excel is not None:
            for p in st.session_state.df_excel['player'].tolist():
                all_players.append(f"{p} (Excel)")
        if st.session_state.df_db is not None:
            for p in st.session_state.df_db['player'].tolist():
                all_players.append(f"{p} (DB)")

        st.subheader("Сравнение двух игроков")
        compare_player1_label = st.selectbox("Игрок 1", all_players, key="cp1_v2")
        compare_player2_label = st.selectbox("Игрок 2", all_players, key="cp2_v2")
        if st.button("Сравнить выбранных", use_container_width=True, key="compare_btn_v2"):
            if compare_player1_label == compare_player2_label:
                st.warning("Выберите разных игроков.")
            else:
                # Извлекаем имя и источник
                def extract_player(label):
                    if label.endswith(" (Excel)"):
                        return label[:-7], st.session_state.df_excel
                    elif label.endswith(" (DB)"):
                        return label[:-4], st.session_state.df_db
                    return None, None
                name1, source1 = extract_player(compare_player1_label)
                name2, source2 = extract_player(compare_player2_label)
                if name1 and name2 and source1 is not None and source2 is not None:
                    p1 = source1[source1['player'] == name1].iloc[0]
                    p2 = source2[source2['player'] == name2].iloc[0]
                    # Для сравнения создаём объединённый DataFrame из двух строк, чтобы нормализация работала корректно
                    combined_df = pd.concat([p1.to_frame().T, p2.to_frame().T], ignore_index=True)
                    pos1 = get_position_group(p1['position'])
                    pos2 = get_position_group(p2['position'])
                    metrics_set = set()
                    for m in st.session_state.current_settings.get(pos1, {}) | st.session_state.current_settings.get(pos2, {}):
                        if m in combined_df.columns:
                            metrics_set.add(m)
                    radar_metrics = list(metrics_set)[:8]
                    if not radar_metrics:
                        radar_metrics = [c for c in combined_df.columns if c.endswith('_p90') or c.endswith('_pct')][:8]
                    fig = create_compare_figure(p1, p2, radar_metrics, combined_df)
                    st.pyplot(fig)
                else:
                    st.error("Не удалось найти игроков.")

        st.subheader("Сравнение игроков одной позиции")
        position_choice = st.selectbox("Позиция", ['FW','AM','CM','FB','CB'], key="pos_choice_comp_v2")
        # Собираем игроков этой позиции из обоих источников
        pos_players = []
        for label in all_players:
            if label.endswith(" (Excel)"):
                name = label[:-7]
                source = st.session_state.df_excel
            else:
                name = label[:-4]
                source = st.session_state.df_db
            if source is not None:
                row = source[source['player'] == name]
                if not row.empty and get_position_group(row.iloc[0]['position']) == position_choice:
                    pos_players.append(label)
        if not pos_players:
            st.info(f"Нет игроков позиции **{position_choice}**")
        else:
            selected_players_labels = st.multiselect(
                "Выберите до 6 игроков",
                pos_players,
                max_selections=6,
                key="multi_players_pos_v2"
            )
            if st.button("Сравнить игроков позиции", use_container_width=True, key="btn_compare_pos_v2"):
                if len(selected_players_labels) < 2:
                    st.warning("Выберите хотя бы двух игроков.")
                elif len(selected_players_labels) > 6:
                    st.warning("Максимум 6 игроков.")
                else:
                    # Извлекаем имена и формируем объединённый df для сравнения
                    players_data = []
                    for label in selected_players_labels:
                        if label.endswith(" (Excel)"):
                            name = label[:-7]
                            source = st.session_state.df_excel
                        else:
                            name = label[:-4]
                            source = st.session_state.df_db
                        player_row = source[source['player'] == name].iloc[0]
                        players_data.append(player_row)
                    combined_df = pd.DataFrame(players_data)
                    pos_metrics = [m for m, w in st.session_state.current_settings.get(position_choice, {}).items() if w != 0 and m in combined_df.columns]
                    if not pos_metrics:
                        st.error("Для данной позиции не заданы метрики в выбранных данных.")
                    else:
                        colors = ['blue','red','green','orange','purple','brown']
                        fig = create_position_radar([p['player'] for p in players_data], combined_df, pos_metrics, colors)
                        st.pyplot(fig)

# Основная область – работает с активным DataFrame
if st.session_state.active_df_type == 'excel':
    df_active = st.session_state.df_excel
    position_tables_active = st.session_state.position_tables_excel
elif st.session_state.active_df_type == 'db':
    df_active = st.session_state.df_db
    position_tables_active = st.session_state.position_tables_db
else:
    df_active = None
    position_tables_active = {}

if df_active is not None:
    all_metrics = [m for m in ALL_POSSIBLE_METRICS if m in df_active.columns]
    metric_names = {m: METRIC_NAMES_RU.get(m, m) for m in all_metrics}
    with st.expander("Настройка колонок общей таблицы"):
        selected_metrics = st.multiselect(
            "Выберите до 5 метрик для отображения",
            options=all_metrics,
            format_func=lambda m: metric_names[m],
            default=st.session_state.selected_main_metrics if st.session_state.selected_main_metrics else all_metrics[:3],
            max_selections=5,
            key="main_metrics_selector"
        )
    st.session_state.selected_main_metrics = selected_metrics
    if not selected_metrics:
        selected_metrics = all_metrics[:3]

    tabs = st.tabs(["Общий рейтинг", "FW", "AM", "CM", "FB", "CB"])

    with tabs[0]:
        df_main = build_main_table(df_active, selected_metrics)

        st.dataframe(
            df_main,
            height=600,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="main_table",
        )

        if "main_table" in st.session_state and st.session_state.main_table.selection.rows:
            idx = next(iter(st.session_state.main_table.selection.rows))
            if idx < len(df_active):
                player_row = df_active.iloc[idx]
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    fig = create_player_radar_figure(player_row, df_active, st.session_state.current_settings)
                    st.pyplot(fig)

    for i, pos in enumerate(['FW','AM','CM','FB','CB'], 1):
        with tabs[i]:
            rows, headers = position_tables_active.get(pos, ([], []))
            if rows:
                numbered_rows = [[j+1] + row for j, row in enumerate(rows)]
                df_pos = pd.DataFrame(numbered_rows, columns=['№'] + headers)
                st.dataframe(
                    df_pos,
                    height=400,
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key=f"table_{pos}",
                )
                state_key = f"table_{pos}"
                if state_key in st.session_state and st.session_state[state_key].selection.rows:
                    idx = next(iter(st.session_state[state_key].selection.rows))
                    if idx < len(rows):
                        player_name = rows[idx][0]
                        player_min = int(rows[idx][1])
                        candidate = df_active[(df_active['player'] == player_name) & (df_active['minutes'] == player_min)]
                        if not candidate.empty:
                            player_row = candidate.iloc[0]
                            col1, col2, col3 = st.columns([1, 2, 1])
                            with col2:
                                fig = create_player_radar_figure(player_row, df_active, st.session_state.current_settings)
                                st.pyplot(fig)
            else:
                st.info(f"Нет игроков позиции {pos}")

    if st.button("📥 Экспорт в Excel"):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_main.to_excel(writer, sheet_name='Общий рейтинг', index=False)
            for pos, (rows, headers) in position_tables_active.items():
                if rows:
                    df_pos = pd.DataFrame(rows, columns=headers)
                    df_pos.to_excel(writer, sheet_name=pos, index=False)
                    from openpyxl.formatting.rule import ColorScaleRule
                    from openpyxl.utils import get_column_letter
                    ws = writer.sheets[pos]
                    metric_columns = list(range(4, 4 + len(headers) - 3))
                    for col_idx in metric_columns:
                        col_letter = get_column_letter(col_idx)
                        max_row = len(rows) + 1
                        ws.conditional_formatting.add(
                            f'{col_letter}2:{col_letter}{max_row}',
                            ColorScaleRule(start_type='min', start_color='FFC7CE',
                                          mid_type='percentile', mid_value=50, mid_color='FFFFEB',
                                          end_type='max', end_color='C6EFCE')
                        )
        st.download_button(
            label="Скачать Excel",
            data=output.getvalue(),
            file_name="players_rating.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# Редактор весов (общий)
if st.session_state.get('show_weights_editor'):
    with st.expander("Редактор весов метрик", expanded=True):
        positions_order = ['FW', 'AM', 'CM', 'FB', 'CB']
        pos_names = {'FW':'Нападающие','AM':'Атак. полузащитники','CM':'Центр. полузащитники','FB':'Крайние защитники','CB':'Центр. защитники'}
        if df_active is not None:
            available_metrics = [m for m in ALL_POSSIBLE_METRICS if m in df_active.columns]
        else:
            available_metrics = ALL_POSSIBLE_METRICS
        weight_tabs = st.tabs([pos_names[p] for p in positions_order])
        new_weights = {}
        for idx, pos in enumerate(positions_order):
            with weight_tabs[idx]:
                st.caption(f"**{pos_names[pos]}** — снимите галочку, чтобы исключить")
                current_pos_weights = st.session_state.current_settings.get(pos, {})
                for metric in available_metrics:
                    name = METRIC_NAMES_RU.get(metric, metric)
                    enabled = metric in current_pos_weights and current_pos_weights[metric] != 0
                    displayed_weight = abs(current_pos_weights.get(metric, 1.0)) if enabled else 1.0
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        checked = st.checkbox(f"**{name}**", value=enabled, key=f"chk_{pos}_{metric}")
                    with col2:
                        weight_val = st.number_input("Вес", min_value=0.1, max_value=10.0, value=displayed_weight, step=0.5, disabled=not checked, key=f"wgt_{pos}_{metric}")
                    if checked and weight_val > 0:
                        if metric in NEGATIVE_METRICS:
                            new_weights.setdefault(pos, {})[metric] = -weight_val
                        else:
                            new_weights.setdefault(pos, {})[metric] = weight_val
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Сохранить веса", use_container_width=True, key="save_weights"):
                for pos in positions_order:
                    if pos not in new_weights or not new_weights[pos]:
                        st.error(f"Для позиции **{pos_names[pos]}** должна быть включена хотя бы одна метрика.")
                        st.stop()
                st.session_state.current_settings = new_weights
                save_settings(new_weights)
                st.session_state.show_weights_editor = False
                st.cache_data.clear()
                st.success("Веса обновлены. Данные пересчитываются...")
                for attr in ['df_excel', 'df_db']:
                    df = getattr(st.session_state, attr)
                    if df is not None:
                        setattr(st.session_state, attr, calculate_ratings(df, new_weights))
                        if attr == 'df_excel':
                            st.session_state.position_tables_excel = build_position_tables(df, new_weights)
                        else:
                            st.session_state.position_tables_db = build_position_tables(df, new_weights)
                st.rerun()
        with col2:
            if st.button("Отмена", use_container_width=True, key="cancel_weights"):
                st.session_state.show_weights_editor = False
                st.rerun()
