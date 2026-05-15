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
import plotly.graph_objects as go
from datetime import date

warnings.filterwarnings('ignore')
load_dotenv()

# -------------------- ГЛОБАЛЬНЫЕ КОНСТАНТЫ --------------------
MIN_MINUTES = 90
TOP_N_FOR_PLOTS = 8
SETTINGS_FILE = os.path.expanduser('~/InStatAnalyst_settings.pkl')

ALL_POSSIBLE_METRICS = [
    'goals_p90', 'assists_p90', 'shots_p90', 'shots_on_target_p90',
    'goals_by_head_p90', 'free_kick_shots_p90', 'free_kick_goals_p90',
    'shots_from_penalty_area_p90', 'shots_on_target_penalty_area_p90',
    'shots_outside_penalty_area_p90', 'shots_on_target_outside_penalty_area_p90',
    'headers_p90', 'headers_on_target_p90',
    'xG_p90',
    'key_passes_p90', 'passes_p90', 'pass_accuracy',
    'short_passes_p90', 'short_passes_accuracy',
    'long_passes_p90', 'long_passes_accuracy',
    'progressive_passes_p90', 'progressive_passes_accuracy',
    'passes_final_third_p90', 'passes_final_third_accuracy',
    'passes_into_penalty_box_p90', 'passes_into_penalty_box_accuracy',
    'super_long_passes_p90', 'super_long_passes_accuracy',
    'crosses_p90', 'crosses_accuracy',
    'passes_for_shot_p90',
    'dribbles_p90', 'dribbles_success_pct',
    'dribbling_final_third_p90', 'dribbling_final_third_success_pct',
    'carry_p90',
    'challenges_p90', 'challenges_won_pct',
    'defensive_challenges_p90', 'defensive_challenges_won_pct',
    'attacking_challenges_p90', 'attacking_challenges_won_pct',
    'air_challenges_p90', 'air_challenges_won_pct',
    'tackles_p90', 'tackles_success_pct',
    'interceptions_p90',
    'loose_ball_recoveries_p90',
    'actions_opp_box_p90', 'actions_opp_box_success_p90',
    'chances_p90', 'chances_successful_p90',
    'chances_created_p90',
    'involvement_scoring_p90',
    'shots_on_target_pct',
    'lost_balls_p90', 'lost_balls_own_half_p90', 'individual_ball_losses_p90',
    'lost_balls_after_passes_p90',
    'challenges_unsuccessful_p90', 'dribbles_unsuccessful_p90',
    'bad_ball_control_p90', 'offsides_p90',
    'mistakes_goals_p90', 'mistakes_chances_p90',
    'fouls_p90', 'fouls_suffered_p90',
    'yellow_cards_p90', 'red_cards_p90',
    'ball_recoveries_p90', 'ball_recoveries_opp_half_p90',
    'actions_successful_p90', 'actions_unsuccessful_p90',
    'final_third_entries_p90', 'final_third_carry_p90',
    'final_third_entries_pass_p90',
    'open_passes_received_p90',
    'long_open_passes_received_p90',
    'super_long_open_passes_received_p90',
    'open_passes_received_first_third_p90',
    'open_passes_received_central_third_p90',
    'open_passes_received_final_third_p90',
    'open_passes_received_opponent_box_p90',
]

