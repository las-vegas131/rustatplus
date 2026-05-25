import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from config import MATCH_ALL_METRICS, MIN_MINUTES
import streamlit as st

load_dotenv()

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
        st.error(f"❌ Отсутствуют переменные окружения: {', '.join(missing)}. Добавьте их в файл `.env`.")
        st.stop()
    try:
        conn = psycopg2.connect(**get_db_config())
        conn.close()
    except Exception as e:
        st.error(f"❌ Не удалось подключиться к базе данных: {e}")
        st.stop()

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
    except:
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
def load_from_db(league_names, seasons, teams=None):
    conn = psycopg2.connect(**get_db_config())
    # Список всех метрик (без суффикса _p90)
    base_metrics = [
        'goals', 'assists', 'shots', 'shots_on_target', 'goals_by_head',
        'free_kick_shots', 'free_kick_goals', 'shots_from_penalty_area',
        'shots_on_target_penalty_area', 'shots_outside_penalty_area',
        'shots_on_target_outside_penalty_area', 'headers', 'headers_on_target',
        'xG', 'key_passes', 'passes', 'pass_accuracy', 'short_passes',
        'short_passes_accuracy', 'long_passes', 'long_passes_accuracy',
        'progressive_passes', 'progressive_passes_accuracy', 'passes_final_third',
        'passes_final_third_accuracy', 'passes_into_penalty_box',
        'passes_into_penalty_box_accuracy', 'super_long_passes',
        'super_long_passes_accuracy', 'crosses', 'crosses_accuracy',
        'passes_for_shot', 'dribbles', 'dribbles_success_pct',
        'dribbling_final_third', 'dribbling_final_third_success_pct', 'carry',
        'challenges', 'challenges_won_pct', 'defensive_challenges',
        'defensive_challenges_won_pct', 'attacking_challenges',
        'attacking_challenges_won_pct', 'air_challenges', 'air_challenges_won_pct',
        'tackles', 'tackles_success_pct', 'interceptions', 'loose_ball_recoveries',
        'actions_opp_box', 'actions_opp_box_success', 'chances', 'chances_successful',
        'chances_created', 'involvement_scoring', 'shots_on_target_pct',
        'lost_balls', 'lost_balls_own_half', 'individual_ball_losses',
        'lost_balls_after_passes', 'challenges_unsuccessful', 'dribbles_unsuccessful',
        'bad_ball_control', 'offsides', 'mistakes_goals', 'mistakes_chances',
        'fouls', 'fouls_suffered', 'yellow_cards', 'red_cards', 'ball_recoveries',
        'ball_recoveries_opp_half', 'actions', 'actions_successful', 'actions_unsuccessful',
        'final_third_entries', 'final_third_carry', 'final_third_entries_pass',
        'open_passes_received', 'long_open_passes_received', 'super_long_open_passes_received',
        'open_passes_received_first_third', 'open_passes_received_central_third',
        'open_passes_received_final_third', 'open_passes_received_opponent_box'
    ]
    # Формируем SELECT с COALESCE для каждой метрики, чтобы NULL заменялись на 0
    select_parts = [
        "p.name AS player", "p.position", "ps.minutes_played AS minutes",
        "t.name AS team", "l.name AS league"
    ]
    for col in base_metrics:
        select_parts.append(f"COALESCE(ps.{col}, 0) AS {col}")
    query = f"""
    SELECT {', '.join(select_parts)}
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

    # Исключаем вратарей
    df = df[~df['position'].str.upper().str.contains('GK', na=False)]

    # Процентные колонки могут быть в долях, преобразуем в проценты
    pct_cols = [col for col in df.columns if col.endswith('_pct') or col == 'pass_accuracy']
    for col in pct_cols:
        if df[col].max() <= 1.0:
            df[col] = df[col] * 100

    # Заполняем пропуски нулями (хотя COALESCE уже сделал)
    df = df.fillna(0)

    # Рассчитываем p90 для всех числовых метрик
    minutes = df['minutes'].values
    for col in base_metrics:
        if col in df.columns:
            df[f'{col}_p90'] = np.where(minutes > 0, (df[col] / minutes) * 90, 0)

    # Добавляем ТТД метрики
    if 'actions' in df.columns and 'actions_successful' in df.columns:
        df['ttd_actions_total'] = df['actions']
        df['ttd_actions_successful'] = df['actions_successful']
        df['ttd_actions_p90'] = np.where(minutes > 0, (df['ttd_actions_total'] / minutes) * 90, 0)
    if 'actions_opp_box' in df.columns and 'actions_opp_box_success' in df.columns:
        df['ttd_opp_actions_total'] = df['actions_opp_box']
        df['ttd_opp_actions_successful'] = df['actions_opp_box_success']
        df['ttd_opp_actions_p90'] = np.where(minutes > 0, (df['ttd_opp_actions_total'] / minutes) * 90, 0)

    return df

@st.cache_data(ttl=60)
def load_match_stats(match_id, team_ids=None):
    conn = psycopg2.connect(**get_db_config())
    base_metrics = [
        'goals', 'assists', 'shots', 'shots_on_target', 'goals_by_head',
        'free_kick_shots', 'free_kick_goals', 'shots_from_penalty_area',
        'shots_on_target_penalty_area', 'shots_outside_penalty_area',
        'shots_on_target_outside_penalty_area', 'headers', 'headers_on_target',
        'xG', 'key_passes', 'passes', 'pass_accuracy', 'short_passes',
        'short_passes_accuracy', 'long_passes', 'long_passes_accuracy',
        'progressive_passes', 'progressive_passes_accuracy', 'passes_final_third',
        'passes_final_third_accuracy', 'passes_into_penalty_box',
        'passes_into_penalty_box_accuracy', 'super_long_passes',
        'super_long_passes_accuracy', 'crosses', 'crosses_accuracy',
        'passes_for_shot', 'dribbles', 'dribbles_success_pct',
        'dribbling_final_third', 'dribbling_final_third_success_pct', 'carry',
        'challenges', 'challenges_won_pct', 'defensive_challenges',
        'defensive_challenges_won_pct', 'attacking_challenges',
        'attacking_challenges_won_pct', 'air_challenges', 'air_challenges_won_pct',
        'tackles', 'tackles_success_pct', 'interceptions', 'loose_ball_recoveries',
        'actions_opp_box', 'actions_opp_box_success', 'chances', 'chances_successful',
        'chances_created', 'involvement_scoring', 'shots_on_target_pct',
        'lost_balls', 'lost_balls_own_half', 'individual_ball_losses',
        'lost_balls_after_passes', 'challenges_unsuccessful', 'dribbles_unsuccessful',
        'bad_ball_control', 'offsides', 'mistakes_goals', 'mistakes_chances',
        'fouls', 'fouls_suffered', 'yellow_cards', 'red_cards', 'ball_recoveries',
        'ball_recoveries_opp_half', 'actions', 'actions_successful', 'actions_unsuccessful',
        'final_third_entries', 'final_third_carry', 'final_third_entries_pass',
        'open_passes_received', 'long_open_passes_received', 'super_long_open_passes_received',
        'open_passes_received_first_third', 'open_passes_received_central_third',
        'open_passes_received_final_third', 'open_passes_received_opponent_box'
    ]
    select_parts = [
        "p.name AS player", "p.position", "COALESCE(mps.minutes_played, 0) AS minutes", "t.name AS team"
    ]
    for col in base_metrics:
        select_parts.append(f"COALESCE(mps.{col}, 0) AS {col}")
    query = f"""
    SELECT {', '.join(select_parts)}
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

    pct_cols = [col for col in df.columns if col.endswith('_pct') or col == 'pass_accuracy']
    for col in pct_cols:
        if df[col].max() <= 1.0:
            df[col] = df[col] * 100

    df = df.fillna(0)
    return df

def get_league_averages(league_name, season):
    df = load_from_db([league_name], [season])
    df = df[df['minutes'] >= MIN_MINUTES]
    if df.empty:
        return {}
    avg = {}
    for m in MATCH_ALL_METRICS:
        p90_col = f'{m}_p90'
        if p90_col in df.columns:
            avg[m] = df[p90_col].mean()
    return avg

def get_player_season_stats_df(league_name, season):
    df = load_from_db([league_name], [season])
    if df.empty:
        return pd.DataFrame()
    cols = ['player'] + [f'{m}_p90' for m in MATCH_ALL_METRICS if f'{m}_p90' in df.columns]
    return df[cols]
