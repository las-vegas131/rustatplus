import streamlit as st
import pandas as pd
import io
import os
import plotly.graph_objects as go
from collections import defaultdict
import psycopg2

from config import (
    MIN_MINUTES, SETTINGS_FILE, SELECTED_METRICS_FILE,
    ALL_POSSIBLE_METRICS, DEFAULT_METRICS_WEIGHTS, DEFAULT_MATCH_WEIGHTS,
    METRIC_NAMES_RU, MATCH_METRIC_NAMES_RU, MATCH_ALL_METRICS, NEGATIVE_METRICS
)
from utils import (
    load_settings, save_settings, load_selected_metrics, save_selected_metrics,
    load_match_selected_metrics, save_match_selected_metrics
)
from db import (
    check_db_connection, get_leagues, get_seasons_for_leagues,
    get_teams_for_leagues_seasons, get_teams_for_league, get_matches_for_league,
    load_from_db, load_match_stats, get_league_averages, get_player_season_stats_df,
    import_season_excel, import_match_excel, get_db_config
)
from calculations import (
    calculate_ratings, calculate_match_ratings,
    build_position_tables, build_main_table,
    build_match_position_tables, build_match_main_table,
    get_position_group
)
from visualization import (
    create_player_radar_figure, create_compare_figure, create_position_radar,
    export_matches_advanced, export_match_standard_with_charts
)

st.set_page_config(page_title="InStat Analyst", layout="wide")

st.markdown("""
<style>
thead tr th {
    position: sticky !important;
    top: 0 !important;
    background-color: transparent !important;
    z-index: 1;
}
.match-table tbody tr, .match-table tbody td {
    background-color: transparent !important;
}
.stDataFrame tbody tr, .stDataFrame tbody td {
    background-color: transparent !important;
}
.match-table th {
    background-color: transparent !important;
}
</style>
""", unsafe_allow_html=True)

st.title("Анализ футболистов InStat")

# Инициализация session_state
if 'df_db' not in st.session_state:
    st.session_state.df_db = None
if 'df_matches' not in st.session_state:
    st.session_state.df_matches = {}
if 'position_tables' not in st.session_state:
    st.session_state.position_tables = {}
if 'current_settings' not in st.session_state:
    saved = load_settings(SETTINGS_FILE)
    if saved is not None:
        st.session_state.current_settings = saved
    else:
        st.session_state.current_settings = {pos: w.copy() for pos, w in DEFAULT_METRICS_WEIGHTS.items()}
if 'match_settings' not in st.session_state:
    st.session_state.match_settings = {pos: w.copy() for pos, w in DEFAULT_MATCH_WEIGHTS.items()}
if 'selected_main_metrics' not in st.session_state:
    saved = load_selected_metrics(SELECTED_METRICS_FILE)
    st.session_state.selected_main_metrics = saved if saved is not None else []
if 'match_selected_metrics' not in st.session_state:
    saved = load_match_selected_metrics()
    st.session_state.match_selected_metrics = saved if saved is not None else []
if 'avg_source' not in st.session_state:
    st.session_state.avg_source = 'Текущие данные'
if 'avg_league' not in st.session_state:
    st.session_state.avg_league = None
if 'avg_season' not in st.session_state:
    st.session_state.avg_season = None