NEGATIVE_METRICS = [
    'lost_balls_p90', 'lost_balls_own_half_p90', 'individual_ball_losses_p90',
    'lost_balls_after_passes_p90', 'challenges_unsuccessful_p90',
    'dribbles_unsuccessful_p90', 'bad_ball_control_p90', 'offsides_p90',
    'yellow_cards_p90', 'red_cards_p90', 'mistakes_goals_p90', 'mistakes_chances_p90',
    'fouls_p90', 'actions_unsuccessful_p90',
    # для матчей
    'lost_balls', 'lost_balls_own_half', 'individual_ball_losses',
    'lost_balls_after_passes', 'challenges_unsuccessful',
    'dribbles_unsuccessful', 'bad_ball_control', 'offsides',
    'yellow_cards', 'red_cards', 'mistakes_goals', 'mistakes_chances',
    'fouls', 'actions_unsuccessful',
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

for pos in DEFAULT_METRICS_WEIGHTS:
    for m in ALL_POSSIBLE_METRICS:
        if m not in DEFAULT_METRICS_WEIGHTS[pos]:
            DEFAULT_METRICS_WEIGHTS[pos][m] = 0.0

METRIC_NAMES_RU = {
    'goals_p90': 'Голы', 'assists_p90': 'Голевые передачи',
    'shots_p90': 'Удары', 'shots_on_target_p90': 'Удары в створ',
    'goals_by_head_p90': 'Голы головой',
    'free_kick_shots_p90': 'Штрафные удары', 'free_kick_goals_p90': 'Голы со штрафных',
    'shots_from_penalty_area_p90': 'Удары из штрафной',
    'shots_on_target_penalty_area_p90': 'В створ из штрафной',
    'shots_outside_penalty_area_p90': 'Удары из-за штрафной',
    'shots_on_target_outside_penalty_area_p90': 'В створ из-за штрафной',
    'headers_p90': 'Удары головой', 'headers_on_target_p90': 'Удары головой в створ',
    'xG_p90': 'xG (ожидаемые голы)',
    'key_passes_p90': 'Ключевые передачи', 'passes_p90': 'Передачи',
    'pass_accuracy': 'Точность передач %',
    'short_passes_p90': 'Короткие передачи', 'short_passes_accuracy': 'Короткие точные %',
    'long_passes_p90': 'Длинные передачи', 'long_passes_accuracy': 'Длинные точные %',
    'progressive_passes_p90': 'Продвигающие передачи',
    'progressive_passes_accuracy': 'Продвигающие точные %',
    'passes_final_third_p90': 'Передачи в финальную треть',
    'passes_final_third_accuracy': 'В финальную треть точные %',
    'passes_into_penalty_box_p90': 'Передачи в штрафную',
    'passes_into_penalty_box_accuracy': 'В штрафную точные %',
    'super_long_passes_p90': 'Сверхдлинные передачи',
    'super_long_passes_accuracy': 'Сверхдлинные точные %',
    'crosses_p90': 'Кроссы', 'crosses_accuracy': 'Кроссы точные %',
    'passes_for_shot_p90': 'Передачи под удар',
    'dribbles_p90': 'Обводки', 'dribbles_success_pct': 'Обводки успешные %',
    'dribbling_final_third_p90': 'Обводки в финальной трети',
    'dribbling_final_third_success_pct': 'Обводки в финальной трети %',
    'carry_p90': 'Продвижение мяча (Carry)',
    'challenges_p90': 'Единоборства', 'challenges_won_pct': 'Единоборства выигранные %',
    'defensive_challenges_p90': 'Оборонительные единоборства',
    'defensive_challenges_won_pct': 'Оборонительные един. выигранные %',
    'attacking_challenges_p90': 'Атакующие единоборства',
    'attacking_challenges_won_pct': 'Атакующие един. выигранные %',
    'air_challenges_p90': 'Верховые единоборства',
    'air_challenges_won_pct': 'Верховые единоборства %',
    'tackles_p90': 'Отборы', 'tackles_success_pct': 'Отборы успешные %',
    'interceptions_p90': 'Перехваты',
    'loose_ball_recoveries_p90': 'Подборы',
    'actions_opp_box_p90': 'Действия в штрафной соперника',
    'actions_opp_box_success_p90': 'Успешные действия в штрафной',
    'chances_p90': 'Голевые моменты', 'chances_successful_p90': 'Реализованные моменты',
    'chances_created_p90': 'Созданные моменты',
    'involvement_scoring_p90': 'Участие в голевых атаках',
    'shots_on_target_pct': 'Точность ударов %',
    'lost_balls_p90': 'Потери мяча', 'lost_balls_own_half_p90': 'Потери на своей половине',
    'individual_ball_losses_p90': 'Индивидуальные потери',
    'lost_balls_after_passes_p90': 'Потери после передач',
    'challenges_unsuccessful_p90': 'Неудачные единоборства',
    'dribbles_unsuccessful_p90': 'Неудачные обводки',
    'bad_ball_control_p90': 'Плохой приём мяча',
    'offsides_p90': 'Офсайды',
    'mistakes_goals_p90': 'Ошибки → голы', 'mistakes_chances_p90': 'Ошибки → моменты',
    'fouls_p90': 'Фолы', 'fouls_suffered_p90': 'Фолы на игроке',
    'yellow_cards_p90': 'Жёлтые карточки', 'red_cards_p90': 'Красные карточки',
    'ball_recoveries_p90': 'Возвраты мяча',
    'ball_recoveries_opp_half_p90': 'Возвраты на чужой половине',
    'actions_successful_p90': 'Успешные действия',
    'actions_unsuccessful_p90': 'Неуспешные действия',
    'final_third_entries_p90': 'Входы в финальную треть',
    'final_third_carry_p90': 'Входы в финальную треть (дриблинг)',
    'final_third_entries_pass_p90': 'Входы в финальную треть (пас)',
    'open_passes_received_p90': 'Открытые передачи принято',
    'long_open_passes_received_p90': 'Длинные передачи принято',
    'super_long_open_passes_received_p90': 'Сверхдлинные передачи принято',
    'open_passes_received_first_third_p90': 'Принято в 1-й трети',
    'open_passes_received_central_third_p90': 'Принято в центр. трети',
    'open_passes_received_final_third_p90': 'Принято в финальной трети',
    'open_passes_received_opponent_box_p90': 'Принято в штрафной',
}

# -------------------- БЕЗОПАСНОЕ ПОДКЛЮЧЕНИЕ К БД --------------------
def get_db_config():
    return {
        "host": os.getenv("SUPABASE_HOST"),
        "port": os.getenv("SUPABASE_PORT"),
        "dbname": os.getenv("SUPABASE_DBNAME"),
        "user": os.getenv("SUPABASE_USER"),
        "password": os.getenv("SUPABASE_PASSWORD"),
    }

def check_db_connection():
    required_vars = ["SUPABASE_HOST", "SUPABASE_PORT", "SUPABASE_DBNAME",
                     "SUPABASE_USER", "SUPABASE_PASSWORD"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        st.error(f"❌ Отсутствуют переменные окружения: {', '.join(missing)}. "
                 f"Добавьте их в файл `.env`.")
        st.stop()
    try:
        conn = psycopg2.connect(**get_db_config())
        conn.close()
    except Exception as e:
        st.error(f"❌ Не удалось подключиться к базе данных: {e}")
        st.stop()

check_db_connection()

# -------------------- ФУНКЦИИ АНАЛИЗА (общие) --------------------
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

# -------------------- МАТЧЕВАЯ СТАТИСТИКА (без нормализации на 90 минут) --------------------
MATCH_METRIC_NAMES_RU = {
    'goals': 'Голы', 'assists': 'Голевые передачи',
    'shots': 'Удары', 'shots_on_target': 'Удары в створ',
    'goals_by_head': 'Голы головой',
    'free_kick_shots': 'Штрафные удары', 'free_kick_goals': 'Голы со штрафных',
    'shots_from_penalty_area': 'Удары из штрафной',
    'shots_on_target_penalty_area': 'В створ из штрафной',
    'shots_outside_penalty_area': 'Удары из-за штрафной',
    'shots_on_target_outside_penalty_area': 'В створ из-за штрафной',
    'headers': 'Удары головой', 'headers_on_target': 'Удары головой в створ',
    'xG': 'xG (ожидаемые голы)',
    'key_passes': 'Ключевые передачи', 'passes': 'Передачи',
    'pass_accuracy': 'Точность передач',
    'short_passes': 'Короткие передачи', 'short_passes_accuracy': 'Короткие точные',
    'long_passes': 'Длинные передачи', 'long_passes_accuracy': 'Длинные точные',
    'progressive_passes': 'Продвигающие передачи',
    'progressive_passes_accuracy': 'Продвигающие точные',
    'passes_final_third': 'Передачи в финальную треть',
    'passes_final_third_accuracy': 'В финальную треть точные',
    'passes_into_penalty_box': 'Передачи в штрафную',
    'passes_into_penalty_box_accuracy': 'В штрафную точные',
    'super_long_passes': 'Сверхдлинные передачи',
    'super_long_passes_accuracy': 'Сверхдлинные точные',
    'crosses': 'Кроссы', 'crosses_accuracy': 'Кроссы точные',
    'passes_for_shot': 'Передачи под удар',
    'dribbles': 'Обводки', 'dribbles_success_pct': 'Обводки успешные',
    'dribbling_final_third': 'Обводки в финальной трети',
    'dribbling_final_third_success_pct': 'Обводки в финальной трети',
    'carry': 'Продвижение мяча (Carry)',
    'challenges': 'Единоборства', 'challenges_won_pct': 'Единоборства выигранные',
    'defensive_challenges': 'Оборонительные единоборства',
    'defensive_challenges_won_pct': 'Оборонительные един. выигранные',
    'attacking_challenges': 'Атакующие единоборства',
    'attacking_challenges_won_pct': 'Атакующие един. выигранные',
    'air_challenges': 'Верховые единоборства',
    'air_challenges_won_pct': 'Верховые единоборства',
    'tackles': 'Отборы', 'tackles_success_pct': 'Отборы успешные',
    'interceptions': 'Перехваты',
    'loose_ball_recoveries': 'Подборы',
    'actions_opp_box': 'Действия в штрафной соперника',
    'actions_opp_box_success': 'Успешные действия в штрафной',
    'chances': 'Голевые моменты', 'chances_successful': 'Реализованные моменты',
    'chances_created': 'Созданные моменты',
    'involvement_scoring': 'Участие в голевых атаках',
    'shots_on_target_pct': 'Точность ударов',
    'lost_balls': 'Потери мяча', 'lost_balls_own_half': 'Потери на своей половине',
    'individual_ball_losses': 'Индивидуальные потери',
    'lost_balls_after_passes': 'Потери после передач',
    'challenges_unsuccessful': 'Неудачные единоборства',
    'dribbles_unsuccessful': 'Неудачные обводки',
    'bad_ball_control': 'Плохой приём мяча',
    'offsides': 'Офсайды',
    'mistakes_goals': 'Ошибки → голы', 'mistakes_chances': 'Ошибки → моменты',
    'fouls': 'Фолы', 'fouls_suffered': 'Фолы на игроке',
    'yellow_cards': 'Жёлтые карточки', 'red_cards': 'Красные карточки',
    'ball_recoveries': 'Возвраты мяча',
    'ball_recoveries_opp_half': 'Возвраты на чужой половине',
    'actions_successful': 'Успешные действия',
    'actions_unsuccessful': 'Неуспешные действия',
    'final_third_entries': 'Входы в финальную треть',
    'final_third_carry': 'Входы в финальную треть (дриблинг)',
    'final_third_entries_pass': 'Входы в финальную треть (пас)',
    'open_passes_received': 'Открытые передачи принято',
    'long_open_passes_received': 'Длинные передачи принято',
    'super_long_open_passes_received': 'Сверхдлинные передачи принято',
    'open_passes_received_first_third': 'Принято в 1-й трети',
    'open_passes_received_central_third': 'Принято в центр. трети',
    'open_passes_received_final_third': 'Принято в финальной трети',
    'open_passes_received_opponent_box': 'Принято в штрафной',
}

MATCH_ALL_METRICS = [
    'goals', 'assists', 'shots', 'shots_on_target',
    'goals_by_head', 'free_kick_shots', 'free_kick_goals',
    'shots_from_penalty_area', 'shots_on_target_penalty_area',
    'shots_outside_penalty_area', 'shots_on_target_outside_penalty_area',
    'headers', 'headers_on_target', 'xG',
    'key_passes', 'passes', 'pass_accuracy',
    'short_passes', 'short_passes_accuracy', 'long_passes', 'long_passes_accuracy',
    'progressive_passes', 'progressive_passes_accuracy',
    'passes_final_third', 'passes_final_third_accuracy',
    'passes_into_penalty_box', 'passes_into_penalty_box_accuracy',
    'super_long_passes', 'super_long_passes_accuracy',
    'crosses', 'crosses_accuracy', 'passes_for_shot',
    'dribbles', 'dribbles_success_pct',
    'dribbling_final_third', 'dribbling_final_third_success_pct', 'carry',
    'challenges', 'challenges_won_pct',
    'defensive_challenges', 'defensive_challenges_won_pct',
    'attacking_challenges', 'attacking_challenges_won_pct',
    'air_challenges', 'air_challenges_won_pct',
    'tackles', 'tackles_success_pct', 'interceptions',
    'loose_ball_recoveries', 'actions_opp_box', 'actions_opp_box_success',
    'chances', 'chances_successful', 'chances_created',
    'involvement_scoring', 'shots_on_target_pct',
    'lost_balls', 'lost_balls_own_half', 'individual_ball_losses',
    'lost_balls_after_passes', 'challenges_unsuccessful',
    'dribbles_unsuccessful', 'bad_ball_control', 'offsides',
    'mistakes_goals', 'mistakes_chances',
    'fouls', 'fouls_suffered',
    'yellow_cards', 'red_cards',
    'ball_recoveries', 'ball_recoveries_opp_half',
    'actions_successful', 'actions_unsuccessful',
    'final_third_entries', 'final_third_carry', 'final_third_entries_pass',
    'open_passes_received', 'long_open_passes_received',
    'super_long_open_passes_received',
    'open_passes_received_first_third', 'open_passes_received_central_third',
    'open_passes_received_final_third', 'open_passes_received_opponent_box',
]

DEFAULT_MATCH_WEIGHTS = {
    'FW': {
        'goals': 3.0, 'xG': 2.5, 'shots_on_target': 2.0,
        'assists': 1.5, 'dribbles': 1.2, 'actions_opp_box': 1.2,
        'chances_successful': 1.0, 'key_passes': 1.0, 'pass_accuracy': 0.5,
        'lost_balls': -2.0, 'individual_ball_losses': -1.5,
        'yellow_cards': -0.5, 'red_cards': -3.0, 'mistakes_goals': -2.5,
        'mistakes_chances': -1.0, 'fouls': -0.5,
    },
    'AM': {
        'key_passes': 3.0, 'assists': 2.5, 'progressive_passes': 2.0,
        'pass_accuracy': 1.5, 'dribbles': 1.5, 'goals': 1.0,
        'xG': 1.0, 'shots_on_target': 1.0, 'chances': 1.0,
        'lost_balls': -1.5, 'individual_ball_losses': -1.0,
        'yellow_cards': -0.5, 'red_cards': -3.0, 'mistakes_goals': -1.5,
        'mistakes_chances': -1.0, 'fouls': -0.5,
    },
    'CM': {
        'pass_accuracy': 3.0, 'progressive_passes': 2.5, 'interceptions': 2.0,
        'tackles': 1.5, 'key_passes': 1.5, 'progressive_passes_accuracy': 1.5,
        'challenges_won_pct': 1.0, 'ball_recoveries': 1.0,
        'lost_balls_own_half': -2.0, 'lost_balls': -1.5,
        'individual_ball_losses': -1.0, 'yellow_cards': -1.0,
        'red_cards': -3.0, 'mistakes_goals': -2.0, 'mistakes_chances': -1.5,
        'fouls': -0.5,
    },
    'FB': {
        'tackles': 2.5, 'interceptions': 2.0, 'crosses_accuracy': 2.0,
        'pass_accuracy': 1.5, 'tackles_success_pct': 1.5, 'dribbles': 1.2,
        'key_passes': 1.2, 'progressive_passes': 1.0,
        'mistakes_goals': -2.5, 'mistakes_chances': -1.5,
        'lost_balls_own_half': -2.0, 'lost_balls': -1.0,
        'yellow_cards': -1.0, 'red_cards': -3.0, 'fouls': -0.5,
    },
    'CB': {
        'interceptions': 3.0, 'tackles': 2.5, 'air_challenges_won_pct': 2.5,
        'tackles_success_pct': 2.0, 'challenges_won_pct': 1.5, 'ball_recoveries': 1.5,
        'loose_ball_recoveries': 1.5, 'pass_accuracy': 1.0,
        'mistakes_goals': -3.0, 'mistakes_chances': -2.0,
        'lost_balls_own_half': -2.5, 'individual_ball_losses': -1.5,
        'yellow_cards': -1.0, 'red_cards': -3.5, 'fouls': -1.0,
    },
}

for pos in DEFAULT_MATCH_WEIGHTS:
    for m in MATCH_ALL_METRICS:
        if m not in DEFAULT_MATCH_WEIGHTS[pos]:
            DEFAULT_MATCH_WEIGHTS[pos][m] = 0.0

def format_match_metric(metric, value, player_row, avg_val=None, season_val=None):
    """Форматирует метрику матча с опциональным сравнением со средним по лиге и с сезоном."""
    if pd.isna(value):
        return "-"
    try:
        value = float(value)
    except (ValueError, TypeError):
        return str(value)

    # Базовое форматирование значения
    formatted_value = ""
    if metric.endswith('_pct') or metric == 'pass_accuracy':
        formatted_value = f"{value:.1f}%"
    elif metric in ['goals', 'assists', 'xG', 'yellow_cards', 'red_cards',
                    'mistakes_goals', 'mistakes_chances', 'fouls', 'fouls_suffered']:
        formatted_value = f"{value:.2f}"
    else:
        if value == int(value):
            formatted_value = str(int(value))
        else:
            formatted_value = f"{value:.2f}"

    # Добавляем сравнение со средним по лиге (цветной фон)
    style = ""
    if avg_val is not None and pd.notna(avg_val):
        try:
            avg_val = float(avg_val)
            if metric in NEGATIVE_METRICS:
                # Для негативных метрик: меньше = лучше
                better = value < avg_val
            else:
                better = value > avg_val
            color = "#e6f3ff" if better else "#f5e6d3"  # светло-синий или светло-коричневый
            style = f"background-color: {color};"
        except (ValueError, TypeError):
            pass

    # Добавляем сравнение с сезоном (стрелки)
    arrows = ""
    if season_val is not None and pd.notna(season_val):
        try:
            season_val = float(season_val)
            if metric in NEGATIVE_METRICS:
                better_season = value < season_val
            else:
                better_season = value > season_val
            if better_season:
                arrows = " 🔼🔼"
            else:
                arrows = " 🔽🔽"
        except (ValueError, TypeError):
            pass

    # Собираем итоговую строку с HTML-стилем
    if style:
        return f'<span style="{style} padding: 2px 6px; border-radius: 4px;">{formatted_value}{arrows}</span>'
    else:
        return formatted_value + arrows

def get_league_averages(league_name, season):
    """Возвращает Series средних значений по лиге/сезону для матчевых метрик."""
    df = load_from_db([league_name], [season])
    if df is None or df.empty:
        return None
    # Для матчей используем абсолютные метрики (без _p90)
    # Поэтому нам нужны средние по абсолютным показателям за сезон.
    # Но в load_from_db мы вычисляем _p90 для сезонных данных.
    # Чтобы получить абсолютные средние, проще сделать отдельный запрос или использовать уже загруженные данные.
    # Поскольку load_from_db возвращает DataFrame с абсолютными значениями и _p90,
    # мы можем взять средние по абсолютным колонкам (которые совпадают с MATCH_ALL_METRICS).
    avg = {}
    for m in MATCH_ALL_METRICS:
        if m in df.columns:
            avg[m] = df[m].mean()
    return pd.Series(avg)

def get_player_season_stats_df(league_name, season):
    """Загружает сезонную статистику игроков (абсолютные значения) для сравнения с матчем."""
    # Используем load_from_db, но нам нужны абсолютные значения.
    # load_from_db добавляет _p90, но и абсолютные колонки остаются.
    # Поэтому просто вернём df из load_from_db.
    return load_from_db([league_name], [season])

@st.cache_data
def calculate_match_ratings(df, position_weights, league_col='league'):
    if league_col in df.columns:
        result_dfs = []
        for _, group_df in df.groupby(league_col):
            rated = _calculate_match_ratings_for_group(group_df, position_weights)
            result_dfs.append(rated)
        return pd.concat(result_dfs, ignore_index=True)
    else:
        return _calculate_match_ratings_for_group(df, position_weights)

def _calculate_match_ratings_for_group(df, position_weights):
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
        pos_sum = 0.0; pos_weight_sum = 0.0
        neg_sum = 0.0; neg_weight_sum = 0.0
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
        return 100 * (pos_score + neg_score) / 2

    df['rating'] = df.apply(calc_row, axis=1).round(1)
    return df

def build_match_position_tables(df, position_weights, avg_series=None, season_df=None):
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
                # Получаем среднее по лиге
                avg_val = avg_series[m] if (avg_series is not None and m in avg_series) else None
                # Получаем сезонное значение игрока
                season_val = None
                if season_df is not None:
                    player_name = player_row['player']
                    season_row = season_df[season_df['player'] == player_name]
                    if not season_row.empty and m in season_row.columns:
                        season_val = season_row.iloc[0][m]
                formatted = format_match_metric(m, val, player_row, avg_val=avg_val, season_val=season_val)
                norm_val = player_row[f'{m}_norm_pos']
                is_max = (norm_val == max_vals[m])
                is_min = (norm_val == min_vals[m])
                # Добавляем подсветку лучшего/худшего в позиции (но она может конфликтовать с цветом avg)
                # Поэтому оставим стрелки и цвет для avg, а для позиции просто текст с иконками
                if is_max and not is_min:
                    formatted = f"🟢 {formatted}"
                elif is_min and not is_max:
                    formatted = f"🔴 {formatted}"
                row_data.append(formatted)
            rows.append(row_data)

        # Формируем заголовки с средними по лиге
        headers = ['Игрок', 'Мин', 'Рейтинг']
        for m in metrics:
            name = MATCH_METRIC_NAMES_RU.get(m, m)
            if avg_series is not None and m in avg_series:
                avg_val = avg_series[m]
                if pd.notna(avg_val):
                    headers.append(f"{name} ({avg_val:.2f})")
                else:
                    headers.append(name)
            else:
                headers.append(name)

        tables[pos] = (rows, headers)
    return tables

def build_match_main_table(df, selected_metrics, avg_series=None, season_df=None):
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

    # Заголовки с средними
    main_headers = ['№','Игрок','Поз','Мин','Рейтинг']
    for m in metrics:
        name = MATCH_METRIC_NAMES_RU.get(m, m)
        if avg_series is not None and m in avg_series:
            avg_val = avg_series[m]
            if pd.notna(avg_val):
                main_headers.append(f"{name} ({avg_val:.2f})")
            else:
                main_headers.append(name)
        else:
            main_headers.append(name)

    main_data = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        row_data = [i, row['player'], row['position'], int(row['minutes']), f"{row['rating']:.1f}"]
        for m in metrics:
            val = row[m]
            avg_val = avg_series[m] if (avg_series is not None and m in avg_series) else None
            season_val = None
            if season_df is not None:
                player_name = row['player']
                season_row = season_df[season_df['player'] == player_name]
                if not season_row.empty and m in season_row.columns:
                    season_val = season_row.iloc[0][m]
            detail = format_match_metric(m, val, row, avg_val=avg_val, season_val=season_val)
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

# -------------------- ЗАГРУЗКА СЕЗОННОЙ СТАТИСТИКИ ИЗ БД --------------------
def load_from_db(league_names, seasons, teams=None):
    conn = psycopg2.connect(**get_db_config())
    query = """
    SELECT 
        p.name AS player, p.position,
        ps.minutes_played AS minutes,
        ps.goals, ps.assists, ps.shots, ps.shots_on_target,
        ps.goals_by_head, ps.free_kick_shots, ps.free_kick_goals,
        ps.shots_from_penalty_area, ps.shots_on_target_penalty_area,
        ps.shots_outside_penalty_area, ps.shots_on_target_outside_penalty_area,
        ps.headers, ps.headers_on_target,
        ps.xG,
        ps.key_passes, ps.passes, ps.pass_accuracy,
        ps.short_passes, ps.short_passes_accuracy,
        ps.long_passes, ps.long_passes_accuracy,
        ps.progressive_passes, ps.progressive_passes_accuracy,
        ps.passes_final_third, ps.passes_final_third_accuracy,
        ps.passes_into_penalty_box, ps.passes_into_penalty_box_accuracy,
        ps.super_long_passes, ps.super_long_passes_accuracy,
        ps.crosses, ps.crosses_accuracy,
        ps.passes_for_shot,
        ps.dribbles, ps.dribbles_success_pct,
        ps.dribbling_final_third, ps.dribbling_final_third_success_pct,
        ps.carry,
        ps.challenges, ps.challenges_won_pct,
        ps.defensive_challenges, ps.defensive_challenges_won_pct,
        ps.attacking_challenges, ps.attacking_challenges_won_pct,
        ps.air_challenges, ps.air_challenges_won_pct,
        ps.tackles, ps.tackles_success_pct,
        ps.interceptions,
        ps.loose_ball_recoveries,
        ps.actions_opp_box, ps.actions_opp_box_success,
        ps.chances, ps.chances_successful, ps.chances_created,
        ps.involvement_scoring,
        ps.shots_on_target_pct,
        ps.lost_balls, ps.lost_balls_own_half, ps.individual_ball_losses,
        ps.lost_balls_after_passes,
        ps.challenges_unsuccessful, ps.dribbles_unsuccessful,
        ps.bad_ball_control, ps.offsides,
        ps.mistakes_goals, ps.mistakes_chances,
        ps.fouls, ps.fouls_suffered,
        ps.yellow_cards, ps.red_cards,
        ps.ball_recoveries, ps.ball_recoveries_opp_half,
        ps.actions_successful, ps.actions_unsuccessful, ps.actions,
        ps.final_third_entries, ps.final_third_carry, ps.final_third_entries_pass,
        ps.open_passes_received, ps.long_open_passes_received,
        ps.super_long_open_passes_received,
        ps.open_passes_received_first_third, ps.open_passes_received_central_third,
        ps.open_passes_received_final_third, ps.open_passes_received_opponent_box,
        ps.matches_played, ps.starting_lineup,
        t.name AS team, l.name AS league
    FROM player_stats ps
    JOIN players p ON ps.player_id = p.id
    JOIN teams t ON ps.team_id = t.id
    JOIN leagues l ON t.league_id = l.id
    WHERE l.name = ANY(%s) AND ps.season = ANY(%s)
    """
    params = [league_names, seasons]
    if teams and len(teams) > 0:
        query += " AND t.name = ANY(%s)"
        params.append(teams)
    df = pd.read_sql(query, conn, params=params)
    conn.close()

    df = df[~df['position'].str.upper().str.contains('GK', na=False)]

    pct_cols = [
        'pass_accuracy', 'dribbles_success_pct', 'tackles_success_pct',
        'crosses_accuracy', 'challenges_won_pct', 'air_challenges_won_pct',
        'progressive_passes_accuracy', 'passes_final_third_accuracy',
        'short_passes_accuracy', 'long_passes_accuracy',
        'passes_into_penalty_box_accuracy', 'super_long_passes_accuracy',
        'dribbling_final_third_success_pct', 'defensive_challenges_won_pct',
        'attacking_challenges_won_pct', 'shots_on_target_pct',
    ]
    for col in pct_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if df[col].max() <= 1.0:
                df[col] = df[col] * 100

    minutes = pd.to_numeric(df['minutes'], errors='coerce').fillna(0)
    stats_to_norm = [
        'goals', 'assists', 'shots', 'shots_on_target',
        'goals_by_head', 'free_kick_shots', 'free_kick_goals',
        'shots_from_penalty_area', 'shots_on_target_penalty_area',
        'shots_outside_penalty_area', 'shots_on_target_outside_penalty_area',
        'headers', 'headers_on_target',
        'xG', 'key_passes', 'passes',
        'short_passes', 'long_passes',
        'progressive_passes', 'passes_final_third',
        'passes_into_penalty_box', 'super_long_passes',
        'crosses', 'passes_for_shot',
        'dribbles', 'dribbling_final_third', 'carry',
        'challenges', 'defensive_challenges', 'attacking_challenges',
        'air_challenges', 'tackles', 'interceptions',
        'loose_ball_recoveries', 'actions_opp_box', 'actions_opp_box_success',
        'chances', 'chances_successful', 'chances_created',
        'involvement_scoring',
        'lost_balls', 'lost_balls_own_half', 'individual_ball_losses',
        'lost_balls_after_passes', 'challenges_unsuccessful',
        'dribbles_unsuccessful', 'bad_ball_control', 'offsides',
        'mistakes_goals', 'mistakes_chances',
        'fouls', 'fouls_suffered', 'yellow_cards', 'red_cards',
        'ball_recoveries', 'ball_recoveries_opp_half',
        'actions', 'actions_successful', 'actions_unsuccessful',
        'final_third_entries', 'final_third_carry', 'final_third_entries_pass',
        'open_passes_received', 'long_open_passes_received',
        'super_long_open_passes_received',
        'open_passes_received_first_third', 'open_passes_received_central_third',
        'open_passes_received_final_third', 'open_passes_received_opponent_box',
    ]
    for col in stats_to_norm:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            df[f'{col}_p90'] = np.where(minutes > 0, (df[col] / minutes) * 90, 0)

    return df

# -------------------- ИМПОРТ СЕЗОННОГО EXCEL --------------------
RENAME_DICT_IMPORT = {
    'Player': 'player', 'Position': 'position',
    'Minutes played': 'minutes_played',
    'Goals': 'goals', 'Assists': 'assists',
    'Shots': 'shots', 'Shots on target': 'shots_on_target',
    'Goals by head': 'goals_by_head',
    'Free-kick shots': 'free_kick_shots', 'Free-kick goals': 'free_kick_goals',
    'Shots from the penalty area': 'shots_from_penalty_area',
    'Shots on target from the penalty area': 'shots_on_target_penalty_area',
    'Shots from outside the penalty area': 'shots_outside_penalty_area',
    'Shots on target from outside the penalty area': 'shots_on_target_outside_penalty_area',
    'Headers': 'headers', 'Headers on target': 'headers_on_target',
    'xG (expected goals)': 'xG',
    'Key passes': 'key_passes', 'Passes': 'passes',
    'Passes accurate, %': 'pass_accuracy',
    'Short passes': 'short_passes', 'Short passes accurate, %': 'short_passes_accuracy',
    'Long passes': 'long_passes', 'Long passes accurate, %': 'long_passes_accuracy',
    'Progressive passes': 'progressive_passes',
    'Progressive passes accurate, %': 'progressive_passes_accuracy',
    'Passes forward to the final third': 'passes_final_third',
    'Passes forward to the final third accurate, %': 'passes_final_third_accuracy',
    'Passes into the penalty box': 'passes_into_penalty_box',
    'Passes into the penalty box accurate, %': 'passes_into_penalty_box_accuracy',
    'Super long passes': 'super_long_passes',
    'Super long passes accurate, %': 'super_long_passes_accuracy',
    'Crosses': 'crosses', 'Crosses accurate, %': 'crosses_accuracy',
    'Passes for a shot': 'passes_for_shot',
    'Dribbles': 'dribbles', 'Dribbles successful, %': 'dribbles_success_pct',
    'Dribbling in the final third': 'dribbling_final_third',
    'Dribbling in the final third successful, %': 'dribbling_final_third_success_pct',
    'Carry': 'carry',
    'Challenges': 'challenges', 'Challenges won, %': 'challenges_won_pct',
    'Defensive challenges': 'defensive_challenges',
    'Defensive challenges won, %': 'defensive_challenges_won_pct',
    'Attacking challenges': 'attacking_challenges',
    'Attacking challenges won, %': 'attacking_challenges_won_pct',
    'Air challenges': 'air_challenges',
    'Air challenges won, %': 'air_challenges_won_pct',
    'Tackles': 'tackles', 'Tackles successful, %': 'tackles_success_pct',
    'Interceptions': 'interceptions',
    'Loose ball recoveries': 'loose_ball_recoveries',
    'Actions in opponent\'s box': 'actions_opp_box',
    'Actions in opponent\'s box successful': 'actions_opp_box_success',
    'Chances': 'chances', 'Chances successful': 'chances_successful',
    'Chances created': 'chances_created',
    'Involvement in scoring attacks': 'involvement_scoring',
    'Shots on target, %': 'shots_on_target_pct',
    'Lost balls': 'lost_balls', 'Lost balls in own half': 'lost_balls_own_half',
    'Individual ball losses': 'individual_ball_losses',
    'Lost balls after passes': 'lost_balls_after_passes',
    'Challenges unsuccessful': 'challenges_unsuccessful',
    'Dribbles unsuccessful': 'dribbles_unsuccessful',
    'Bad ball control': 'bad_ball_control', 'Offsides': 'offsides',
    'Mistakes leading to goals': 'mistakes_goals',
    'Mistakes leading to chances': 'mistakes_chances',
    'Fouls': 'fouls', 'Fouls suffered': 'fouls_suffered',
    'Yellow cards': 'yellow_cards', 'Red cards': 'red_cards',
    'Ball recoveries': 'ball_recoveries',
    'Ball recoveries in opponent\'s half': 'ball_recoveries_opp_half',
    'Actions': 'actions', 'Actions successful': 'actions_successful',
    'Actions unsuccessful': 'actions_unsuccessful',
    'Final third entries': 'final_third_entries',
    'Final third entries through carry': 'final_third_carry',
    'Final third entries through pass': 'final_third_entries_pass',
    'Matches played': 'matches_played',
    'Starting lineup appearances': 'starting_lineup',
    'Open passes received': 'open_passes_received',
    'Long open passes received': 'long_open_passes_received',
    'Super long open passes received': 'super_long_open_passes_received',
    'Open passes received in the first third': 'open_passes_received_first_third',
    'Open passes received in the central third': 'open_passes_received_central_third',
    'Open passes received in the final third': 'open_passes_received_final_third',
    'Open passes received in the opponent\'s box': 'open_passes_received_opponent_box',
}

STATS_FIELDS_SEASON = [v for k, v in RENAME_DICT_IMPORT.items() if k not in ['Player', 'Position']]

def clean_value(v):
    if pd.isna(v) or str(v).strip() in ('', '-'):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None

def import_season_excel(uploaded_file_content, league_name, season, team_column='Team'):
    try:
        df = pd.read_excel(io.BytesIO(uploaded_file_content), sheet_name='Основная статистика')
    except ValueError:
        xls = pd.ExcelFile(io.BytesIO(uploaded_file_content))
        first_sheet = xls.sheet_names[0]
        df = pd.read_excel(io.BytesIO(uploaded_file_content), sheet_name=first_sheet, header=0)
    df = df.dropna(subset=['№'])

    existing_renames = {k: v for k, v in RENAME_DICT_IMPORT.items() if k in df.columns}
    if team_column and team_column != 'team':
        existing_renames[team_column] = 'team'
    df = df.rename(columns=existing_renames)

    if 'player' not in df.columns:
        st.error("В файле нет колонки 'Player'. Импорт невозможен.")
        return 0
    if 'team' not in df.columns:
        st.error(f"В файле нет колонки '{team_column}'. Импорт невозможен.")
        return 0

    if 'position' in df.columns:
        df = df[~df['position'].str.upper().str.contains('GK', na=False)]

    conn = psycopg2.connect(**get_db_config())
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT id FROM leagues WHERE name = %s", (league_name,))
    league_id = cur.fetchone()[0]

    inserted = 0
    for _, row in df.iterrows():
        player = row.get('player', '')
        team_name = row.get('team', '')
        pos = row.get('position', '')

        if not player or not team_name:
            continue

        cur.execute("SELECT id FROM teams WHERE name = %s AND league_id = %s", (team_name, league_id))
        team_row = cur.fetchone()
        if team_row:
            team_id = team_row[0]
        else:
            cur.execute("INSERT INTO teams (name, league_id) VALUES (%s, %s) RETURNING id", (team_name, league_id))
            team_id = cur.fetchone()[0]

        cur.execute("SELECT id FROM players WHERE name = %s", (player,))
        player_row = cur.fetchone()
        if player_row:
            player_id = player_row[0]
        else:
            cur.execute("INSERT INTO players (name, position) VALUES (%s, %s) RETURNING id", (player, pos))
            player_id = cur.fetchone()[0]

        stats_values = [clean_value(row.get(f, None)) for f in STATS_FIELDS_SEASON]

        columns = ['player_id', 'team_id', 'season'] + STATS_FIELDS_SEASON
        placeholders = ['%s'] * len(columns)
        update_set = ', '.join([f"{col} = EXCLUDED.{col}" for col in STATS_FIELDS_SEASON])

        sql = f"""
            INSERT INTO player_stats ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT (player_id, team_id, season) DO UPDATE SET {update_set}
        """
        cur.execute(sql, [player_id, team_id, season] + stats_values)
        inserted += 1

    cur.close()
    conn.close()
    return inserted

def import_match_excel(uploaded_file_content, league_name, season, home_team, away_team, match_date, label, which_team='home'):
    try:
        df = pd.read_excel(io.BytesIO(uploaded_file_content), sheet_name='Основная статистика')
    except ValueError:
        xls = pd.ExcelFile(io.BytesIO(uploaded_file_content))
        first_sheet = xls.sheet_names[0]
        df = pd.read_excel(io.BytesIO(uploaded_file_content), sheet_name=first_sheet, header=0)
    df = df.dropna(subset=['№'])

    existing_renames = {k: v for k, v in RENAME_DICT_IMPORT.items() if k in df.columns}
    df = df.rename(columns=existing_renames)

    if 'player' not in df.columns:
        st.error("В файле нет колонки 'Player'. Импорт невозможен.")
        return None

    if which_team == 'home':
        df['team'] = home_team
    else:
        df['team'] = away_team

    if 'position' in df.columns:
        df = df[~df['position'].str.upper().str.contains('GK', na=False)]

    conn = psycopg2.connect(**get_db_config())
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT id FROM leagues WHERE name = %s", (league_name,))
    league_id = cur.fetchone()[0]

    def get_or_create_team(name):
        cur.execute("SELECT id FROM teams WHERE name = %s AND league_id = %s", (name, league_id))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("INSERT INTO teams (name, league_id) VALUES (%s, %s) RETURNING id", (name, league_id))
        return cur.fetchone()[0]

    home_id = get_or_create_team(home_team)
    away_id = get_or_create_team(away_team)

    cur.execute("""
        SELECT id FROM matches 
        WHERE season = %s AND league_id = %s AND home_team_id = %s AND away_team_id = %s 
          AND (label = %s OR (label IS NULL AND %s IS NULL))
    """, (season, league_id, home_id, away_id, label, label))
    match_row = cur.fetchone()
    if match_row:
        match_id = match_row[0]
    else:
        cur.execute("""
            INSERT INTO matches (season, league_id, home_team_id, away_team_id, match_date, label)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (season, league_id, home_id, away_id, match_date, label))
        match_id = cur.fetchone()[0]

    stats_fields_match = [f for f in STATS_FIELDS_SEASON if f != 'season']

    for _, row in df.iterrows():
        player_name = row.get('player', '')
        team_name = row.get('team', '')
        pos = row.get('position', '')

        if not player_name or not team_name:
            continue

        cur.execute("SELECT id FROM players WHERE name = %s", (player_name,))
        player_row = cur.fetchone()
        if player_row:
            player_id = player_row[0]
        else:
            cur.execute("INSERT INTO players (name, position) VALUES (%s, %s) RETURNING id", (player_name, pos))
            player_id = cur.fetchone()[0]

        team_id = get_or_create_team(team_name)
        stats_values = [clean_value(row.get(f, None)) for f in stats_fields_match]

        columns = ['match_id', 'player_id', 'team_id'] + stats_fields_match
        placeholders = ['%s'] * len(columns)
        update_set = ', '.join([f"{col} = EXCLUDED.{col}" for col in stats_fields_match])

        sql = f"""
            INSERT INTO match_player_stats ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT (match_id, player_id) DO UPDATE SET {update_set}
        """
        cur.execute(sql, [match_id, player_id, team_id] + stats_values)

    cur.close()
    conn.close()
    return match_id

# -------------------- ДИНАМИЧЕСКАЯ ЗАГРУЗКА СПИСКОВ --------------------
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
        return []

@st.cache_data(ttl=60)
def get_seasons_for_leagues(league_names):
    if not league_names:
        return []
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ps.season
            FROM player_stats ps
            JOIN teams t ON ps.team_id = t.id
            JOIN leagues l ON t.league_id = l.id
            WHERE l.name = ANY(%s)
            ORDER BY ps.season
        """, (league_names,))
        seasons = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return seasons
    except:
        return []

@st.cache_data(ttl=60)
def get_teams_for_leagues_seasons(league_names, seasons):
    if not league_names or not seasons:
        return []
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT t.name
            FROM teams t
            JOIN player_stats ps ON t.id = ps.team_id
            JOIN leagues l ON t.league_id = l.id
            WHERE l.name = ANY(%s) AND ps.season = ANY(%s)
            ORDER BY t.name
        """, (league_names, seasons))
        teams = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return teams
    except:
        return []

@st.cache_data(ttl=60)
def get_teams_for_league(league_name):
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("""
            SELECT t.name
            FROM teams t
            JOIN leagues l ON t.league_id = l.id
            WHERE l.name = %s
            ORDER BY t.name
        """, (league_name,))
        teams = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return teams
    except:
        return []

@st.cache_data(ttl=60)
def get_matches_for_league(league_name):
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("""
            SELECT m.id, m.label, l.name AS league, m.season,
                   ht.name AS home, at.name AS away, m.match_date
            FROM matches m
            JOIN leagues l ON m.league_id = l.id
            JOIN teams ht ON m.home_team_id = ht.id
            JOIN teams at ON m.away_team_id = at.id
            WHERE l.name = %s
            ORDER BY m.match_date DESC, m.id DESC
        """, (league_name,))
        matches = cur.fetchall()
        cur.close()
        conn.close()
        return matches
    except:
        return []

@st.cache_data(ttl=60)
def load_match_stats(match_id, team_ids=None):
    conn = psycopg2.connect(**get_db_config())
    query = """
    SELECT 
        p.name AS player, p.position,
        mps.minutes_played AS minutes,
        mps.goals, mps.assists, mps.shots, mps.shots_on_target,
        mps.goals_by_head, mps.free_kick_shots, mps.free_kick_goals,
        mps.shots_from_penalty_area, mps.shots_on_target_penalty_area,
        mps.shots_outside_penalty_area, mps.shots_on_target_outside_penalty_area,
        mps.headers, mps.headers_on_target,
        mps.xG,
        mps.key_passes, mps.passes, mps.pass_accuracy,
        mps.short_passes, mps.short_passes_accuracy,
        mps.long_passes, mps.long_passes_accuracy,
        mps.progressive_passes, mps.progressive_passes_accuracy,
        mps.passes_final_third, mps.passes_final_third_accuracy,
        mps.passes_into_penalty_box, mps.passes_into_penalty_box_accuracy,
        mps.super_long_passes, mps.super_long_passes_accuracy,
        mps.crosses, mps.crosses_accuracy,
        mps.passes_for_shot,
        mps.dribbles, mps.dribbles_success_pct,
        mps.dribbling_final_third, mps.dribbling_final_third_success_pct,
        mps.carry,
        mps.challenges, mps.challenges_won_pct,
        mps.defensive_challenges, mps.defensive_challenges_won_pct,
        mps.attacking_challenges, mps.attacking_challenges_won_pct,
        mps.air_challenges, mps.air_challenges_won_pct,
        mps.tackles, mps.tackles_success_pct,
        mps.interceptions,
        mps.loose_ball_recoveries,
        mps.actions_opp_box, mps.actions_opp_box_success,
        mps.chances, mps.chances_successful, mps.chances_created,
        mps.involvement_scoring,
        mps.shots_on_target_pct,
        mps.lost_balls, mps.lost_balls_own_half, mps.individual_ball_losses,
        mps.lost_balls_after_passes,
        mps.challenges_unsuccessful, mps.dribbles_unsuccessful,
        mps.bad_ball_control, mps.offsides,
        mps.mistakes_goals, mps.mistakes_chances,
        mps.fouls, mps.fouls_suffered,
        mps.yellow_cards, mps.red_cards,
        mps.ball_recoveries, mps.ball_recoveries_opp_half,
        mps.actions_successful, mps.actions_unsuccessful, mps.actions,
        mps.final_third_entries, mps.final_third_carry, mps.final_third_entries_pass,
        mps.open_passes_received, mps.long_open_passes_received,
        mps.super_long_open_passes_received,
        mps.open_passes_received_first_third, mps.open_passes_received_central_third,
        mps.open_passes_received_final_third, mps.open_passes_received_opponent_box,
        t.name AS team
    FROM match_player_stats mps
    JOIN players p ON mps.player_id = p.id
    JOIN teams t ON mps.team_id = t.id
    WHERE mps.match_id = %s
    """
    params = [match_id]
    if team_ids and len(team_ids) > 0:
        query += " AND mps.team_id = ANY(%s)"
        params.append(team_ids)
    df = pd.read_sql(query, conn, params=params)
    conn.close()

    df = df[~df['position'].str.upper().str.contains('GK', na=False)]

    pct_cols = [
        'pass_accuracy', 'dribbles_success_pct', 'tackles_success_pct',
        'crosses_accuracy', 'challenges_won_pct', 'air_challenges_won_pct',
        'progressive_passes_accuracy', 'passes_final_third_accuracy',
        'short_passes_accuracy', 'long_passes_accuracy',
        'passes_into_penalty_box_accuracy', 'super_long_passes_accuracy',
        'dribbling_final_third_success_pct', 'defensive_challenges_won_pct',
        'attacking_challenges_won_pct', 'shots_on_target_pct',
    ]
    for col in pct_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if df[col].max() <= 1.0:
                df[col] = df[col] * 100

    return df

# -------------------- ВИЗУАЛИЗАЦИЯ (Plotly) --------------------
def normalize_for_radar(df, metrics, player_row):
    normed = pd.Series(index=metrics, dtype=float)
    for m in metrics:
        col = df[m]
        mn, mx = col.min(), col.max()
        if mx - mn == 0:
            normed[m] = 0.5
        else:
            val = player_row[m]
            normed[m] = (val - mn) / (mx - mn)
        if m in NEGATIVE_METRICS:
            normed[m] = 1.0 - normed[m]
    return normed

def build_radar_labels(metrics, players, avg_series=None):
    labels = []
    for m in metrics:
        name = METRIC_NAMES_RU.get(m, m) if m.endswith('_p90') or m == 'pass_accuracy' else MATCH_METRIC_NAMES_RU.get(m, m)
        lines = [name]
        for p in players:
            val = p[m]
            if m.endswith('_pct') or m == 'pass_accuracy':
                detail = format_match_metric(m, val, p)
            else:
                detail = format_match_metric(m, val, p)
            lines.append(f"{p['player']}: {detail}")
        if avg_series is not None and m in avg_series:
            avg_val = avg_series[m]
            if m.endswith('_pct') or m == 'pass_accuracy':
                avg_detail = f"{avg_val:.2f}%"
            else:
                avg_detail = f"{avg_val:.2f}"
            lines.append(f"Средние: {avg_detail}")
        labels.append("<br>".join(lines))
    return labels

def add_average_trace(fig, radar_metrics, avg_values, labels, full_df):
    if avg_values is None:
        return
    norm_avg = normalize_for_radar(full_df, radar_metrics, pd.Series(avg_values, index=radar_metrics))
    values = norm_avg.tolist()
    fig.add_trace(go.Scatterpolar(
        r=values + values[:1],
        theta=labels + labels[:1],
        fill='toself',
        name='Средние',
        line=dict(color='#333333', dash='dash'),
        opacity=0.4,
    ))

def create_player_radar_figure(player_row, df, position_weights, avg_values=None):
    pos = get_position_group(player_row['position'])
    weights = position_weights.get(pos, {})
    sorted_metrics = sorted(weights.items(), key=lambda x: -abs(x[1]))
    radar_metrics = [m for m, _ in sorted_metrics if m in df.columns][:8]
    if not radar_metrics:
        radar_metrics = [c for c in df.columns if c.endswith('_p90') or c.endswith('_pct') or c in MATCH_ALL_METRICS][:8]

    labels = build_radar_labels(radar_metrics, [player_row], avg_series=avg_values)
    values = normalize_for_radar(df, radar_metrics, player_row).tolist()

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values + values[:1],
        theta=labels + labels[:1],
        fill='toself',
        name=player_row['player'],
        line_color='blue',
    ))
    if avg_values is not None:
        add_average_trace(fig, radar_metrics, avg_values, labels, df)

    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0, 1], showticklabels=False)),
        showlegend=True,
        height=600, width=600,
        margin=dict(l=120, r=120, t=80, b=120),
    )
    return fig

def create_compare_figure(p1, p2, radar_metrics, full_df, avg_values=None):
    players = [p1, p2]
    labels = build_radar_labels(radar_metrics, players, avg_series=avg_values)

    vals1 = normalize_for_radar(full_df, radar_metrics, p1).tolist()
    vals2 = normalize_for_radar(full_df, radar_metrics, p2).tolist()

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals1 + vals1[:1],
        theta=labels + labels[:1],
        fill='toself',
        name=f'{p1["player"]} ({p1["rating"]:.1f})',
        line_color='blue', opacity=0.6,
    ))
    fig.add_trace(go.Scatterpolar(
        r=vals2 + vals2[:1],
        theta=labels + labels[:1],
        fill='toself',
        name=f'{p2["player"]} ({p2["rating"]:.1f})',
        line_color='red', opacity=0.6,
    ))
    if avg_values is not None:
        add_average_trace(fig, radar_metrics, avg_values, labels, full_df)

    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0, 1], showticklabels=False)),
        showlegend=True,
        height=650, width=650,
        margin=dict(l=120, r=120, t=80, b=120),
        title="Сравнение игроков",
    )
    return fig

def create_position_radar(players_data, full_df, pos_metrics, colors, avg_values=None):
    fig = go.Figure()
    labels = build_radar_labels(pos_metrics[:8], players_data, avg_series=avg_values)

    for i, player_row in enumerate(players_data):
        values = normalize_for_radar(full_df, pos_metrics[:8], player_row).tolist()
        color = colors[i % len(colors)]
        fig.add_trace(go.Scatterpolar(
            r=values + values[:1],
            theta=labels + labels[:1],
            fill='toself',
            name=player_row['player'],
            line_color=color,
            opacity=0.6,
        ))
    if avg_values is not None:
        add_average_trace(fig, pos_metrics[:8], avg_values, labels, full_df)

    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0, 1], showticklabels=False)),
        showlegend=True,
        height=900, width=900,
        margin=dict(l=120, r=120, t=80, b=120),
        title="Сравнение по позиции",
    )
    return fig

# -------------------- ПОЛУЧЕНИЕ СРЕДНИХ ХАРАКТЕРИСТИК --------------------
def get_average_series(radar_metrics, full_df):
    avg_source = st.session_state.get('avg_source', 'Текущие данные')
    if avg_source == 'Текущие данные' and full_df is not None:
        return full_df[radar_metrics].mean()
    elif avg_source == 'Лига из БД':
        league = st.session_state.get('avg_league')
        season = st.session_state.get('avg_season')
        if league and season:
            df_league = load_from_db([league], [season])
            if df_league is not None and not df_league.empty:
                df_league = df_league[df_league['minutes'] >= MIN_MINUTES]
                if not df_league.empty:
                    return df_league[radar_metrics].mean()
    return None

# -------------------- ИНТЕРФЕЙС STREAMLIT --------------------
st.set_page_config(page_title="InStat Analyst", layout="wide")
st.title("Анализ футболистов InStat")

if 'df_db' not in st.session_state:
    st.session_state.df_db = None
if 'df_matches' not in st.session_state:
    st.session_state.df_matches = {}
if 'position_tables' not in st.session_state:
    st.session_state.position_tables = {}
if 'current_settings' not in st.session_state:
    st.session_state.current_settings = load_settings()
if 'selected_main_metrics' not in st.session_state:
    st.session_state.selected_main_metrics = []
if 'avg_source' not in st.session_state:
    st.session_state.avg_source = 'Текущие данные'
if 'avg_league' not in st.session_state:
    st.session_state.avg_league = None
if 'avg_season' not in st.session_state:
    st.session_state.avg_season = None
if 'match_compare_league' not in st.session_state:
    st.session_state.match_compare_league = None
if 'match_compare_season' not in st.session_state:
    st.session_state.match_compare_season = None

with st.sidebar:
    st.header("📤 Импорт Excel")
    uploaded_file = st.file_uploader("Excel-файл", type="xlsx", key="import_excel")
    if uploaded_file:
        import_type = st.radio("Тип данных", ["Сезон", "Матч"], key="import_type")
        if import_type == "Сезон":
            existing_leagues = get_leagues()
            if not existing_leagues:
                st.error("Нет доступных лиг в БД.")
            else:
                import_league = st.selectbox("Лига", existing_leagues, key="season_league_select")
                import_season = st.text_input("Сезон (например, 2024/2025)", key="import_season")
                if st.button("Загрузить сезон в БД", use_container_width=True):
                    if not import_season.strip():
                        st.error("Введите название сезона")
                    else:
                        with st.spinner("Импорт сезона..."):
                            cnt = import_season_excel(uploaded_file.getvalue(), import_league.strip(), import_season.strip())
                            if cnt:
                                st.success(f"Импортировано {cnt} игроков")
                            else:
                                st.error("Импорт не удался")
        else:  # Матч
            existing_leagues = get_leagues()
            if not existing_leagues:
                st.error("Нет доступных лиг в БД.")
            else:
                match_league = st.selectbox("Лига", existing_leagues, key="match_league_select")
                seasons_in_league = get_seasons_for_leagues([match_league])
                if not seasons_in_league:
                    st.warning("В выбранной лиге нет сезонов.")
                    match_season = None
                else:
                    match_season = st.selectbox("Сезон", seasons_in_league, key="match_season_select")
                teams_in_league = get_teams_for_league(match_league)
                if not teams_in_league:
                    st.error("В выбранной лиге нет команд.")
                else:
                    home_team = st.selectbox("Домашняя команда", teams_in_league, key="home_team_select")
                    away_team = st.selectbox("Гостевая команда", teams_in_league, key="away_team_select")

                    team_to_load = st.radio("Какую команду загружаем?", ["Только хозяев", "Только гостей"], key="match_team_load")
                    match_date = st.date_input("Дата матча", value=None, key="match_date")
                    match_label = st.text_input("Метка матча (необязательно)", key="match_label")
                    if st.button("Загрузить матч в БД", use_container_width=True):
                        if not match_season:
                            st.error("Сезон не выбран")
                        else:
                            with st.spinner("Импорт матча..."):
                                team_arg = 'home' if team_to_load == "Только хозяев" else 'away'
                                try:
                                    mid = import_match_excel(uploaded_file.getvalue(), match_league.strip(), match_season.strip(),
                                                            home_team.strip(), away_team.strip(),
                                                            match_date, match_label.strip() if match_label else None,
                                                            which_team=team_arg)
                                    if mid:
                                        st.success(f"Матч #{mid} загружен")
                                    else:
                                        st.error("Не удалось импортировать матч")
                                except Exception as e:
                                    st.error(f"Ошибка импорта матча: {e}")

    st.header("📊 Сезонная статистика")
    leagues_list = get_leagues()
    if not leagues_list:
        st.warning("Нет лиг в базе")
        selected_leagues = []
    else:
        selected_leagues = st.multiselect("Лиги", leagues_list, key="league_db")
    if selected_leagues:
        seasons_list = get_seasons_for_leagues(selected_leagues)
        if not seasons_list:
            st.warning("Нет сезонов")
            selected_seasons = []
        else:
            selected_seasons = st.multiselect("Сезоны", seasons_list, key="season_db")
    else:
        selected_seasons = []
    if selected_leagues and selected_seasons:
        teams_list = get_teams_for_leagues_seasons(selected_leagues, selected_seasons)
        if teams_list:
            selected_teams = st.multiselect("Команды", teams_list, key="teams_db")
        else:
            selected_teams = []
    else:
        selected_teams = []
    if selected_leagues and selected_seasons:
        if st.button("Загрузить сезонные данные", use_container_width=True):
            with st.spinner("Запрос..."):
                teams_param = None if len(selected_teams) == 0 else selected_teams
                df_raw = load_from_db(selected_leagues, selected_seasons, teams_param)
                total = len(df_raw)
                df_filtered = df_raw[df_raw['minutes'] >= MIN_MINUTES].copy()
                if len(df_filtered) == 0:
                    st.error("Нет игроков с достаточным временем")
                else:
                    df_filtered = calculate_ratings(df_filtered, st.session_state.current_settings)
                    df_filtered = df_filtered.sort_values('rating', ascending=False).reset_index(drop=True)
                    st.session_state.df_db = df_filtered
                    st.session_state.position_tables = build_position_tables(df_filtered, st.session_state.current_settings)
                    st.session_state.pop('position_compare_params', None)
                    st.success(f"Загружено {len(df_filtered)} игроков")
    else:
        st.info("Выберите лигу и сезон")

    st.header("⚽ Матчевая статистика")
    all_leagues = get_leagues()
    if not all_leagues:
        st.warning("Нет лиг в базе")
    else:
        match_league_analysis = st.selectbox("Лига", all_leagues, key="match_analysis_league")
        matches_in_league = get_matches_for_league(match_league_analysis)
        if not matches_in_league:
            st.info("Нет матчей в выбранной лиге")
        else:
            match_options = [f"#{m[0]} {m[1]} ({m[3]}) {m[4]} vs {m[5]}" for m in matches_in_league]
            selected_matches_labels = st.multiselect("Выберите матчи", match_options, key="match_multiselect")
            if selected_matches_labels:
                teams_in_league = get_teams_for_league(match_league_analysis)
                team_choice = st.radio("Команда", ["Обе", "Хозяева", "Гости"], key="match_team_choice")
                if st.button("Загрузить матчи", use_container_width=True):
                    with st.spinner("Загрузка матчей..."):
                        new_matches = {}
                        for label in selected_matches_labels:
                            match_id = int(label.split()[0][1:])
                            match_info = next(m for m in matches_in_league if m[0] == match_id)
                            home_team = match_info[4]
                            away_team = match_info[5]
                            team_ids = None
                            if team_choice == "Хозяева":
                                conn = psycopg2.connect(**get_db_config())
                                cur = conn.cursor()
                                cur.execute("SELECT id FROM teams WHERE name = %s", (home_team,))
                                tid = cur.fetchone()
                                if tid: team_ids = [tid[0]]
                                cur.close()
                                conn.close()
                            elif team_choice == "Гости":
                                conn = psycopg2.connect(**get_db_config())
                                cur = conn.cursor()
                                cur.execute("SELECT id FROM teams WHERE name = %s", (away_team,))
                                tid = cur.fetchone()
                                if tid: team_ids = [tid[0]]
                                cur.close()
                                conn.close()
                            df_match = load_match_stats(match_id, team_ids)
                            if not df_match.empty:
                                df_match['league'] = 'match'
                                df_match = calculate_match_ratings(df_match, DEFAULT_MATCH_WEIGHTS)
                                df_match = df_match.sort_values('rating', ascending=False).reset_index(drop=True)
                                new_matches[match_id] = {
                                    'df': df_match,
                                    'label': label,
                                    'league': match_info[2],
                                    'season': match_info[3],
                                }
                        if new_matches:
                            st.session_state.df_matches = new_matches
                            st.success(f"Загружено {len(new_matches)} матчей")
                        else:
                            st.warning("Нет данных по выбранным матчам")

    # Настройки сравнения для матчей
    if st.session_state.df_matches:
        st.header("📊 Сравнение с лигой")
        compare_league = st.selectbox("Лига для сравнения", all_leagues,
                                      index=all_leagues.index(match_league_analysis) if match_league_analysis in all_leagues else 0,
                                      key="compare_league")
        if compare_league:
            seasons_compare = get_seasons_for_leagues([compare_league])
            # По умолчанию берём сезон первого загруженного матча или любой доступный
            default_season = list(st.session_state.df_matches.values())[0]['season'] if st.session_state.df_matches else None
            if default_season and default_season in seasons_compare:
                default_idx = seasons_compare.index(default_season)
            else:
                default_idx = 0
            compare_season = st.selectbox("Сезон для сравнения", seasons_compare, index=default_idx, key="compare_season")
            if st.button("Применить сравнение", use_container_width=True):
                st.session_state.match_compare_league = compare_league
                st.session_state.match_compare_season = compare_season
                st.success("Сравнение обновлено")
        else:
            st.session_state.match_compare_league = None
            st.session_state.match_compare_season = None

    # Настройки весов (общие)
    st.header("⚙️ Веса")
    if st.button("Редактор весов", use_container_width=True):
        st.session_state.show_weights_editor = True
    if st.button("Сбросить веса", use_container_width=True):
        st.session_state.current_settings = {pos: w.copy() for pos, w in DEFAULT_METRICS_WEIGHTS.items()}
        save_settings(st.session_state.current_settings)
        st.cache_data.clear()
        st.success("Веса сброшены")
        if st.session_state.df_db is not None:
            st.session_state.df_db = calculate_ratings(st.session_state.df_db, st.session_state.current_settings)
            st.session_state.position_tables = build_position_tables(st.session_state.df_db, st.session_state.current_settings)
        for mid, data in st.session_state.df_matches.items():
            data['df'] = calculate_match_ratings(data['df'], DEFAULT_MATCH_WEIGHTS)

    st.header("📊 Средние")
    avg_source = st.radio("Источник", ["Текущие данные", "Лига из БД"], key="avg_source")
    if avg_source == "Лига из БД":
        avg_league = st.selectbox("Лига для средних", get_leagues(), key="avg_league")
        if avg_league:
            avg_seasons = get_seasons_for_leagues([avg_league])
            avg_season = st.selectbox("Сезон", avg_seasons, key="avg_season") if avg_seasons else None
        else:
            avg_season = None
    else:
        avg_league = None; avg_season = None

# -------------------- ОСНОВНАЯ ОБЛАСТЬ (ВКЛАДКИ) --------------------
tab_season, tab_match = st.tabs(["📈 Сезон", "⚽ Матч"])

with tab_season:
    if st.session_state.df_db is not None:
        df_active = st.session_state.df_db
        position_tables_active = st.session_state.position_tables

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

        subtabs = st.tabs(["Общий рейтинг", "FW", "AM", "CM", "FB", "CB"])

        with subtabs[0]:
            df_main = build_main_table(df_active, selected_metrics)
            st.dataframe(df_main, height=600, use_container_width=True, on_select="rerun", selection_mode="single-row", key="main_table")
            if "main_table" in st.session_state and st.session_state.main_table.selection.rows:
                idx = next(iter(st.session_state.main_table.selection.rows))
                if idx < len(df_active):
                    player_row = df_active.iloc[idx]
                    col1, col2, col3 = st.columns([1, 2, 1])
                    pos = get_position_group(player_row['position'])
                    weights = st.session_state.current_settings.get(pos, {})
                    sorted_metrics = sorted(weights.items(), key=lambda x: -abs(x[1]))
                    radar_metrics = [m for m, _ in sorted_metrics if m in df_active.columns][:8]
                    if not radar_metrics:
                        radar_metrics = [c for c in df_active.columns if c.endswith('_p90') or c.endswith('_pct')][:8]
                    avg_series = get_average_series(radar_metrics, df_active)
                    with col2:
                        fig = create_player_radar_figure(player_row, df_active, st.session_state.current_settings, avg_values=avg_series)
                        st.plotly_chart(fig, use_container_width=True)

        for i, pos in enumerate(['FW','AM','CM','FB','CB'], 1):
            with subtabs[i]:
                rows, headers = position_tables_active.get(pos, ([], []))
                if rows:
                    numbered_rows = [[j+1] + row for j, row in enumerate(rows)]
                    df_pos = pd.DataFrame(numbered_rows, columns=['№'] + headers)
                    st.dataframe(df_pos, height=400, use_container_width=True, on_select="rerun", selection_mode="single-row", key=f"table_{pos}")
                    state_key = f"table_{pos}"
                    if state_key in st.session_state and st.session_state[state_key].selection.rows:
                        idx = next(iter(st.session_state[state_key].selection.rows))
                        if idx < len(rows):
                            player_name = rows[idx][0]
                            player_min = int(rows[idx][1])
                            candidate = df_active[(df_active['player'] == player_name) & (df_active['minutes'] == player_min)]
                            if not candidate.empty:
                                player_row = candidate.iloc[0]
                                pos_group = get_position_group(player_row['position'])
                                weights = st.session_state.current_settings.get(pos_group, {})
                                sorted_metrics = sorted(weights.items(), key=lambda x: -abs(x[1]))
                                radar_metrics = [m for m, _ in sorted_metrics if m in df_active.columns][:8]
                                if not radar_metrics:
                                    radar_metrics = [c for c in df_active.columns if c.endswith('_p90') or c.endswith('_pct')][:8]
                                avg_series = get_average_series(radar_metrics, df_active)
                                col1, col2, col3 = st.columns([1, 2, 1])
                                with col2:
                                    fig = create_player_radar_figure(player_row, df_active, st.session_state.current_settings, avg_values=avg_series)
                                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info(f"Нет игроков позиции {pos}")

        if st.button("📥 Экспорт в Excel", key="export_season"):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_main = build_main_table(df_active, selected_metrics)
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
            st.download_button(label="Скачать Excel", data=output.getvalue(), file_name="season_players_rating.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Загрузите сезонные данные (в боковой панели)")

with tab_match:
    if st.session_state.df_matches:
        # Получаем средние по лиге и сезонные данные игроков, если выбрано сравнение
        avg_series = None
        season_df = None
        if st.session_state.match_compare_league and st.session_state.match_compare_season:
            avg_series = get_league_averages(st.session_state.match_compare_league, st.session_state.match_compare_season)
            season_df = get_player_season_stats_df(st.session_state.match_compare_league, st.session_state.match_compare_season)
            if season_df is not None:
                # Отфильтруем только нужных игроков? Нет, load_from_db возвращает всех, это ок.
                pass

        match_ids = list(st.session_state.df_matches.keys())
        match_labels = [st.session_state.df_matches[mid]['label'] for mid in match_ids]
        selected_label = st.selectbox("Активный матч", match_labels, key="active_match_selector")
        active_match_id = None
        for mid, data in st.session_state.df_matches.items():
            if data['label'] == selected_label:
                active_match_id = mid
                break

        if active_match_id is not None:
            df_active = st.session_state.df_matches[active_match_id]['df']

            all_metrics = [m for m in MATCH_ALL_METRICS if m in df_active.columns]
            metric_names = {m: MATCH_METRIC_NAMES_RU.get(m, m) for m in all_metrics}
            with st.expander("Настройка колонок общей таблицы"):
                selected_metrics = st.multiselect(
                    "Выберите до 5 метрик для отображения",
                    options=all_metrics,
                    format_func=lambda m: metric_names[m],
                    default=all_metrics[:3],
                    max_selections=5,
                    key="match_main_metrics_selector"
                )
            if not selected_metrics:
                selected_metrics = all_metrics[:3]

            subtabs = st.tabs(["Общий рейтинг", "FW", "AM", "CM", "FB", "CB"])

            with subtabs[0]:
                df_main = build_match_main_table(df_active, selected_metrics, avg_series=avg_series, season_df=season_df)
                # Используем HTML-рендеринг, так как у нас есть HTML-стили
                st.write(df_main.to_html(escape=False, index=False), unsafe_allow_html=True)
                # Оставляем возможность клика для радара (придётся использовать другой подход, пока пропустим)

            for i, pos in enumerate(['FW','AM','CM','FB','CB'], 1):
                with subtabs[i]:
                    pos_tables = build_match_position_tables(df_active, DEFAULT_MATCH_WEIGHTS, avg_series=avg_series, season_df=season_df)
                    rows, headers = pos_tables.get(pos, ([], []))
                    if rows:
                        numbered_rows = [[j+1] + row for j, row in enumerate(rows)]
                        df_pos = pd.DataFrame(numbered_rows, columns=['№'] + headers)
                        st.write(df_pos.to_html(escape=False, index=False), unsafe_allow_html=True)
                    else:
                        st.info(f"Нет игроков позиции {pos}")

            if st.button("📥 Экспорт в Excel", key="export_match"):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_main = build_match_main_table(df_active, selected_metrics, avg_series=avg_series, season_df=season_df)
                    df_main.to_excel(writer, sheet_name='Общий рейтинг', index=False)
                    for pos, (rows, headers) in build_match_position_tables(df_active, DEFAULT_MATCH_WEIGHTS, avg_series=avg_series, season_df=season_df).items():
                        if rows:
                            df_pos = pd.DataFrame(rows, columns=headers)
                            df_pos.to_excel(writer, sheet_name=pos, index=False)
                st.download_button(label="Скачать Excel", data=output.getvalue(), file_name="match_players_rating.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Загрузите матчи (в боковой панели)")

# -------------------- РЕДАКТОР ВЕСОВ --------------------
if st.session_state.get('show_weights_editor'):
    with st.expander("Редактор весов метрик", expanded=True):
        positions_order = ['FW', 'AM', 'CM', 'FB', 'CB']
        pos_names = {'FW':'Нападающие','AM':'Атак. полузащитники','CM':'Центр. полузащитники','FB':'Крайние защитники','CB':'Центр. защитники'}
        active_df = st.session_state.df_db if st.session_state.df_db is not None else (
            list(st.session_state.df_matches.values())[0]['df'] if st.session_state.df_matches else None
        )
        if active_df is not None:
            available_metrics = [m for m in ALL_POSSIBLE_METRICS if m in active_df.columns]
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
                if st.session_state.df_db is not None:
                    st.session_state.df_db = calculate_ratings(st.session_state.df_db, new_weights)
                    st.session_state.position_tables = build_position_tables(st.session_state.df_db, new_weights)
                for mid, data in st.session_state.df_matches.items():
                    data['df'] = calculate_match_ratings(data['df'], DEFAULT_MATCH_WEIGHTS)
                st.rerun()
        with col2:
            if st.button("Отмена", use_container_width=True, key="cancel_weights"):
                st.session_state.show_weights_editor = False
                st.rerun()
