import os
import pandas as pd
import numpy as np
import psycopg2
from dotenv import load_dotenv
import streamlit as st

from config import MIN_MINUTES, MATCH_ALL_METRICS
from utils import clean_value

load_dotenv()

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
    "Actions in opponent's box": 'actions_opp_box',
    "Actions in opponent's box successful": 'actions_opp_box_success',
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
    "Ball recoveries in opponent's half": 'ball_recoveries_opp_half',
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
    "Open passes received in the opponent's box": 'open_passes_received_opponent_box',
}

STATS_FIELDS_SEASON = [v for k, v in RENAME_DICT_IMPORT.items() if k not in ['Player', 'Position']]

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
def load_from_db(league_names, seasons, teams=None):
    conn = psycopg2.connect(**get_db_config())
    # Базовый запрос с COALESCE для всех метрик, кроме p90 (они вычисляются позже)
    # Перечислим все колонки, которые ожидаем
    base_cols = [
        'ps.goals', 'ps.assists', 'ps.shots', 'ps.shots_on_target',
        'ps.goals_by_head', 'ps.free_kick_shots', 'ps.free_kick_goals',
        'ps.shots_from_penalty_area', 'ps.shots_on_target_penalty_area',
        'ps.shots_outside_penalty_area', 'ps.shots_on_target_outside_penalty_area',
        'ps.headers', 'ps.headers_on_target',
        'ps.xG', 'ps.key_passes', 'ps.passes', 'ps.pass_accuracy',
        'ps.short_passes', 'ps.short_passes_accuracy',
        'ps.long_passes', 'ps.long_passes_accuracy',
        'ps.progressive_passes', 'ps.progressive_passes_accuracy',
        'ps.passes_final_third', 'ps.passes_final_third_accuracy',
        'ps.passes_into_penalty_box', 'ps.passes_into_penalty_box_accuracy',
        'ps.super_long_passes', 'ps.super_long_passes_accuracy',
        'ps.crosses', 'ps.crosses_accuracy',
        'ps.passes_for_shot',
        'ps.dribbles', 'ps.dribbles_success_pct',
        'ps.dribbling_final_third', 'ps.dribbling_final_third_success_pct',
        'ps.carry',
        'ps.challenges', 'ps.challenges_won_pct',
        'ps.defensive_challenges', 'ps.defensive_challenges_won_pct',
        'ps.attacking_challenges', 'ps.attacking_challenges_won_pct',
        'ps.air_challenges', 'ps.air_challenges_won_pct',
        'ps.tackles', 'ps.tackles_success_pct',
        'ps.interceptions',
        'ps.loose_ball_recoveries',
        'ps.actions_opp_box', 'ps.actions_opp_box_success',
        'ps.chances', 'ps.chances_successful', 'ps.chances_created',
        'ps.involvement_scoring',
        'ps.shots_on_target_pct',
        'ps.lost_balls', 'ps.lost_balls_own_half', 'ps.individual_ball_losses',
        'ps.lost_balls_after_passes',
        'ps.challenges_unsuccessful', 'ps.dribbles_unsuccessful',
        'ps.bad_ball_control', 'ps.offsides',
        'ps.mistakes_goals', 'ps.mistakes_chances',
        'ps.fouls', 'ps.fouls_suffered',
        'ps.yellow_cards', 'ps.red_cards',
        'ps.ball_recoveries', 'ps.ball_recoveries_opp_half',
        'ps.actions_successful', 'ps.actions_unsuccessful', 'ps.actions',
        'ps.final_third_entries', 'ps.final_third_carry', 'ps.final_third_entries_pass',
        'ps.open_passes_received', 'ps.long_open_passes_received',
        'ps.super_long_open_passes_received',
        'ps.open_passes_received_first_third', 'ps.open_passes_received_central_third',
        'ps.open_passes_received_final_third', 'ps.open_passes_received_opponent_box',
        'ps.matches_played', 'ps.starting_lineup'
    ]
    # Формируем SELECT с COALESCE для каждой колонки (чтобы избежать NULL)
    select_parts = [
        "p.name AS player", "p.position", "ps.minutes_played AS minutes",
        "t.name AS team", "l.name AS league"
    ]
    for col in base_cols:
        # Убираем префикс ps.
        col_name = col.split('.')[-1]
        select_parts.append(f"COALESCE({col}, 0) AS {col_name}")
    select_clause = ",\n        ".join(select_parts)

    query = f"""
    SELECT 
        {select_clause}
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

    # Убираем вратарей
    df = df[~df['position'].str.upper().str.contains('GK', na=False)]

    # Преобразуем проценты (если значения <=1, умножаем на 100)
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

    # Вычисляем p90 метрики
    minutes = df['minutes'].values
    base_metrics = ['goals', 'assists', 'shots', 'shots_on_target', 'goals_by_head',
                    'free_kick_shots', 'free_kick_goals', 'shots_from_penalty_area',
                    'shots_on_target_penalty_area', 'shots_outside_penalty_area',
                    'shots_on_target_outside_penalty_area', 'headers', 'headers_on_target',
                    'xG', 'key_passes', 'passes', 'short_passes', 'long_passes',
                    'progressive_passes', 'passes_final_third', 'passes_into_penalty_box',
                    'super_long_passes', 'crosses', 'passes_for_shot', 'dribbles',
                    'dribbling_final_third', 'carry', 'challenges', 'defensive_challenges',
                    'attacking_challenges', 'air_challenges', 'tackles', 'interceptions',
                    'loose_ball_recoveries', 'actions_opp_box', 'actions_opp_box_success',
                    'chances', 'chances_successful', 'chances_created', 'involvement_scoring',
                    'lost_balls', 'lost_balls_own_half', 'individual_ball_losses',
                    'lost_balls_after_passes', 'challenges_unsuccessful', 'dribbles_unsuccessful',
                    'bad_ball_control', 'offsides', 'mistakes_goals', 'mistakes_chances',
                    'fouls', 'fouls_suffered', 'yellow_cards', 'red_cards', 'ball_recoveries',
                    'ball_recoveries_opp_half', 'actions_successful', 'actions_unsuccessful', 'actions',
                    'final_third_entries', 'final_third_carry', 'final_third_entries_pass',
                    'open_passes_received', 'long_open_passes_received', 'super_long_open_passes_received',
                    'open_passes_received_first_third', 'open_passes_received_central_third',
                    'open_passes_received_final_third', 'open_passes_received_opponent_box']
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
    base_cols = [
        'mps.goals', 'mps.assists', 'mps.shots', 'mps.shots_on_target',
        'mps.goals_by_head', 'mps.free_kick_shots', 'mps.free_kick_goals',
        'mps.shots_from_penalty_area', 'mps.shots_on_target_penalty_area',
        'mps.shots_outside_penalty_area', 'mps.shots_on_target_outside_penalty_area',
        'mps.headers', 'mps.headers_on_target',
        'mps.xG', 'mps.key_passes', 'mps.passes', 'mps.pass_accuracy',
        'mps.short_passes', 'mps.short_passes_accuracy',
        'mps.long_passes', 'mps.long_passes_accuracy',
        'mps.progressive_passes', 'mps.progressive_passes_accuracy',
        'mps.passes_final_third', 'mps.passes_final_third_accuracy',
        'mps.passes_into_penalty_box', 'mps.passes_into_penalty_box_accuracy',
        'mps.super_long_passes', 'mps.super_long_passes_accuracy',
        'mps.crosses', 'mps.crosses_accuracy',
        'mps.passes_for_shot',
        'mps.dribbles', 'mps.dribbles_success_pct',
        'mps.dribbling_final_third', 'mps.dribbling_final_third_success_pct',
        'mps.carry',
        'mps.challenges', 'mps.challenges_won_pct',
        'mps.defensive_challenges', 'mps.defensive_challenges_won_pct',
        'mps.attacking_challenges', 'mps.attacking_challenges_won_pct',
        'mps.air_challenges', 'mps.air_challenges_won_pct',
        'mps.tackles', 'mps.tackles_success_pct',
        'mps.interceptions',
        'mps.loose_ball_recoveries',
        'mps.actions_opp_box', 'mps.actions_opp_box_success',
        'mps.chances', 'mps.chances_successful', 'mps.chances_created',
        'mps.involvement_scoring',
        'mps.shots_on_target_pct',
        'mps.lost_balls', 'mps.lost_balls_own_half', 'mps.individual_ball_losses',
        'mps.lost_balls_after_passes',
        'mps.challenges_unsuccessful', 'mps.dribbles_unsuccessful',
        'mps.bad_ball_control', 'mps.offsides',
        'mps.mistakes_goals', 'mps.mistakes_chances',
        'mps.fouls', 'mps.fouls_suffered',
        'mps.yellow_cards', 'mps.red_cards',
        'mps.ball_recoveries', 'mps.ball_recoveries_opp_half',
        'mps.actions_successful', 'mps.actions_unsuccessful', 'mps.actions',
        'mps.final_third_entries', 'mps.final_third_carry', 'mps.final_third_entries_pass',
        'mps.open_passes_received', 'mps.long_open_passes_received',
        'mps.super_long_open_passes_received',
        'mps.open_passes_received_first_third', 'mps.open_passes_received_central_third',
        'mps.open_passes_received_final_third', 'mps.open_passes_received_opponent_box'
    ]
    select_parts = [
        "p.name AS player", "p.position", "mps.minutes_played AS minutes",
        "t.name AS team"
    ]
    for col in base_cols:
        col_name = col.split('.')[-1]
        select_parts.append(f"COALESCE({col}, 0) AS {col_name}")
    select_clause = ",\n        ".join(select_parts)

    query = f"""
    SELECT 
        {select_clause}
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
       # Добавляем ТТД метрики для матча (аналог сезонных, но без пересчёта на 90 минут)
    if 'actions' in df.columns and 'actions_successful' in df.columns:
        df['ttd_actions'] = df.apply(
            lambda row: f"{int(row['actions_successful'])}/{int(row['actions'])}" if row['actions'] > 0 else "",
            axis=1
        )
    else:
        df['ttd_actions'] = ""
    if 'actions_opp_box' in df.columns and 'actions_opp_box_success' in df.columns:
        df['ttd_opp_actions'] = df.apply(
            lambda row: f"{int(row['actions_opp_box_success'])}/{int(row['actions_opp_box'])}" if row['actions_opp_box'] > 0 else "",
            axis=1
        )
    else:
        df['ttd_opp_actions'] = "" 
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

# Импорт из Excel
def import_season_excel(uploaded_file_content, league_name, season, team_column='Team'):
    import io
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
    import io
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