# Боковая панель (импорт, загрузка и т.д.)
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
        else:
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
                st.subheader("📊 Сравнение с лигой")
                comp_league = st.selectbox("Лига для сравнения", all_leagues,
                                           index=all_leagues.index(match_league_analysis) if match_league_analysis in all_leagues else 0,
                                           key="comp_league")
                seasons_for_comp = get_seasons_for_leagues([comp_league])
                default_season_idx = 0
                if seasons_for_comp:
                    first_match_info = matches_in_league[0] if matches_in_league else None
                    if first_match_info:
                        try:
                            default_season_idx = seasons_for_comp.index(first_match_info[3])
                        except:
                            pass
                comp_season = st.selectbox("Сезон для сравнения", seasons_for_comp, index=default_season_idx, key="comp_season")
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
                                df_match = calculate_match_ratings(df_match, st.session_state.match_settings)
                                df_match = df_match.sort_values('rating', ascending=False).reset_index(drop=True)
                                new_matches[match_id] = {'df': df_match, 'label': label}
                        if new_matches:
                            st.session_state.df_matches = new_matches
                            league_avg = get_league_averages(comp_league, comp_season)
                            player_season_df = get_player_season_stats_df(comp_league, comp_season)
                            player_season_map = {}
                            if not player_season_df.empty:
                                for _, row in player_season_df.iterrows():
                                    player_dict = {}
                                    for m in MATCH_ALL_METRICS:
                                        p90_col = f'{m}_p90'
                                        if p90_col in row:
                                            player_dict[m] = row[p90_col]
                                    player_season_map[row['player']] = player_dict
                            st.session_state.match_tables = {}
                            for mid, data in new_matches.items():
                                df = data['df']
                                pos_tables = build_match_position_tables(df, st.session_state.match_settings,
                                                                          league_avg=league_avg,
                                                                          player_season_map=player_season_map)
                                st.session_state.match_tables[mid] = pos_tables
                            st.session_state.league_avg = league_avg
                            st.session_state.player_season_map = player_season_map
                            st.success(f"Загружено {len(new_matches)} матчей")
                        else:
                            st.warning("Нет данных по выбранным матчам")

    st.header("⚙️ Веса")
    if st.button("Редактор весов (сезон)", use_container_width=True):
        st.session_state.show_weights_editor = True
    if st.button("Редактор весов (матч)", use_container_width=True):
        st.session_state.show_match_weights_editor = True
    if st.button("Сбросить все веса", use_container_width=True):
        st.session_state.current_settings = {pos: w.copy() for pos, w in DEFAULT_METRICS_WEIGHTS.items()}
        st.session_state.match_settings = {pos: w.copy() for pos, w in DEFAULT_MATCH_WEIGHTS.items()}
        save_settings(st.session_state.current_settings, SETTINGS_FILE)
        st.cache_data.clear()
        st.success("Веса сброшены")
        if st.session_state.df_db is not None:
            st.session_state.df_db = calculate_ratings(st.session_state.df_db, st.session_state.current_settings)
            st.session_state.position_tables = build_position_tables(st.session_state.df_db, st.session_state.current_settings)
        for mid, data in st.session_state.df_matches.items():
            data['df'] = calculate_match_ratings(data['df'], st.session_state.match_settings)

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
        avg_league = None
        avg_season = None

# Основные вкладки
tab_season, tab_match = st.tabs(["📈 Сезон", "⚽ Матч"])

