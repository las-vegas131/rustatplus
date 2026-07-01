import os
import logging
import io
import asyncio
import re
import json
from datetime import datetime

import pandas as pd
import plotly.io as pio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, ChatAction
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.constants import ParseMode

# Импорт ваших модулей
from config import (
    MIN_MINUTES, SETTINGS_FILE, SELECTED_METRICS_FILE,
    ALL_POSSIBLE_METRICS, DEFAULT_METRICS_WEIGHTS, DEFAULT_MATCH_WEIGHTS,
    METRIC_NAMES_RU, MATCH_METRIC_NAMES_RU, MATCH_ALL_METRICS
)
from db import (
    get_leagues, get_seasons_for_leagues, get_teams_for_leagues_seasons,
    get_teams_for_league, get_matches_for_league, load_from_db,
    load_match_stats, get_league_averages, get_player_season_stats_df
)
from calculations import (
    calculate_ratings, calculate_match_ratings,
    build_main_table, build_position_tables,
    build_match_main_table, build_match_position_tables,
    get_position_group
)
from visualization import (
    create_player_radar_figure,
    export_matches_advanced, export_match_standard_position_tables
)
from utils import (
    load_settings, save_settings, load_match_settings, save_match_settings
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------- ЗАГРУЗКА ВЕСОВ ПРИ СТАРТЕ --------------------
# Загружаем сохранённые веса из файлов (как в основном приложении)
current_season_weights = load_settings(SETTINGS_FILE)
if current_season_weights is None:
    current_season_weights = {pos: w.copy() for pos, w in DEFAULT_METRICS_WEIGHTS.items()}

current_match_weights = load_match_settings()
if current_match_weights is None:
    current_match_weights = {pos: w.copy() for pos, w in DEFAULT_MATCH_WEIGHTS.items()}

# Состояния для интерактивного редактирования весов
WEIGHTS_SELECT_POS, WEIGHTS_SELECT_METRIC, WEIGHTS_INPUT_VALUE = range(3)

# -------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --------------------
def get_main_keyboard():
    """Основная клавиатура с командами."""
    keyboard = [
        [InlineKeyboardButton("📊 Сезонная статистика", callback_data="season")],
        [InlineKeyboardButton("⚽ Матчевая статистика", callback_data="match")],
        [InlineKeyboardButton("📈 Радар игрока", callback_data="radar")],
        [InlineKeyboardButton("📤 Экспорт Excel", callback_data="export")],
        [InlineKeyboardButton("⚙️ Настройка весов", callback_data="weights")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def send_excel_file(update: Update, context: ContextTypes.DEFAULT_TYPE, df: pd.DataFrame, filename: str, caption: str = None):
    """Отправляет DataFrame как Excel-файл."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Данные')
    output.seek(0)
    if caption is None:
        caption = f"📊 {filename}"
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=InputFile(output, filename=filename),
        caption=caption
    )

async def send_radar_image(update: Update, context: ContextTypes.DEFAULT_TYPE, player_row, df, weights, avg_values=None):
    """Генерирует радар и отправляет изображение."""
    try:
        fig = create_player_radar_figure(player_row, df, weights, avg_values=avg_values)
        img_bytes = fig.to_image(format="png", width=600, height=600, scale=2)
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=InputFile(io.BytesIO(img_bytes), filename="radar.png"),
            caption=f"📈 Радар для {player_row['player']}"
        )
    except Exception as e:
        logger.error(f"Ошибка генерации радара: {e}")
        await update.callback_query.message.reply_text("❌ Не удалось создать радар. Попробуйте позже.")

# -------------------- ОБРАБОТЧИКИ КОМАНД --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start – приветствие и главное меню."""
    await update.message.reply_text(
        "👋 Привет! Я бот InStatAnalyst.\n"
        "Я помогу вам анализировать футбольную статистику. Используйте кнопки ниже.",
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Доступные команды:\n"
        "/season – сезонная статистика (рейтинг игроков)\n"
        "/match – матчевая статистика\n"
        "/radar – построить радар для игрока\n"
        "/export – экспорт данных в Excel\n"
        "/weights – настройка весов метрик\n"
        "Также вы можете использовать кнопки в меню."
    )

# -------------------- СЕЗОННАЯ СТАТИСТИКА --------------------
async def season_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    leagues = get_leagues()
    if not leagues:
        await query.edit_message_text("❌ Нет доступных лиг в базе.")
        return
    keyboard = [[InlineKeyboardButton(l, callback_data=f"season_league_{l}")] for l in leagues]
    await query.edit_message_text("Выберите лигу:", reply_markup=InlineKeyboardMarkup(keyboard))

async def season_league(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league = query.data.replace("season_league_", "")
    context.user_data['season_league'] = league
    seasons = get_seasons_for_leagues([league])
    if not seasons:
        await query.edit_message_text("❌ Нет сезонов для выбранной лиги.")
        return
    keyboard = [[InlineKeyboardButton(s, callback_data=f"season_season_{s}")] for s in seasons]
    await query.edit_message_text(f"Лига: {league}\nВыберите сезон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def season_season(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    season = query.data.replace("season_season_", "")
    context.user_data['season_season'] = season
    league = context.user_data.get('season_league')
    teams = get_teams_for_leagues_seasons([league], [season])
    if not teams:
        await query.edit_message_text("❌ Нет команд для выбранного сезона.")
        return
    # Инициализируем список выбранных команд
    if 'season_teams' not in context.user_data:
        context.user_data['season_teams'] = []
    # Строим клавиатуру с галочками
    keyboard = []
    for t in teams:
        check = "✅ " if t in context.user_data['season_teams'] else ""
        keyboard.append([InlineKeyboardButton(f"{check}{t}", callback_data=f"season_team_{t}")])
    keyboard.append([InlineKeyboardButton("📊 Показать рейтинг", callback_data="season_show")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="season")])
    await query.edit_message_text(
        f"Лига: {league}\nСезон: {season}\nВыберите команды (можно несколько):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def season_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    team = query.data.replace("season_team_", "")
    league = context.user_data.get('season_league')
    season = context.user_data.get('season_season')
    # Переключаем состояние команды
    if 'season_teams' not in context.user_data:
        context.user_data['season_teams'] = []
    if team in context.user_data['season_teams']:
        context.user_data['season_teams'].remove(team)
    else:
        context.user_data['season_teams'].append(team)
    # Обновляем клавиатуру
    teams = get_teams_for_leagues_seasons([league], [season])
    keyboard = []
    for t in teams:
        check = "✅ " if t in context.user_data['season_teams'] else ""
        keyboard.append([InlineKeyboardButton(f"{check}{t}", callback_data=f"season_team_{t}")])
    keyboard.append([InlineKeyboardButton("📊 Показать рейтинг", callback_data="season_show")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="season")])
    await query.edit_message_text(
        f"Лига: {league}\nСезон: {season}\nВыбрано команд: {len(context.user_data['season_teams'])}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def season_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league = context.user_data.get('season_league')
    season = context.user_data.get('season_season')
    teams = context.user_data.get('season_teams', [])
    if not teams:
        await query.edit_message_text("❌ Выберите хотя бы одну команду.")
        return
    await query.edit_message_text("⏳ Загружаю данные...")
    loop = asyncio.get_running_loop()
    df_raw = await loop.run_in_executor(None, load_from_db, [league], [season], teams)
    df_filtered = df_raw[df_raw['minutes'] >= MIN_MINUTES].copy()
    if df_filtered.empty:
        await query.edit_message_text("❌ Нет игроков с достаточным временем.")
        return
    df_rated = await loop.run_in_executor(None, calculate_ratings, df_filtered, current_season_weights)
    df_rated = df_rated.sort_values('rating', ascending=False).reset_index(drop=True)
    # Выбираем метрики для отображения
    all_metrics = [m for m in ALL_POSSIBLE_METRICS if m in df_rated.columns]
    mandatory = ['ttd_actions_p90', 'ttd_opp_actions_p90']
    display_metrics = [m for m in all_metrics if m in mandatory or m in ['goals_p90', 'assists_p90', 'xG_p90', 'key_passes_p90']]
    if not display_metrics:
        display_metrics = all_metrics[:5]
    df_main = build_main_table(df_rated, display_metrics)
    filename = f"season_rating_{league}_{season}.xlsx"
    await send_excel_file(update, context, df_main, filename)
    await query.edit_message_text("✅ Рейтинг отправлен в Excel-файле.")

# -------------------- МАТЧЕВАЯ СТАТИСТИКА (ПОДДЕРЖКА НЕСКОЛЬКИХ МАТЧЕЙ) --------------------
async def match_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    leagues = get_leagues()
    if not leagues:
        await query.edit_message_text("❌ Нет доступных лиг.")
        return
    keyboard = [[InlineKeyboardButton(l, callback_data=f"match_league_{l}")] for l in leagues]
    await query.edit_message_text("Выберите лигу для матчей:", reply_markup=InlineKeyboardMarkup(keyboard))

async def match_league(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league = query.data.replace("match_league_", "")
    context.user_data['match_league'] = league
    matches = get_matches_for_league(league)
    if not matches:
        await query.edit_message_text("❌ Нет матчей в этой лиге.")
        return
    # Инициализируем список выбранных матчей
    if 'match_ids' not in context.user_data:
        context.user_data['match_ids'] = []
    # Строим клавиатуру с галочками
    keyboard = []
    for m in matches:
        label = f"{m[1]} ({m[3]}) {m[4]} vs {m[5]}"
        check = "✅ " if m[0] in context.user_data['match_ids'] else ""
        keyboard.append([InlineKeyboardButton(f"{check}{label}", callback_data=f"match_select_{m[0]}")])
    keyboard.append([InlineKeyboardButton("📊 Показать статистику (объединить)", callback_data="match_show_combined")])
    keyboard.append([InlineKeyboardButton("📊 Показать статистику (по каждому)", callback_data="match_show_separate")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="match")])
    await query.edit_message_text(
        f"Выбрано матчей: {len(context.user_data['match_ids'])}\n"
        "Выберите матчи (можно несколько). Затем нажмите 'Показать статистику'.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def match_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = int(query.data.replace("match_select_", ""))
    if 'match_ids' not in context.user_data:
        context.user_data['match_ids'] = []
    if match_id in context.user_data['match_ids']:
        context.user_data['match_ids'].remove(match_id)
    else:
        context.user_data['match_ids'].append(match_id)
    # Обновляем клавиатуру
    league = context.user_data.get('match_league')
    matches = get_matches_for_league(league)
    keyboard = []
    for m in matches:
        label = f"{m[1]} ({m[3]}) {m[4]} vs {m[5]}"
        check = "✅ " if m[0] in context.user_data['match_ids'] else ""
        keyboard.append([InlineKeyboardButton(f"{check}{label}", callback_data=f"match_select_{m[0]}")])
    keyboard.append([InlineKeyboardButton("📊 Показать статистику (объединить)", callback_data="match_show_combined")])
    keyboard.append([InlineKeyboardButton("📊 Показать статистику (по каждому)", callback_data="match_show_separate")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="match")])
    await query.edit_message_text(
        f"Выбрано матчей: {len(context.user_data['match_ids'])}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def match_show_combined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Объединяет данные из нескольких матчей в один DataFrame и отправляет Excel."""
    query = update.callback_query
    await query.answer()
    match_ids = context.user_data.get('match_ids', [])
    if not match_ids:
        await query.edit_message_text("❌ Выберите хотя бы один матч.")
        return
    await query.edit_message_text("⏳ Загружаю данные и объединяю матчи...")
    loop = asyncio.get_running_loop()
    # Загружаем все матчи и объединяем
    all_dfs = []
    for mid in match_ids:
        df = await loop.run_in_executor(None, load_match_stats, mid, None)
        if not df.empty:
            df['match_id'] = mid
            all_dfs.append(df)
    if not all_dfs:
        await query.edit_message_text("❌ Нет данных для выбранных матчей.")
        return
    combined_df = pd.concat(all_dfs, ignore_index=True)
    # Рассчитываем рейтинг по объединённым данным
    df_rated = await loop.run_in_executor(None, calculate_match_ratings, combined_df, current_match_weights)
    df_rated = df_rated.sort_values('rating', ascending=False).reset_index(drop=True)
    # Строим общую таблицу
    all_metrics = [m for m in MATCH_ALL_METRICS if m in df_rated.columns]
    if 'ttd_actions' in df_rated.columns:
        all_metrics.append('ttd_actions')
    if 'ttd_opp_actions' in df_rated.columns:
        all_metrics.append('ttd_opp_actions')
    display_metrics = all_metrics[:10]
    league_avg = await loop.run_in_executor(None, get_league_averages, context.user_data.get('match_league'), None)
    df_main = build_match_main_table(df_rated, display_metrics, league_avg=league_avg, player_season_map=None)
    filename = f"matches_combined_{len(match_ids)}.xlsx"
    await send_excel_file(update, context, df_main, filename, f"Объединённая статистика {len(match_ids)} матчей")
    await query.edit_message_text("✅ Объединённая статистика отправлена.")

async def match_show_separate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет отдельный Excel-файл для каждого выбранного матча."""
    query = update.callback_query
    await query.answer()
    match_ids = context.user_data.get('match_ids', [])
    if not match_ids:
        await query.edit_message_text("❌ Выберите хотя бы один матч.")
        return
    await query.edit_message_text("⏳ Загружаю данные...")
    loop = asyncio.get_running_loop()
    league_avg = await loop.run_in_executor(None, get_league_averages, context.user_data.get('match_league'), None)
    for mid in match_ids:
        df = await loop.run_in_executor(None, load_match_stats, mid, None)
        if df.empty:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ Нет данных для матча {mid}")
            continue
        df_rated = await loop.run_in_executor(None, calculate_match_ratings, df, current_match_weights)
        df_rated = df_rated.sort_values('rating', ascending=False).reset_index(drop=True)
        all_metrics = [m for m in MATCH_ALL_METRICS if m in df_rated.columns]
        if 'ttd_actions' in df_rated.columns:
            all_metrics.append('ttd_actions')
        if 'ttd_opp_actions' in df_rated.columns:
            all_metrics.append('ttd_opp_actions')
        display_metrics = all_metrics[:10]
        df_main = build_match_main_table(df_rated, display_metrics, league_avg=league_avg, player_season_map=None)
        filename = f"match_{mid}.xlsx"
        await send_excel_file(update, context, df_main, filename, f"Матч #{mid}")
    await query.edit_message_text("✅ Все матчи отправлены.")

# -------------------- РАДАР --------------------
async def radar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите имя игрока (или часть имени):")
    context.user_data['radar_waiting'] = True

async def radar_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('radar_waiting', False):
        return
    player_name = update.message.text.strip()
    context.user_data['radar_waiting'] = False
    await update.message.reply_text("⏳ Ищем игрока...")
    leagues = get_leagues()
    if not leagues:
        await update.message.reply_text("❌ Нет лиг.")
        return
    # Ищем в первой лиге и первом сезоне (можно расширить)
    league = leagues[0]
    seasons = get_seasons_for_leagues([league])
    if not seasons:
        await update.message.reply_text("❌ Нет сезонов.")
        return
    season = seasons[0]
    loop = asyncio.get_running_loop()
    df = await loop.run_in_executor(None, load_from_db, [league], [season], None)
    df = df[df['minutes'] >= MIN_MINUTES]
    matches = df[df['player'].str.contains(player_name, case=False)]
    if matches.empty:
        await update.message.reply_text(f"❌ Игрок '{player_name}' не найден.")
        return
    player_row = matches.iloc[0]
    avg_series = df[['goals_p90', 'assists_p90', 'xG_p90', 'key_passes_p90', 'pass_accuracy', 'dribbles_p90', 'tackles_p90', 'interceptions_p90']].mean()
    await send_radar_image(update, context, player_row, df, current_season_weights, avg_series)
    await update.message.reply_text("✅ Радар отправлен.")

# -------------------- ЭКСПОРТ EXCEL --------------------
async def export_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📊 Экспорт сезонной статистики", callback_data="export_season")],
        [InlineKeyboardButton("⚽ Экспорт матчевой статистики", callback_data="export_match")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main")]
    ]
    await query.edit_message_text("Выберите тип экспорта:", reply_markup=InlineKeyboardMarkup(keyboard))

async def export_season(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await season_start(update, context)

async def export_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await match_start(update, context)

# -------------------- НАСТРОЙКА ВЕСОВ (ИНТЕРАКТИВНОЕ РЕДАКТИРОВАНИЕ) --------------------
async def weights_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📊 Веса для сезона", callback_data="weights_season")],
        [InlineKeyboardButton("⚽ Веса для матчей", callback_data="weights_match")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main")]
    ]
    await query.edit_message_text("Выберите тип весов:", reply_markup=InlineKeyboardMarkup(keyboard))

async def weights_season(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("➕ Изменить вес метрики", callback_data="weights_season_edit")],
        [InlineKeyboardButton("🔄 Сбросить все веса сезона", callback_data="reset_season_weights")],
        [InlineKeyboardButton("🔙 Назад", callback_data="weights")]
    ]
    # Показываем текущие веса кратко
    text = "Текущие веса для сезона:\n"
    for pos, weights in current_season_weights.items():
        pos_name = {'FW':'Нападающие','AM':'Атак. полузащитники','CM':'Центр. полузащитники','FB':'Крайние защитники','CB':'Центр. защитники'}.get(pos, pos)
        text += f"\n{pos_name}:\n"
        for m, w in weights.items():
            if w != 0:
                text += f"  {METRIC_NAMES_RU.get(m, m)}: {w}\n"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def weights_season_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Показываем список позиций для выбора
    keyboard = []
    for pos in ['FW', 'AM', 'CM', 'FB', 'CB']:
        pos_name = {'FW':'Нападающие','AM':'Атак. полузащитники','CM':'Центр. полузащитники','FB':'Крайние защитники','CB':'Центр. защитники'}.get(pos, pos)
        keyboard.append([InlineKeyboardButton(pos_name, callback_data=f"weights_season_pos_{pos}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="weights_season")])
    await query.edit_message_text("Выберите позицию для редактирования весов:", reply_markup=InlineKeyboardMarkup(keyboard))

async def weights_season_pos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pos = query.data.replace("weights_season_pos_", "")
    context.user_data['edit_pos'] = pos
    # Показываем список метрик с текущими весами
    weights = current_season_weights.get(pos, {})
    keyboard = []
    for m, w in weights.items():
        if w != 0:
            keyboard.append([InlineKeyboardButton(f"{METRIC_NAMES_RU.get(m, m)}: {w}", callback_data=f"weights_season_metric_{m}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="weights_season_edit")])
    await query.edit_message_text(
        f"Позиция: {pos}\nВыберите метрику для изменения веса:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def weights_season_metric(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    metric = query.data.replace("weights_season_metric_", "")
    context.user_data['edit_metric'] = metric
    await query.edit_message_text(
        f"Введите новое значение веса для метрики '{METRIC_NAMES_RU.get(metric, metric)}'\n"
        "Текущее значение: {:.1f}\n"
        "Введите число (может быть отрицательным):".format(current_season_weights[context.user_data['edit_pos']].get(metric, 0))
    )
    context.user_data['edit_type'] = 'season'
    return ConversationHandler.END  # Мы не используем ConversationHandler, просто переключаем состояние

async def weights_season_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстового ввода для изменения веса."""
    if 'edit_type' not in context.user_data or context.user_data['edit_type'] != 'season':
        return
    try:
        new_weight = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите число.")
        return
    pos = context.user_data.get('edit_pos')
    metric = context.user_data.get('edit_metric')
    if not pos or not metric:
        await update.message.reply_text("❌ Ошибка: не выбрана позиция или метрика.")
        return
    # Обновляем веса
    current_season_weights[pos][metric] = new_weight
    save_settings(current_season_weights, SETTINGS_FILE)
    await update.message.reply_text(f"✅ Вес для {METRIC_NAMES_RU.get(metric, metric)} изменён на {new_weight:.1f}")
    # Возвращаем в главное меню весов
    context.user_data['edit_type'] = None
    context.user_data['edit_pos'] = None
    context.user_data['edit_metric'] = None
    keyboard = [[InlineKeyboardButton("🔙 Назад в меню весов", callback_data="weights_season")]]
    await update.message.reply_text("Возврат в меню весов.", reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_season_weights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_season_weights
    current_season_weights = {pos: w.copy() for pos, w in DEFAULT_METRICS_WEIGHTS.items()}
    save_settings(current_season_weights, SETTINGS_FILE)
    await update.callback_query.answer("Веса сезона сброшены к значениям по умолчанию.")
    await update.callback_query.edit_message_text("✅ Веса сезона сброшены.")

async def weights_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("➕ Изменить вес метрики", callback_data="weights_match_edit")],
        [InlineKeyboardButton("🔄 Сбросить все веса матчей", callback_data="reset_match_weights")],
        [InlineKeyboardButton("🔙 Назад", callback_data="weights")]
    ]
    text = "Текущие веса для матчей:\n"
    for pos, weights in current_match_weights.items():
        pos_name = {'FW':'Нападающие','AM':'Атак. полузащитники','CM':'Центр. полузащитники','FB':'Крайние защитники','CB':'Центр. защитники'}.get(pos, pos)
        text += f"\n{pos_name}:\n"
        for m, w in weights.items():
            if w != 0:
                text += f"  {MATCH_METRIC_NAMES_RU.get(m, m)}: {w}\n"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def weights_match_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for pos in ['FW', 'AM', 'CM', 'FB', 'CB']:
        pos_name = {'FW':'Нападающие','AM':'Атак. полузащитники','CM':'Центр. полузащитники','FB':'Крайние защитники','CB':'Центр. защитники'}.get(pos, pos)
        keyboard.append([InlineKeyboardButton(pos_name, callback_data=f"weights_match_pos_{pos}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="weights_match")])
    await query.edit_message_text("Выберите позицию для редактирования весов:", reply_markup=InlineKeyboardMarkup(keyboard))

async def weights_match_pos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pos = query.data.replace("weights_match_pos_", "")
    context.user_data['edit_pos'] = pos
    weights = current_match_weights.get(pos, {})
    keyboard = []
    for m, w in weights.items():
        if w != 0:
            keyboard.append([InlineKeyboardButton(f"{MATCH_METRIC_NAMES_RU.get(m, m)}: {w}", callback_data=f"weights_match_metric_{m}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="weights_match_edit")])
    await query.edit_message_text(
        f"Позиция: {pos}\nВыберите метрику для изменения веса:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def weights_match_metric(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    metric = query.data.replace("weights_match_metric_", "")
    context.user_data['edit_metric'] = metric
    await query.edit_message_text(
        f"Введите новое значение веса для метрики '{MATCH_METRIC_NAMES_RU.get(metric, metric)}'\n"
        "Текущее значение: {:.1f}\n"
        "Введите число (может быть отрицательным):".format(current_match_weights[context.user_data['edit_pos']].get(metric, 0))
    )
    context.user_data['edit_type'] = 'match'

async def weights_match_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстового ввода для изменения веса матча."""
    if 'edit_type' not in context.user_data or context.user_data['edit_type'] != 'match':
        return
    try:
        new_weight = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите число.")
        return
    pos = context.user_data.get('edit_pos')
    metric = context.user_data.get('edit_metric')
    if not pos or not metric:
        await update.message.reply_text("❌ Ошибка: не выбрана позиция или метрика.")
        return
    current_match_weights[pos][metric] = new_weight
    save_match_settings(current_match_weights)
    await update.message.reply_text(f"✅ Вес для {MATCH_METRIC_NAMES_RU.get(metric, metric)} изменён на {new_weight:.1f}")
    context.user_data['edit_type'] = None
    context.user_data['edit_pos'] = None
    context.user_data['edit_metric'] = None
    keyboard = [[InlineKeyboardButton("🔙 Назад в меню весов", callback_data="weights_match")]]
    await update.message.reply_text("Возврат в меню весов.", reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_match_weights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_match_weights
    current_match_weights = {pos: w.copy() for pos, w in DEFAULT_MATCH_WEIGHTS.items()}
    save_match_settings(current_match_weights)
    await update.callback_query.answer("Веса матчей сброшены к значениям по умолчанию.")
    await update.callback_query.edit_message_text("✅ Веса матчей сброшены.")

# -------------------- ОБЩИЙ ОБРАБОТЧИК КНОПОК --------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "main":
        await query.edit_message_text("Главное меню:", reply_markup=get_main_keyboard())
    elif data == "season":
        await season_start(update, context)
    elif data == "match":
        await match_start(update, context)
    elif data == "radar":
        await radar_start(update, context)
    elif data == "export":
        await export_start(update, context)
    elif data == "weights":
        await weights_start(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data.startswith("season_"):
        if data.startswith("season_league_"):
            await season_league(update, context)
        elif data.startswith("season_season_"):
            await season_season(update, context)
        elif data.startswith("season_team_"):
            await season_team(update, context)
        elif data == "season_show":
            await season_show(update, context)
    elif data.startswith("match_"):
        if data.startswith("match_league_"):
            await match_league(update, context)
        elif data.startswith("match_select_"):
            await match_select(update, context)
        elif data == "match_show_combined":
            await match_show_combined(update, context)
        elif data == "match_show_separate":
            await match_show_separate(update, context)
    elif data.startswith("export_"):
        if data == "export_season":
            await season_start(update, context)
        elif data == "export_match":
            await match_start(update, context)
    elif data.startswith("weights_"):
        if data == "weights_season":
            await weights_season(update, context)
        elif data == "weights_match":
            await weights_match(update, context)
        elif data == "reset_season_weights":
            await reset_season_weights(update, context)
        elif data == "reset_match_weights":
            await reset_match_weights(update, context)
        elif data == "weights_season_edit":
            await weights_season_edit_start(update, context)
        elif data.startswith("weights_season_pos_"):
            await weights_season_pos(update, context)
        elif data.startswith("weights_season_metric_"):
            await weights_season_metric(update, context)
        elif data == "weights_match_edit":
            await weights_match_edit_start(update, context)
        elif data.startswith("weights_match_pos_"):
            await weights_match_pos(update, context)
        elif data.startswith("weights_match_metric_"):
            await weights_match_metric(update, context)

# -------------------- ЗАПУСК БОТА --------------------
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")
    application = Application.builder().token(token).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("season", season_start))
    application.add_handler(CommandHandler("match", match_start))
    application.add_handler(CommandHandler("radar", radar_start))
    application.add_handler(CommandHandler("export", export_start))
    application.add_handler(CommandHandler("weights", weights_start))

    # Обработчики инлайн-кнопок
    application.add_handler(CallbackQueryHandler(button_handler))

    # Обработчики текстовых сообщений (для ввода имени игрока и весов)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, radar_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, weights_season_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, weights_match_input))

    logger.info("Бот запущен и готов к работе.")
    application.run_polling()

if __name__ == "__main__":
    main()
