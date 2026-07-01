import os
import logging
import sys
import asyncio
import io
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не задан.")
    sys.exit(1)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Импорт ваших модулей
try:
    from config import *
    from db import *
    from calculations import *
    from visualization import *
    from utils import load_settings, save_settings, load_match_settings, save_match_settings
except ImportError as e:
    logger.error(f"❌ Ошибка импорта модулей: {e}")
    sys.exit(1)

# Глобальные веса
current_season_weights = load_settings(SETTINGS_FILE)
if current_season_weights is None:
    current_season_weights = {pos: w.copy() for pos, w in DEFAULT_METRICS_WEIGHTS.items()}
    save_settings(current_season_weights, SETTINGS_FILE)

current_match_weights = load_match_settings()
if current_match_weights is None:
    current_match_weights = {pos: w.copy() for pos, w in DEFAULT_MATCH_WEIGHTS.items()}
    save_match_settings(current_match_weights)

# Предустановленные наборы метрик
METRIC_SETS = {
    "Основные": ['goals_p90', 'assists_p90', 'xG_p90', 'key_passes_p90', 'pass_accuracy', 'dribbles_p90', 'tackles_p90', 'interceptions_p90'],
    "Атакующие": ['goals_p90', 'assists_p90', 'shots_on_target_p90', 'xG_p90', 'key_passes_p90', 'dribbles_p90', 'actions_opp_box_p90', 'chances_created_p90'],
    "Защитные": ['tackles_p90', 'interceptions_p90', 'ball_recoveries_p90', 'loose_ball_recoveries_p90', 'clearances_p90', 'blocks_p90'],
    "Все": ALL_POSSIBLE_METRICS[:12]  # ограничим 12 для читаемости
}

# -------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --------------------
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 Сезонная статистика", callback_data="season")],
        [InlineKeyboardButton("⚽ Матчевая статистика", callback_data="match")],
        [InlineKeyboardButton("📈 Радар игрока", callback_data="radar")],
        [InlineKeyboardButton("📤 Экспорт Excel", callback_data="export")],
        [InlineKeyboardButton("⚙️ Настройка весов", callback_data="weights")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button(callback_data="main"):
    return InlineKeyboardButton("🔙 Назад", callback_data=callback_data)

async def send_excel_file(update: Update, context: ContextTypes.DEFAULT_TYPE, df: pd.DataFrame, filename: str, caption=""):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Данные')
    output.seek(0)
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=InputFile(output, filename=filename),
        caption=caption or f"📊 {filename}"
    )

async def send_table_as_text(update: Update, context: ContextTypes.DEFAULT_TYPE, df: pd.DataFrame, title: str):
    """Отправляет DataFrame в виде форматированного текста (Markdown)."""
    if df.empty:
        await update.callback_query.message.reply_text("❌ Нет данных.")
        return
    # Ограничим количество строк для читаемости (первые 15)
    df_display = df.head(15)
    # Формируем Markdown-таблицу
    headers = "| " + " | ".join(df_display.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(df_display.columns)) + " |"
    rows = []
    for _, row in df_display.iterrows():
        row_str = "| " + " | ".join(str(v)[:30] for v in row.values) + " |"
        rows.append(row_str)
    table = "\n".join([headers, separator] + rows)
    text = f"**{title}**\n```\n{table}\n```"
    await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def send_radar_image(update: Update, context: ContextTypes.DEFAULT_TYPE, player_row, df, weights, avg_values=None):
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

# -------------------- ГЛАВНОЕ МЕНЮ И ПОМОЩЬ --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот InStatAnalyst.\n"
        "Я помогу вам анализировать футбольную статистику. Используйте кнопки ниже.",
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Доступные команды:\n"
        "/season – сезонная статистика\n"
        "/match – матчевая статистика\n"
        "/radar – радар игрока\n"
        "/export – экспорт в Excel\n"
        "/weights – настройка весов\n"
        "Или используйте кнопки в меню."
    )