with tab_season:
    if st.session_state.df_db is not None:
        df_active = st.session_state.df_db
        position_tables_active = st.session_state.position_tables
        all_metrics = [m for m in ALL_POSSIBLE_METRICS if m in df_active.columns]
        mandatory_metrics = ['ttd_actions_p90', 'ttd_opp_actions_p90']
        selectable_metrics = [m for m in all_metrics if m not in mandatory_metrics]
        metric_names = {m: METRIC_NAMES_RU.get(m, m) for m in selectable_metrics}
        
        with st.expander("Настройка колонок общей таблицы"):
            saved = st.session_state.selected_main_metrics if st.session_state.selected_main_metrics else []
            default_selected = [m for m in saved if m in selectable_metrics]
            selected_optional = st.multiselect(
                "Выберите дополнительные метрики для отображения",
                options=selectable_metrics,
                format_func=lambda m: metric_names[m],
                default=default_selected,
                key="main_metrics_selector_optional"
            )
            selected_metrics = mandatory_metrics + selected_optional
            if selected_optional != saved:
                st.session_state.selected_main_metrics = selected_optional
                save_selected_metrics(selected_optional, SELECTED_METRICS_FILE)
        if not selected_metrics:
            selected_metrics = mandatory_metrics + all_metrics[:3]

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
                    avg_series = None
                    if st.session_state.avg_source == 'Текущие данные':
                        avg_series = df_active[radar_metrics].mean()
                    elif st.session_state.avg_source == 'Лига из БД' and st.session_state.avg_league and st.session_state.avg_season:
                        df_league = load_from_db([st.session_state.avg_league], [st.session_state.avg_season])
                        if not df_league.empty:
                            df_league = df_league[df_league['minutes'] >= MIN_MINUTES]
                            if not df_league.empty:
                                avg_series = df_league[radar_metrics].mean()
                    with col2:
                        fig = create_player_radar_figure(player_row, df_active, st.session_state.current_settings, avg_values=avg_series)
                        st.plotly_chart(fig, use_container_width=True, key=f"season_radar_main_{idx}")

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
                                avg_series = None
                                if st.session_state.avg_source == 'Текущие данные':
                                    avg_series = df_active[radar_metrics].mean()
                                elif st.session_state.avg_source == 'Лига из БД' and st.session_state.avg_league and st.session_state.avg_season:
                                    df_league = load_from_db([st.session_state.avg_league], [st.session_state.avg_season])
                                    if not df_league.empty:
                                        df_league = df_league[df_league['minutes'] >= MIN_MINUTES]
                                        if not df_league.empty:
                                            avg_series = df_league[radar_metrics].mean()
                                col1, col2, col3 = st.columns([1, 2, 1])
                                with col2:
                                    fig = create_player_radar_figure(player_row, df_active, st.session_state.current_settings, avg_values=avg_series)
                                    st.plotly_chart(fig, use_container_width=True, key=f"season_radar_{pos}_{player_name}")
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
    st.markdown("""
    <style>
    .match-table table { font-size: 12px; }
    .match-table th, .match-table td { font-size: 12px; white-space: nowrap; }
    </style>
    """, unsafe_allow_html=True)
    if st.session_state.df_matches:
        match_ids = list(st.session_state.df_matches.keys())
        match_labels = [st.session_state.df_matches[mid]['label'] for mid in match_ids]
        selected_label = st.selectbox("Активный матч", match_labels, key="active_match_selector")
        active_match_id = None
        for mid, data in st.session_state.df_matches.items():
            if data['label'] == selected_label:
                active_match_id = mid
                break
        if active_match_id is not None:
            df_active_full = st.session_state.df_matches[active_match_id]['df']
            min_minutes_filter = st.selectbox("Минимальное время игрока (минуты)", [10, 20, 30, 45], index=3, key="min_minutes_filter")
            df_active = df_active_full[df_active_full['minutes'] >= min_minutes_filter].copy()
            league_avg = st.session_state.get('league_avg')
            player_season_map = st.session_state.get('player_season_map')
            position_tables_active = build_match_position_tables(df_active, st.session_state.match_settings,
                                                                league_avg=league_avg,
                                                                player_season_map=player_season_map)
            all_metrics = [m for m in MATCH_ALL_METRICS if m in df_active.columns]
            ttd_metrics = ['ttd_actions', 'ttd_opp_actions']
            for tm in ttd_metrics:
                if tm in df_active.columns:
                    all_metrics.append(tm)
            mandatory_metrics = [tm for tm in ttd_metrics if tm in df_active.columns]
            selectable_metrics = [m for m in all_metrics if m not in mandatory_metrics]
            metric_names = {m: MATCH_METRIC_NAMES_RU.get(m, m) for m in selectable_metrics}
            
            with st.expander("Настройка колонок общей таблицы"):
                saved = st.session_state.match_selected_metrics if st.session_state.match_selected_metrics else []
                default_selected = [m for m in saved if m in selectable_metrics]
                selected_optional = st.multiselect(
                    "Выберите дополнительные метрики для отображения",
                    options=selectable_metrics,
                    format_func=lambda m: metric_names[m],
                    default=default_selected,
                    key="match_main_metrics_selector_optional"
                )
                selected_metrics = mandatory_metrics + selected_optional
                if selected_optional != saved:
                    st.session_state.match_selected_metrics = selected_optional
                    save_match_selected_metrics(selected_optional)
            if not selected_metrics:
                selected_metrics = mandatory_metrics + [m for m in all_metrics[:3] if m not in mandatory_metrics]
            subtabs = st.tabs(["Общий рейтинг", "FW", "AM", "CM", "FB", "CB"])
            st.markdown("""
            <div style="font-size:13px; margin-bottom:8px; line-height:1.6;">
            <b>Обозначения:</b><br>
            🟢 – лучший в команде &nbsp;&nbsp; 🔴 – худший в команде<br>
            🔵 – выше среднего по лиге &nbsp;&nbsp; 🟤 – ниже среднего по лиге<br>
            (↑) – в матче лучше своего среднего за сезон &nbsp;&nbsp; (↓) – хуже своего среднего
            </div>
            """, unsafe_allow_html=True)

            with subtabs[0]:
                df_main = build_match_main_table(df_active, selected_metrics,
                                                league_avg=league_avg,
                                                player_season_map=player_season_map)
                st.write(f'<div class="match-table">{df_main.to_html(escape=False, index=False)}</div>', unsafe_allow_html=True)
                player_list = df_active['player'].tolist()
                selected_player = st.selectbox("Выберите игрока для радара", player_list, key="match_radar_main_select")
                if selected_player:
                    player_row = df_active[df_active['player'] == selected_player].iloc[0]
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col2:
                        fig = create_player_radar_figure(player_row, df_active, st.session_state.match_settings, avg_values=league_avg)
                        st.plotly_chart(fig, use_container_width=True, key=f"match_radar_main_{selected_player}")

            for i, pos in enumerate(['FW','AM','CM','FB','CB'], 1):
                with subtabs[i]:
                    rows, headers = position_tables_active.get(pos, ([], []))
                    if rows:
                        numbered_rows = [[j+1] + row for j, row in enumerate(rows)]
                        df_pos = pd.DataFrame(numbered_rows, columns=['№'] + headers)
                        st.write(f'<div class="match-table">{df_pos.to_html(escape=False, index=False)}</div>', unsafe_allow_html=True)
                        player_names = [r[0] for r in rows]
                        if player_names:
                            selected_player_pos = st.selectbox(f"Выберите игрока для радара ({pos})", player_names, key=f"radar_player_{pos}")
                            if selected_player_pos:
                                player_row = df_active[df_active['player'] == selected_player_pos].iloc[0]
                                col1, col2, col3 = st.columns([1, 2, 1])
                                with col2:
                                    fig = create_player_radar_figure(player_row, df_active, st.session_state.match_settings, avg_values=league_avg)
                                    st.plotly_chart(fig, use_container_width=True, key=f"match_radar_{pos}_{selected_player_pos}")
                    else:
                        st.info(f"Нет игроков позиции {pos} при фильтре минут ≥ {min_minutes_filter}")

            # Экспорт в Excel
            st.markdown("---")
            st.subheader("📥 Экспорт матчей (формат RuStat)")
            col_sel, col_team, col_season = st.columns([2, 1, 1])
            with col_sel:
                export_match_ids = st.multiselect(
                    "Выберите матчи для экспорта",
                    options=list(st.session_state.df_matches.keys()),
                    format_func=lambda mid: st.session_state.df_matches[mid]['label'],
                    key="rustat_export_matches"
                )
            team_name_default = "Динамо Минск"
            season_default = "2025"
            if export_match_ids:
                sample_id = export_match_ids[0]
                sample_df = st.session_state.df_matches[sample_id]['df']
                if not sample_df.empty and 'team' in sample_df.columns:
                    team_name_default = sample_df['team'].iloc[0]
            with col_team:
                export_team = st.text_input("Название команды", value=team_name_default, key="rustat_team")
            with col_season:
                export_season = st.text_input("Сезон (год)", value=season_default, key="rustat_season")
            if export_match_ids and st.button("📥 Экспорт в Excel (RuStat)", key="export_rustat"):
                with st.spinner("Формирование RuStat-отчёта..."):
                    output = io.BytesIO()
                    try:
                        export_matches_advanced(
                            st.session_state.df_matches,
                            export_match_ids,
                            export_team.strip(),
                            export_season.strip(),
                            league_avg,
                            player_season_map,
                            output
                        )
                        output.seek(0)
                        st.download_button(
                            label="Скачать Excel",
                            data=output,
                            file_name=f"RuStat_{export_team}_{export_season}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_rustat"
                        )
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
              if st.button("📥 Экспорт в Excel (стандартный)", key="export_match"):
    output = io.BytesIO()
    try:
        export_match_standard_with_charts(
            df_active, selected_metrics, position_tables_active, league_avg, output
        )
        output.seek(0)
        st.download_button(
            label="Скачать Excel",
            data=output,
            file_name=f"match_players_rating_{selected_label}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_standard_match"
        )
    except Exception as e:
        st.error(f"Ошибка при экспорте: {e}")
    else:
        st.info("Загрузите матчи (в боковой панели)")

