import os
import logging
import sys
import asyncio
import io
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # для работы без GUI
from matplotlib.table import Table

load_dotenv()

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

# -------------------- НАБОРЫ МЕТРИК --------------------
SEASON_METRIC_SETS = {
    "Основные": ['goals_p90', 'assists_p90', 'xG_p90', 'key_passes_p90', 'pass_accuracy', 'dribbles_p90', 'tackles_p90', 'interceptions_p90'],
    "Атакующие": ['goals_p90', 'assists_p90', 'shots_on_target_p90', 'xG_p90', 'key_passes_p90', 'dribbles_p90', 'actions_opp_box_p90', 'chances_created_p90'],
    "Защитные": ['tackles_p90', 'interceptions_p90', 'ball_recoveries_p90', 'loose_ball_recoveries_p90', 'actions_opp_box_p90', 'air_challenges_won_pct'],
    "Все основные": ['goals_p90', 'assists_p90', 'xG_p90', 'shots_on_target_p90', 'key_passes_p90', 'pass_accuracy', 'dribbles_p90', 'tackles_p90', 'interceptions_p90', 'ball_recoveries_p90']
}

MATCH_METRIC_SETS = {
    "Основные": ['goals', 'assists', 'xG', 'key_passes', 'pass_accuracy', 'tackles', 'interceptions', 'shots_on_target'],
    "Атакующие": ['goals', 'assists', 'shots_on_target', 'xG', 'key_passes', 'dribbles', 'actions_opp_box', 'chances_created'],
    "Защитные": ['tackles', 'interceptions', 'ball_recoveries', 'loose_ball_recoveries', 'actions_opp_box', 'air_challenges_won_pct'],
    "Все основные": ['goals', 'assists', 'xG', 'shots_on_target', 'key_passes', 'pass_accuracy', 'tackles', 'interceptions', 'ball_recoveries', 'dribbles']
}

# -------------------- ФУНКЦИЯ РЕНДЕРИНГА ТАБЛИЦЫ В ИЗОБРАЖЕНИЕ --------------------
def render_df_to_image(df: pd.DataFrame, title: str, max_rows: int = 25) -> bytes:
    """
    Рендерит DataFrame в изображение PNG с помощью matplotlib.
    Возвращает bytes изображения.
    """
    if df.empty:
        # Возвращаем пустое изображение с текстом
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, "Нет данных", ha='center', va='center', fontsize=14)
        ax.axis('off')
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    # Ограничиваем количество строк
    if len(df) > max_rows:
        df_display = df.head(max_rows)
        footer = f"... и ещё {len(df) - max_rows} строк"
    else:
        df_display = df
        footer = ""

    # Подготавливаем данные
    # Заменяем названия колонок на русские (если есть)
    cols = []
    for c in df_display.columns:
        if c in METRIC_NAMES_RU:
            cols.append(METRIC_NAMES_RU[c])
        elif c in MATCH_METRIC_NAMES_RU:
            cols.append(MATCH_METRIC_NAMES_RU[c])
        else:
            cols.append(c)
    # Создаём список строк для таблицы
    data = [cols] + df_display.values.tolist()
    if footer:
        data.append([footer] + [''] * (len(cols) - 1))

    # Настраиваем размер фигуры
    n_rows = len(data)
    n_cols = len(cols)
    # Ширина зависит от количества колонок (каждая колонка ~1.2 дюйма)
    fig_width = max(6, n_cols * 1.2)
    fig_height = max(2, n_rows * 0.4 + 1)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis('off')

    # Создаём таблицу
    table = ax.table(cellText=data, loc='center', cellLoc='center', colWidths=[0.15] * n_cols)
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.5)

    # Стилизация заголовка
    for (i, j), cell in table.get_celld().items():
        if i == 0:  # Заголовок
            cell.set_text_props(weight='bold', color='white')
            cell.set_facecolor('#4CAF50')
        else:
            cell.set_facecolor('#f9f9f9' if i % 2 == 0 else '#ffffff')
            cell.set_text_props(color='#333333')
        cell.set_edgecolor('#dddddd')

    # Добавляем заголовок над таблицей
    ax.set_title(title, fontsize=14, weight='bold', pad=20)

    # Сохраняем в BytesIO
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=120, facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

# -------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ БОТА --------------------
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

async def send_table_image(update: Update, context: ContextTypes.DEFAULT_TYPE, df: pd.DataFrame, title: str, max_rows: int = 25):
    """Отправляет таблицу как изображение PNG."""
    img_bytes = render_df_to_image(df, title, max_rows)
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=InputFile(io.BytesIO(img_bytes), filename="table.png"),
        caption=f"📊 {title}"
    )

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