# -------------------- СЕЗОННАЯ СТАТИСТИКА (с выбором метрик и позиций) --------------------
async def season_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    leagues = get_leagues()
    if not leagues:
        await query.edit_message_text("❌ Нет доступных лиг.")
        return
    keyboard = [[InlineKeyboardButton(l, callback_data=f"season_league_{l}")] for l in leagues]
    keyboard.append([get_back_button("main")])
    await query.edit_message_text("Выберите лигу:", reply_markup=InlineKeyboardMarkup(keyboard))

async def season_league(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league = query.data.replace("season_league_", "")
    context.user_data['season_league'] = league
    seasons = get_seasons_for_leagues([league])
    if not seasons:
        await query.edit_message_text("❌ Нет сезонов для этой лиги.")
        return
    keyboard = [[InlineKeyboardButton(s, callback_data=f"season_season_{s}")] for s in seasons]
    keyboard.append([get_back_button("season")])
    await query.edit_message_text(f"Лига: {league}\nВыберите сезон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def season_season(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    season = query.data.replace("season_season_", "")
    context.user_data['season_season'] = season
    league = context.user_data.get('season_league')
    teams = get_teams_for_leagues_seasons([league], [season])
    if not teams:
        await query.edit_message_text("❌ Нет команд для этого сезона.")
        return
    keyboard = []
    for t in teams:
        keyboard.append([InlineKeyboardButton(t, callback_data=f"season_team_{t}")])
    keyboard.append([InlineKeyboardButton("✅ Выбрать все", callback_data="season_select_all")])
    keyboard.append([InlineKeyboardButton("📊 Показать", callback_data="season_show_metrics")])
    keyboard.append([get_back_button("season")])
    await query.edit_message_text(
        f"Лига: {league}\nСезон: {season}\nВыберите команды (нажимайте для выбора/снятия):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def season_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    team = query.data.replace("season_team_", "")
    if 'season_teams' not in context.user_data:
        context.user_data['season_teams'] = []
    if team in context.user_data['season_teams']:
        context.user_data['season_teams'].remove(team)
    else:
        context.user_data['season_teams'].append(team)
    await season_show_teams(update, context)

async def season_select_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league = context.user_data.get('season_league')
    season = context.user_data.get('season_season')
    teams = get_teams_for_leagues_seasons([league], [season])
    context.user_data['season_teams'] = teams.copy()
    await season_show_teams(update, context)

async def season_show_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    league = context.user_data.get('season_league')
    season = context.user_data.get('season_season')
    current_teams = context.user_data.get('season_teams', [])
    all_teams = get_teams_for_leagues_seasons([league], [season])
    keyboard = []
    for t in all_teams:
        check = "✅ " if t in current_teams else ""
        keyboard.append([InlineKeyboardButton(f"{check}{t}", callback_data=f"season_team_{t}")])
    keyboard.append([InlineKeyboardButton("✅ Выбрать все", callback_data="season_select_all")])
    keyboard.append([InlineKeyboardButton("📊 Показать", callback_data="season_show_metrics")])
    keyboard.append([get_back_button("season")])
    await query.edit_message_text(
        f"Лига: {league}\nСезон: {season}\nВыбрано команд: {len(current_teams)}\nНажмите на команду для выбора/снятия.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def season_show_metrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    teams = context.user_data.get('season_teams', [])
    if not teams:
        await query.edit_message_text("❌ Выберите хотя бы одну команду.")
        return
    # Предложить выбрать набор метрик
    keyboard = []
    for set_name in METRIC_SETS.keys():
        keyboard.append([InlineKeyboardButton(set_name, callback_data=f"season_metric_set_{set_name}")])
    keyboard.append([InlineKeyboardButton("🔢 Выбрать вручную", callback_data="season_metric_custom")])
    keyboard.append([get_back_button("season")])
    await query.edit_message_text("Выберите набор метрик для отображения:", reply_markup=InlineKeyboardMarkup(keyboard))

async def season_metric_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    set_name = query.data.replace("season_metric_set_", "")
    metrics = METRIC_SETS.get(set_name, [])
    context.user_data['season_metrics'] = metrics
    await season_show_final(update, context, set_name)

async def season_metric_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Просим пользователя ввести метрики через запятую (упрощённо)
    await query.edit_message_text(
        "Введите названия метрик через запятую (например: goals_p90, assists_p90, xG_p90).\n"
        "Список доступных метрик можно посмотреть в файле config.py."
    )
    context.user_data['season_waiting_metrics'] = True

async def season_custom_metrics_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('season_waiting_metrics', False):
        return
    text = update.message.text.strip()
    metrics = [m.strip() for m in text.split(',') if m.strip()]
    context.user_data['season_metrics'] = metrics
    context.user_data['season_waiting_metrics'] = False
    await season_show_final(update, context, "Пользовательский набор")

async def season_show_final(update: Update, context: ContextTypes.DEFAULT_TYPE, set_name=""):
    # Если вызвано из callback, обновляем сообщение
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("⏳ Загружаю данные...")
        message = query.message
    else:
        # если из текстового ввода
        message = await update.message.reply_text("⏳ Загружаю данные...")
    league = context.user_data.get('season_league')
    season = context.user_data.get('season_season')
    teams = context.user_data.get('season_teams', [])
    metrics = context.user_data.get('season_metrics', METRIC_SETS["Основные"])
    if not metrics:
        metrics = METRIC_SETS["Основные"]
    loop = asyncio.get_running_loop()
    df_raw = await loop.run_in_executor(None, load_from_db, [league], [season], teams)
    df_filtered = df_raw[df_raw['minutes'] >= MIN_MINUTES].copy()
    if df_filtered.empty:
        await message.reply_text("❌ Нет игроков с достаточным временем.")
        return
    df_rated = await loop.run_in_executor(None, calculate_ratings, df_filtered, current_season_weights)
    df_rated = df_rated.sort_values('rating', ascending=False).reset_index(drop=True)
    # Строим таблицу с выбранными метриками
    display_metrics = [m for m in metrics if m in df_rated.columns]
    if not display_metrics:
        display_metrics = ['goals_p90', 'assists_p90', 'xG_p90']
    df_main = build_main_table(df_rated, display_metrics)
    # Отправляем как текст (первые 15 строк) и предлагаем Excel для полной версии
    await send_table_as_text(update, context, df_main, f"Рейтинг (лига {league}, сезон {season})")
    # Предлагаем скачать полный Excel
    keyboard = [[InlineKeyboardButton("📥 Скачать Excel (полный)", callback_data="season_download_excel")]]
    keyboard.append([get_back_button("season")])
    await message.reply_text("Для полной таблицы скачайте Excel:", reply_markup=InlineKeyboardMarkup(keyboard))
    # Сохраняем df_main в контекст для скачивания
    context.user_data['season_df'] = df_main
    context.user_data['season_filename'] = f"season_rating_{league}_{season}.xlsx"

async def season_download_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    df = context.user_data.get('season_df')
    filename = context.user_data.get('season_filename', 'season_rating.xlsx')
    if df is not None:
        await send_excel_file(update, context, df, filename, caption="📊 Полная таблица")
    else:
        await query.edit_message_text("❌ Данные не найдены. Попробуйте заново.")

# -------------------- МАТЧЕВАЯ СТАТИСТИКА (с выбором метрик и позиций) --------------------
async def match_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    leagues = get_leagues()
    if not leagues:
        await query.edit_message_text("❌ Нет доступных лиг.")
        return
    keyboard = [[InlineKeyboardButton(l, callback_data=f"match_league_{l}")] for l in leagues]
    keyboard.append([get_back_button("main")])
    await query.edit_message_text("Выберите лигу:", reply_markup=InlineKeyboardMarkup(keyboard))

async def match_league(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league = query.data.replace("match_league_", "")
    context.user_data['match_league'] = league
    matches = get_matches_for_league(league)
    if not matches:
        await query.edit_message_text("❌ Нет матчей в этой лиге.")
        return
    keyboard = []
    for m in matches:
        label = f"{m[1]} ({m[3]}) {m[4]} vs {m[5]}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"match_select_{m[0]}")])
    keyboard.append([InlineKeyboardButton("📊 Показать", callback_data="match_show_metrics")])
    keyboard.append([get_back_button("match")])
    await query.edit_message_text(
        "Выберите матч(и) (нажимайте для выбора/снятия). Если выбрано несколько, будет показан первый:",
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
    # Обновить клавиатуру
    league = context.user_data.get('match_league')
    matches = get_matches_for_league(league)
    keyboard = []
    for m in matches:
        label = f"{m[1]} ({m[3]}) {m[4]} vs {m[5]}"
        check = "✅ " if m[0] in context.user_data['match_ids'] else ""
        keyboard.append([InlineKeyboardButton(f"{check}{label}", callback_data=f"match_select_{m[0]}")])
    keyboard.append([InlineKeyboardButton("📊 Показать", callback_data="match_show_metrics")])
    keyboard.append([get_back_button("match")])
    await query.edit_message_text(
        f"Выбрано матчей: {len(context.user_data['match_ids'])}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def match_show_metrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_ids = context.user_data.get('match_ids', [])
    if not match_ids:
        await query.edit_message_text("❌ Выберите хотя бы один матч.")
        return
    # Если несколько, предлагаем выбрать активный
    if len(match_ids) > 1:
        keyboard = []
        for mid in match_ids:
            # Получим метку матча
            matches = get_matches_for_league(context.user_data.get('match_league'))
            label = next((f"{m[1]} ({m[3]}) {m[4]} vs {m[5]}" for m in matches if m[0] == mid), str(mid))
            keyboard.append([InlineKeyboardButton(label, callback_data=f"match_active_{mid}")])
        keyboard.append([get_back_button("match")])
        await query.edit_message_text("Выберите активный матч для анализа:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        match_id = match_ids[0]
        context.user_data['match_active_id'] = match_id
        await match_choose_metrics(update, context)

async def match_active_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = int(query.data.replace("match_active_", ""))
    context.user_data['match_active_id'] = match_id
    await match_choose_metrics(update, context)

async def match_choose_metrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Выберите набор метрик для матча:")
    else:
        await update.message.reply_text("Выберите набор метрик для матча:")
    keyboard = []
    match_sets = {
        "Основные": ['goals', 'assists', 'shots_on_target', 'xG', 'key_passes', 'pass_accuracy', 'tackles', 'interceptions'],
        "Атакующие": ['goals', 'assists', 'shots_on_target', 'xG', 'key_passes', 'dribbles', 'actions_opp_box', 'chances_created'],
        "Защитные": ['tackles', 'interceptions', 'ball_recoveries', 'loose_ball_recoveries', 'clearances', 'blocks'],
        "Все": MATCH_ALL_METRICS[:12]
    }
    for set_name in match_sets.keys():
        keyboard.append([InlineKeyboardButton(set_name, callback_data=f"match_metric_set_{set_name}")])
    keyboard.append([InlineKeyboardButton("🔢 Ввести вручную", callback_data="match_metric_custom")])
    keyboard.append([get_back_button("match")])
    if query:
        await query.edit_message_text("Выберите набор метрик:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Выберите набор метрик:", reply_markup=InlineKeyboardMarkup(keyboard))

async def match_metric_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    set_name = query.data.replace("match_metric_set_", "")
    match_sets = {
        "Основные": ['goals', 'assists', 'shots_on_target', 'xG', 'key_passes', 'pass_accuracy', 'tackles', 'interceptions'],
        "Атакующие": ['goals', 'assists', 'shots_on_target', 'xG', 'key_passes', 'dribbles', 'actions_opp_box', 'chances_created'],
        "Защитные": ['tackles', 'interceptions', 'ball_recoveries', 'loose_ball_recoveries', 'clearances', 'blocks'],
        "Все": MATCH_ALL_METRICS[:12]
    }
    metrics = match_sets.get(set_name, [])
    context.user_data['match_metrics'] = metrics
    await match_show_final(update, context, set_name)

async def match_metric_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Введите названия метрик через запятую (например: goals, assists, xG).\n"
        "Список доступных метрик в config.py (MATCH_ALL_METRICS)."
    )
    context.user_data['match_waiting_metrics'] = True

async def match_custom_metrics_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('match_waiting_metrics', False):
        return
    text = update.message.text.strip()
    metrics = [m.strip() for m in text.split(',') if m.strip()]
    context.user_data['match_metrics'] = metrics
    context.user_data['match_waiting_metrics'] = False
    await match_show_final(update, context, "Пользовательский набор")

async def match_show_final(update: Update, context: ContextTypes.DEFAULT_TYPE, set_name=""):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("⏳ Загружаю данные матча...")
        message = query.message
    else:
        message = await update.message.reply_text("⏳ Загружаю данные матча...")
    match_id = context.user_data.get('match_active_id')
    if not match_id:
        await message.reply_text("❌ Не выбран активный матч.")
        return
    league = context.user_data.get('match_league')
    metrics = context.user_data.get('match_metrics', ['goals', 'assists', 'shots_on_target', 'xG', 'key_passes', 'pass_accuracy'])
    loop = asyncio.get_running_loop()
    df_match = await loop.run_in_executor(None, load_match_stats, match_id, None)
    if df_match.empty:
        await message.reply_text("❌ Нет данных для этого матча.")
        return
    df_rated = await loop.run_in_executor(None, calculate_match_ratings, df_match, current_match_weights)
    df_rated = df_rated.sort_values('rating', ascending=False).reset_index(drop=True)
    # Получаем средние по лиге для заголовков
    league_avg = await loop.run_in_executor(None, get_league_averages, league, None)
    # Строим общую таблицу
    display_metrics = [m for m in metrics if m in df_rated.columns]
    if not display_metrics:
        display_metrics = ['goals', 'assists', 'shots_on_target', 'xG']
    df_main = build_match_main_table(df_rated, display_metrics, league_avg=league_avg, player_season_map=None)
    # Отправляем текстовую таблицу
    await send_table_as_text(update, context, df_main, f"Матч {match_id}")
    # Предлагаем Excel и разделение по позициям
    keyboard = [
        [InlineKeyboardButton("📥 Скачать Excel (полный)", callback_data="match_download_excel")],
        [InlineKeyboardButton("📋 Показать по позициям", callback_data="match_show_positions")],
        [get_back_button("match")]
    ]
    await message.reply_text("Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['match_df'] = df_main
    context.user_data['match_filename'] = f"match_{match_id}.xlsx"
    context.user_data['match_df_rated'] = df_rated
    context.user_data['match_league_avg'] = league_avg

async def match_download_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    df = context.user_data.get('match_df')
    filename = context.user_data.get('match_filename', 'match.xlsx')
    if df is not None:
        await send_excel_file(update, context, df, filename, caption="📊 Полная таблица")
    else:
        await query.edit_message_text("❌ Данные не найдены.")

async def match_show_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    df_rated = context.user_data.get('match_df_rated')
    league_avg = context.user_data.get('match_league_avg')
    if df_rated is None:
        await query.edit_message_text("❌ Данные не найдены.")
        return
    # Строим таблицы по позициям
    weights = current_match_weights
    pos_tables = build_match_position_tables(df_rated, weights, league_avg=league_avg, player_season_map=None)
    # Отправляем отдельные таблицы для каждой позиции
    for pos, (rows, headers) in pos_tables.items():
        if rows:
            df_pos = pd.DataFrame(rows, columns=headers)
            await send_table_as_text(update, context, df_pos, f"Позиция {pos}")
    await query.edit_message_text("✅ Все позиции отправлены.")

# -------------------- РАДАР (без изменений) --------------------
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

# -------------------- ЭКСПОРТ (упрощён) --------------------
async def export_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📊 Сезон", callback_data="export_season")],
        [InlineKeyboardButton("⚽ Матч", callback_data="export_match")],
        [get_back_button("main")]
    ]
    await query.edit_message_text("Выберите тип экспорта:", reply_markup=InlineKeyboardMarkup(keyboard))

async def export_season(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await season_start(update, context)

async def export_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await match_start(update, context)

# -------------------- НАСТРОЙКА ВЕСОВ (без изменений) --------------------
async def weights_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📊 Веса для сезона", callback_data="weights_season")],
        [InlineKeyboardButton("⚽ Веса для матчей", callback_data="weights_match")],
        [get_back_button("main")]
    ]
    await query.edit_message_text("Выберите тип весов:", reply_markup=InlineKeyboardMarkup(keyboard))

async def weights_season(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "Текущие веса для сезона:\n"
    for pos, weights in current_season_weights.items():
        pos_name = {'FW':'Нападающие','AM':'Атак. полузащитники','CM':'Центр. полузащитники','FB':'Крайние защитники','CB':'Центр. защитники'}.get(pos, pos)
        text += f"\n{pos_name}:\n"
        for m, w in weights.items():
            if w != 0:
                text += f"  {METRIC_NAMES_RU.get(m, m)}: {w}\n"
    keyboard = [
        [InlineKeyboardButton("🔄 Сбросить веса сезона", callback_data="reset_season_weights")],
        [get_back_button("weights")]
    ]
    await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_season_weights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_season_weights
    current_season_weights = {pos: w.copy() for pos, w in DEFAULT_METRICS_WEIGHTS.items()}
    save_settings(current_season_weights, SETTINGS_FILE)
    await update.callback_query.answer("Веса сезона сброшены.")
    await update.callback_query.edit_message_text("✅ Веса сезона сброшены к значениям по умолчанию.")

async def weights_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "Текущие веса для матчей:\n"
    for pos, weights in current_match_weights.items():
        pos_name = {'FW':'Нападающие','AM':'Атак. полузащитники','CM':'Центр. полузащитники','FB':'Крайние защитники','CB':'Центр. защитники'}.get(pos, pos)
        text += f"\n{pos_name}:\n"
        for m, w in weights.items():
            if w != 0:
                text += f"  {MATCH_METRIC_NAMES_RU.get(m, m)}: {w}\n"
    keyboard = [
        [InlineKeyboardButton("🔄 Сбросить веса матчей", callback_data="reset_match_weights")],
        [get_back_button("weights")]
    ]
    await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_match_weights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_match_weights
    current_match_weights = {pos: w.copy() for pos, w in DEFAULT_MATCH_WEIGHTS.items()}
    save_match_settings(current_match_weights)
    await update.callback_query.answer("Веса матчей сброшены.")
    await update.callback_query.edit_message_text("✅ Веса матчей сброшены к значениям по умолчанию.")

# -------------------- ГЛАВНЫЙ ОБРАБОТЧИК КНОПОК --------------------
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
        elif data == "season_select_all":
            await season_select_all(update, context)
        elif data == "season_show_metrics":
            await season_show_metrics(update, context)
        elif data.startswith("season_metric_set_"):
            await season_metric_set(update, context)
        elif data == "season_metric_custom":
            await season_metric_custom(update, context)
        elif data == "season_download_excel":
            await season_download_excel(update, context)
    elif data.startswith("match_"):
        if data.startswith("match_league_"):
            await match_league(update, context)
        elif data.startswith("match_select_"):
            await match_select(update, context)
        elif data == "match_show_metrics":
            await match_show_metrics(update, context)
        elif data.startswith("match_active_"):
            await match_active_select(update, context)
        elif data.startswith("match_metric_set_"):
            await match_metric_set(update, context)
        elif data == "match_metric_custom":
            await match_metric_custom(update, context)
        elif data == "match_download_excel":
            await match_download_excel(update, context)
        elif data == "match_show_positions":
            await match_show_positions(update, context)
    elif data.startswith("export_"):
        if data == "export_season":
            await export_season(update, context)
        elif data == "export_match":
            await export_match(update, context)
    elif data.startswith("weights_"):
        if data == "weights_season":
            await weights_season(update, context)
        elif data == "weights_match":
            await weights_match(update, context)
        elif data == "reset_season_weights":
            await reset_season_weights(update, context)
        elif data == "reset_match_weights":
            await reset_match_weights(update, context)
    else:
        await query.edit_message_text("Неизвестная команда. Используйте /start для главного меню.")

# -------------------- ЗАПУСК --------------------
def main():
    try:
        logger.info("🚀 Запуск бота...")
        application = Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("season", season_start))
        application.add_handler(CommandHandler("match", match_start))
        application.add_handler(CommandHandler("radar", radar_start))
        application.add_handler(CommandHandler("export", export_start))
        application.add_handler(CommandHandler("weights", weights_start))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, radar_input))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, season_custom_metrics_input))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, match_custom_metrics_input))
        logger.info("✅ Бот успешно запущен.")
        application.run_polling()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
