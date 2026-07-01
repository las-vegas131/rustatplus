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

# Проверка наличия токена
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не задан. Установите переменную окружения.")
    sys.exit(1)

# Импорты из telegram (исправленные для версии 20+)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Импорт ваших модулей (убедитесь, что все файлы в одной папке)
try:
    from config import *
    from db import *
    from calculations import *
    from visualization import *
    from utils import load_settings, save_settings, load_match_settings, save_match_settings
except ImportError as e:
    logger.error(f"❌ Ошибка импорта модулей: {e}")
    logger.error("Убедитесь, что все файлы (config.py, db.py, calculations.py, visualization.py, utils.py) находятся в одной папке с bot.py")
    sys.exit(1)

# Глобальные переменные для весов (загружаем из файлов)
current_season_weights = load_settings(SETTINGS_FILE)
if current_season_weights is None:
    current_season_weights = {pos: w.copy() for pos, w in DEFAULT_METRICS_WEIGHTS.items()}
    save_settings(current_season_weights, SETTINGS_FILE)

current_match_weights = load_match_settings()
if current_match_weights is None:
    current_match_weights = {pos: w.copy() for pos, w in DEFAULT_MATCH_WEIGHTS.items()}
    save_match_settings(current_match_weights)

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

async def send_excel_file(update: Update, context: ContextTypes.DEFAULT_TYPE, df: pd.DataFrame, filename: str):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Данные')
    output.seek(0)
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=InputFile(output, filename=filename),
        caption=f"📊 {filename}"
    )

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

# -------------------- ОБРАБОТЧИКИ КОМАНД --------------------
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