# -------------------- ОБРАБОТЧИКИ КОМАНД (СЕЗОН, МАТЧ, РАДАР, ЭКСПОРТ, ВЕСА) --------------------
# (Весь код обработчиков остаётся таким же, как в предыдущей версии, но вместо send_table используется send_table_image.
# Ниже я привожу только ключевые места, где отправляются таблицы.
# Полный код слишком длинный, но я дам его в итоговом ответе.
# В рамках этого сообщения я покажу только изменённые функции отправки таблиц.)

# В функциях season_show_final и match_show_final замените send_table на send_table_image.

async def season_show_final(update: Update, context: ContextTypes.DEFAULT_TYPE, set_name=""):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Загружаю данные...")
    league = context.user_data.get('season_league')
    season = context.user_data.get('season_season')
    teams = context.user_data.get('season_teams', [])
    metrics = context.user_data.get('season_metrics', SEASON_METRIC_SETS["Основные"])
    if not metrics:
        metrics = SEASON_METRIC_SETS["Основные"]
    loop = asyncio.get_running_loop()
    df_raw = await loop.run_in_executor(None, load_from_db, [league], [season], teams)
    df_filtered = df_raw[df_raw['minutes'] >= MIN_MINUTES].copy()
    if df_filtered.empty:
        await query.edit_message_text("❌ Нет игроков с достаточным временем.")
        return
    df_rated = await loop.run_in_executor(None, calculate_ratings, df_filtered, current_season_weights)
    df_rated = df_rated.sort_values('rating', ascending=False).reset_index(drop=True)
    display_metrics = [m for m in metrics if m in df_rated.columns]
    if not display_metrics:
        display_metrics = ['goals_p90', 'assists_p90', 'xG_p90']
    df_main = build_main_table(df_rated, display_metrics)
    # Отправляем как изображение
    await send_table_image(update, context, df_main, f"Рейтинг (лига {league}, сезон {season})", max_rows=20)
    # Предлагаем Excel и позиции
    keyboard = [
        [InlineKeyboardButton("📥 Скачать Excel (полный)", callback_data="season_download_excel")],
        [InlineKeyboardButton("📋 Показать по позициям", callback_data="season_show_positions")],
        [get_back_button("season")]
    ]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['season_df'] = df_main
    context.user_data['season_filename'] = f"season_rating_{league}_{season}.xlsx"
    context.user_data['season_df_rated'] = df_rated

async def match_show_final(update: Update, context: ContextTypes.DEFAULT_TYPE, set_name=""):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Загружаю данные матча...")
    match_id = context.user_data.get('match_active_id')
    if not match_id:
        await query.edit_message_text("❌ Не выбран активный матч.")
        return
    league = context.user_data.get('match_league')
    metrics = context.user_data.get('match_metrics', MATCH_METRIC_SETS["Основные"])
    loop = asyncio.get_running_loop()
    df_match = await loop.run_in_executor(None, load_match_stats, match_id, None)
    if df_match.empty:
        await query.edit_message_text("❌ Нет данных для этого матча.")
        return
    df_rated = await loop.run_in_executor(None, calculate_match_ratings, df_match, current_match_weights)
    df_rated = df_rated.sort_values('rating', ascending=False).reset_index(drop=True)
    league_avg = await loop.run_in_executor(None, get_league_averages, league, None)
    display_metrics = [m for m in metrics if m in df_rated.columns]
    if not display_metrics:
        display_metrics = ['goals', 'assists', 'shots_on_target', 'xG']
    df_main = build_match_main_table(df_rated, display_metrics, league_avg=league_avg, player_season_map=None)
    # Отправляем как изображение
    await send_table_image(update, context, df_main, f"Матч {match_id}", max_rows=20)
    keyboard = [
        [InlineKeyboardButton("📥 Скачать Excel (полный)", callback_data="match_download_excel")],
        [InlineKeyboardButton("📋 Показать по позициям", callback_data="match_show_positions")],
        [get_back_button("match")]
    ]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['match_df'] = df_main
    context.user_data['match_filename'] = f"match_{match_id}.xlsx"
    context.user_data['match_df_rated'] = df_rated
    context.user_data['match_league_avg'] = league_avg

# Остальные функции (season_show_positions, match_show_positions) также используют send_table_image.
# Я не привожу их полностью, но они аналогичны.

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
        logger.info("✅ Бот успешно запущен.")
        application.run_polling()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