# -------------------- РЕДАКТОР ВЕСОВ (СЕЗОН) --------------------
if st.session_state.get('show_weights_editor'):
    with st.expander("Редактор весов метрик (сезон)", expanded=True):
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
                save_settings(new_weights, SETTINGS_FILE)
                st.session_state.show_weights_editor = False
                st.cache_data.clear()
                st.success("Веса обновлены. Данные пересчитываются...")
                if st.session_state.df_db is not None:
                    st.session_state.df_db = calculate_ratings(st.session_state.df_db, new_weights)
                    st.session_state.position_tables = build_position_tables(st.session_state.df_db, new_weights)
                st.rerun()
        with col2:
            if st.button("Отмена", use_container_width=True, key="cancel_weights"):
                st.session_state.show_weights_editor = False
                st.rerun()

# -------------------- РЕДАКТОР ВЕСОВ (МАТЧ) --------------------
if st.session_state.get('show_match_weights_editor'):
    with st.expander("Редактор весов метрик (матч)", expanded=True):
        positions_order = ['FW', 'AM', 'CM', 'FB', 'CB']
        pos_names = {'FW':'Нападающие','AM':'Атак. полузащитники','CM':'Центр. полузащитники','FB':'Крайние защитники','CB':'Центр. защитники'}
        active_df = st.session_state.df_db if st.session_state.df_db is not None else (
            list(st.session_state.df_matches.values())[0]['df'] if st.session_state.df_matches else None
        )
        if active_df is not None:
            available_metrics = [m for m in MATCH_ALL_METRICS if m in active_df.columns]
            if 'ttd_actions' in active_df.columns:
                available_metrics.append('ttd_actions')
            if 'ttd_opp_actions' in active_df.columns:
                available_metrics.append('ttd_opp_actions')
        else:
            available_metrics = MATCH_ALL_METRICS + ['ttd_actions', 'ttd_opp_actions']
        weight_tabs = st.tabs([pos_names[p] for p in positions_order])
        new_weights = {}
        for idx, pos in enumerate(positions_order):
            with weight_tabs[idx]:
                st.caption(f"**{pos_names[pos]}** — снимите галочку, чтобы исключить")
                current_pos_weights = st.session_state.match_settings.get(pos, {})
                for metric in available_metrics:
                    name = MATCH_METRIC_NAMES_RU.get(metric, metric)
                    enabled = metric in current_pos_weights and current_pos_weights[metric] != 0
                    displayed_weight = abs(current_pos_weights.get(metric, 1.0)) if enabled else 1.0
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        checked = st.checkbox(f"**{name}**", value=enabled, key=f"chk_match_{pos}_{metric}")
                    with col2:
                        weight_val = st.number_input("Вес", min_value=0.1, max_value=10.0, value=displayed_weight, step=0.5, disabled=not checked, key=f"wgt_match_{pos}_{metric}")
                    if checked and weight_val > 0:
                        if metric in NEGATIVE_METRICS:
                            new_weights.setdefault(pos, {})[metric] = -weight_val
                        else:
                            new_weights.setdefault(pos, {})[metric] = weight_val
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Сохранить веса матча", use_container_width=True, key="save_match_weights"):
                for pos in positions_order:
                    if pos not in new_weights or not new_weights[pos]:
                        st.error(f"Для позиции **{pos_names[pos]}** должна быть включена хотя бы одна метрика.")
                        st.stop()
                st.session_state.match_settings = new_weights
                st.session_state.show_match_weights_editor = False
                st.cache_data.clear()
                st.success("Веса матча обновлены. Данные пересчитываются...")
                if st.session_state.df_matches:
                    for mid, data in st.session_state.df_matches.items():
                        data['df'] = calculate_match_ratings(data['df'], new_weights)
                        if 'match_tables' in st.session_state and mid in st.session_state.match_tables:
                            st.session_state.match_tables[mid] = build_match_position_tables(
                                data['df'], new_weights,
                                league_avg=st.session_state.get('league_avg'),
                                player_season_map=st.session_state.get('player_season_map')
                            )
                st.rerun()
        with col2:
            if st.button("Отмена", use_container_width=True, key="cancel_match_weights"):
                st.session_state.show_match_weights_editor = False
                st.rerun()