# -------------------- СЕЗОННАЯ СТАТИСТИКА --------------------
async def season_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    leagues = get_leagues()
    if not leagues:
        await query.edit_message_text("❌ Нет доступных лиг.")
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
        await query.edit_message_text("❌ Нет сезонов для этой лиги.")
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
        await query.edit_message_text("❌ Нет команд для этого сезона.")
        return
    keyboard = [[InlineKeyboardButton(t, callback_data=f"season_team_{t}")] for t in teams]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="season")])
    await query.edit_message_text(
        f"Лига: {league}\nСезон: {season}\nВыберите команду (можно несколько):",
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
    current_teams = context.user_data['season_teams']
    league = context.user_data.get('season_league')
    season = context.user_data.get('season_season')
    all_teams = get_teams_for_leagues_seasons([league], [season])
    keyboard = []
    for t in all_teams:
        check = "✅ " if t in current_teams else ""
        keyboard.append([InlineKeyboardButton(f"{check}{t}", callback_data=f"season_team_{t}")])
    keyboard.append([InlineKeyboardButton("📊 Показать рейтинг", callback_data="season_show")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="season")])
    await query.edit_message_text(
        f"Лига: {league}\nСезон: {season}\nВыбрано команд: {len(current_teams)}\nНажмите на команду для выбора/снятия.",
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
    all_metrics = [m for m in ALL_POSSIBLE_METRICS if m in df_rated.columns]
    mandatory = ['ttd_actions_p90', 'ttd_opp_actions_p90']
    display_metrics = [m for m in all_metrics if m in mandatory or m in ['goals_p90', 'assists_p90', 'xG_p90', 'key_passes_p90']]
    if not display_metrics:
        display_metrics = all_metrics[:5]
    df_main = build_main_table(df_rated, display_metrics)
    filename = f"season_rating_{league}_{season}.xlsx"
    await send_excel_file(update, context, df_main, filename)
    await query.edit_message_text("✅ Рейтинг отправлен в Excel-файле.")

# -------------------- МАТЧЕВАЯ СТАТИСТИКА --------------------
async def match_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    leagues = get_leagues()
    if not leagues:
        await query.edit_message_text("❌ Нет доступных лиг.")
        return
    keyboard = [[InlineKeyboardButton(l, callback_data=f"match_league_{l}")] for l in leagues]
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
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="match")])
    await query.edit_message_text("Выберите матч(и) (можно несколько):", reply_markup=InlineKeyboardMarkup(keyboard))

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
    league = context.user_data.get('match_league')
    matches = get_matches_for_league(league)
    keyboard = []
    for m in matches:
        label = f"{m[1]} ({m[3]}) {m[4]} vs {m[5]}"
        check = "✅ " if m[0] in context.user_data['match_ids'] else ""
        keyboard.append([InlineKeyboardButton(f"{check}{label}", callback_data=f"match_select_{m[0]}")])
    keyboard.append([InlineKeyboardButton("📊 Показать статистику", callback_data="match_show")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="match")])
    await query.edit_message_text(
        f"Выбрано матчей: {len(context.user_data['match_ids'])}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def match_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_ids = context.user_data.get('match_ids', [])
    if not match_ids:
        await query.edit_message_text("❌ Выберите хотя бы один матч.")
        return
    await query.edit_message_text("⏳ Загружаю данные матча...")
    match_id = match_ids[0]  # берём первый выбранный
    loop = asyncio.get_running_loop()
    df_match = await loop.run_in_executor(None, load_match_stats, match_id, None)
    if df_match.empty:
        await query.edit_message_text("❌ Нет данных для этого матча.")
        return
    df_rated = await loop.run_in_executor(None, calculate_match_ratings, df_match, current_match_weights)
    df_rated = df_rated.sort_values('rating', ascending=False).reset_index(drop=True)
    league_avg = await loop.run_in_executor(None, get_league_averages, context.user_data.get('match_league'), None)
    all_metrics = [m for m in MATCH_ALL_METRICS if m in df_rated.columns]
    if 'ttd_actions' in df_rated.columns:
        all_metrics.append('ttd_actions')
    if 'ttd_opp_actions' in df_rated.columns:
        all_metrics.append('ttd_opp_actions')
    display_metrics = all_metrics[:8]
    df_main = build_match_main_table(df_rated, display_metrics, league_avg=league_avg, player_season_map=None)
    filename = f"match_{match_id}.xlsx"
    await send_excel_file(update, context, df_main, filename)
    await query.edit_message_text("✅ Матчевая статистика отправлена.")

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

# -------------------- ЭКСПОРТ --------------------
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

# -------------------- НАСТРОЙКА ВЕСОВ --------------------
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
    text = "Текущие веса для сезона:\n"
    for pos, weights in current_season_weights.items():
        pos_name = {'FW':'Нападающие','AM':'Атак. полузащитники','CM':'Центр. полузащитники','FB':'Крайние защитники','CB':'Центр. защитники'}.get(pos, pos)
        text += f"\n{pos_name}:\n"
        for m, w in weights.items():
            if w != 0:
                text += f"  {METRIC_NAMES_RU.get(m, m)}: {w}\n"
    keyboard = [
        [InlineKeyboardButton("🔄 Сбросить веса сезона", callback_data="reset_season_weights")],
        [InlineKeyboardButton("🔙 Назад", callback_data="weights")]
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
        [InlineKeyboardButton("🔙 Назад", callback_data="weights")]
    ]
    await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_match_weights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_match_weights
    current_match_weights = {pos: w.copy() for pos, w in DEFAULT_MATCH_WEIGHTS.items()}
    save_match_settings(current_match_weights)
    await update.callback_query.answer("Веса матчей сброшены.")
    await update.callback_query.edit_message_text("✅ Веса матчей сброшены к значениям по умолчанию.")

# -------------------- ОБРАБОТЧИК КНОПОК --------------------
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
        elif data == "match_show":
            await match_show(update, context)
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

# -------------------- ЗАПУСК БОТА --------------------
def main():
    try:
        logger.info("🚀 Запуск бота...")
        application = Application.builder().token(TOKEN).build()

        # Команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("season", season_start))
        application.add_handler(CommandHandler("match", match_start))
        application.add_handler(CommandHandler("radar", radar_start))
        application.add_handler(CommandHandler("export", export_start))
        application.add_handler(CommandHandler("weights", weights_start))

        # Обработчики кнопок
        application.add_handler(CallbackQueryHandler(button_handler))

        # Обработчик текста для радара
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, radar_input))

        logger.info("✅ Бот успешно запущен и готов к работе.")
        application.run_polling()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
