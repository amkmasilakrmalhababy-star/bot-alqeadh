import asyncio
import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta

import aiosqlite
from better_profanity import profanity
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ==========================
# ENV & LOGGING
# ==========================

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ChaosProBot")

# ==========================
# GLOBALS
# ==========================

DB_PATH = "chaos_pro.db"
SPAM_LIMIT = 6
SPAM_WINDOW = 8
MUTE_DURATION = 30

spam_tracker = defaultdict(list)
competition_cache = {}

# ==========================
# DATABASE
# ==========================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER,
            chat_id INTEGER,
            points INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, chat_id)
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS competitions(
            chat_id INTEGER PRIMARY KEY,
            question TEXT,
            answer TEXT,
            active INTEGER
        )
        """)
        await db.commit()

async def add_points(user_id, chat_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO users(user_id, chat_id, points)
        VALUES(?,?,?)
        ON CONFLICT(user_id, chat_id)
        DO UPDATE SET points = points + ?
        """, (user_id, chat_id, amount, amount))
        await db.commit()

async def get_points(user_id, chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
        SELECT points FROM users
        WHERE user_id=? AND chat_id=?
        """, (user_id, chat_id)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def add_warning(user_id, chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO users(user_id, chat_id, warnings)
        VALUES(?,?,1)
        ON CONFLICT(user_id, chat_id)
        DO UPDATE SET warnings = warnings + 1
        """, (user_id, chat_id))
        await db.commit()

async def get_warnings(user_id, chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
        SELECT warnings FROM users
        WHERE user_id=? AND chat_id=?
        """, (user_id, chat_id)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

# ==========================
# ADMIN CHECK
# ==========================

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(
        update.effective_chat.id,
        update.effective_user.id
    )
    return member.status in ["administrator", "creator"]

# ==========================
# ANTI SPAM
# ==========================

async def anti_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = time.time()

    spam_tracker[user_id] = [
        t for t in spam_tracker[user_id]
        if now - t < SPAM_WINDOW
    ]

    spam_tracker[user_id].append(now)

    if len(spam_tracker[user_id]) > SPAM_LIMIT:
        await update.message.reply_text("🚫 سبام مرفوض. تم كتمك مؤقتًا.")
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=datetime.utcnow() + timedelta(seconds=MUTE_DURATION)
        )

# ==========================
# BAD WORD FILTER
# ==========================

async def profanity_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if profanity.contains_profanity(text):
        await update.message.delete()
        await add_warning(update.effective_user.id, update.effective_chat.id)
        warnings = await get_warnings(update.effective_user.id, update.effective_chat.id)

        if warnings >= 3:
            await context.bot.restrict_chat_member(
                update.effective_chat.id,
                update.effective_user.id,
                ChatPermissions(can_send_messages=False),
                until_date=datetime.utcnow() + timedelta(minutes=5)
            )
            await update.message.reply_text("🚫 تم كتمك بسبب تكرار الألفاظ السيئة.")
        else:
            await update.message.reply_text("⚠️ تحذير بسبب ألفاظ غير لائقة.")

# ==========================
# HELP MENU (PRIVATE)
# ==========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📩 تم إرسال القائمة في الخاص.")
    keyboard = [
        [InlineKeyboardButton("🎮 مسابقات", callback_data="help_games")],
        [InlineKeyboardButton("💰 نقاط", callback_data="help_points")],
        [InlineKeyboardButton("👮 إدارة", callback_data="help_admin")],
    ]
    await context.bot.send_message(
        update.effective_user.id,
        "🔥 قائمة بوت Chaos Pro",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "help_games":
        await query.edit_message_text("/competition السؤال | الجواب\n/stop")
    elif query.data == "help_points":
        await query.edit_message_text("/points\n/top")
    elif query.data == "help_admin":
        await query.edit_message_text("/ban (رد على شخص)\n/mute\n/unmute")

# ==========================
# MAIN (FIXED)
# ==========================

def main():
    asyncio.run(init_db())

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(help_buttons))
    app.add_handler(CommandHandler("competition", competition))
    app.add_handler(CommandHandler("stop", stop_comp))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("top", top))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_spam))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, profanity_filter))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_answer))

    logger.info("Chaos Pro Bot Started")
    app.run_polling()

if __name__ == "__main__":
    main())
logger = logging.getLogger("ChaosProBot")

# ==========================
# GLOBALS
# ==========================

DB_PATH = "chaos_pro.db"
SPAM_LIMIT = 6
SPAM_WINDOW = 8
MUTE_DURATION = 30

spam_tracker = defaultdict(list)
competition_cache = {}

# ==========================
# DATABASE
# ==========================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER,
            chat_id INTEGER,
            points INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, chat_id)
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS competitions(
            chat_id INTEGER PRIMARY KEY,
            question TEXT,
            answer TEXT,
            active INTEGER
        )
        """)
        await db.commit()

async def add_points(user_id, chat_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO users(user_id, chat_id, points)
        VALUES(?,?,?)
        ON CONFLICT(user_id, chat_id)
        DO UPDATE SET points = points + ?
        """, (user_id, chat_id, amount, amount))
        await db.commit()

async def get_points(user_id, chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
        SELECT points FROM users
        WHERE user_id=? AND chat_id=?
        """, (user_id, chat_id)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def add_warning(user_id, chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO users(user_id, chat_id, warnings)
        VALUES(?,?,1)
        ON CONFLICT(user_id, chat_id)
        DO UPDATE SET warnings = warnings + 1
        """, (user_id, chat_id))
        await db.commit()

async def get_warnings(user_id, chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
        SELECT warnings FROM users
        WHERE user_id=? AND chat_id=?
        """, (user_id, chat_id)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

# ==========================
# ADMIN CHECK
# ==========================

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(
        update.effective_chat.id,
        update.effective_user.id
    )
    return member.status in ["administrator", "creator"]

# ==========================
# ANTI SPAM
# ==========================

async def anti_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = time.time()

    spam_tracker[user_id] = [
        t for t in spam_tracker[user_id]
        if now - t < SPAM_WINDOW
    ]

    spam_tracker[user_id].append(now)

    if len(spam_tracker[user_id]) > SPAM_LIMIT:
        await update.message.reply_text("🚫 سبام مرفوض. تم كتمك مؤقتًا.")
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=datetime.utcnow() + timedelta(seconds=MUTE_DURATION)
        )

# ==========================
# BAD WORD FILTER
# ==========================

async def profanity_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if profanity.contains_profanity(text):
        await update.message.delete()
        await add_warning(update.effective_user.id, update.effective_chat.id)
        warnings = await get_warnings(update.effective_user.id, update.effective_chat.id)

        if warnings >= 3:
            await context.bot.restrict_chat_member(
                update.effective_chat.id,
                update.effective_user.id,
                ChatPermissions(can_send_messages=False),
                until_date=datetime.utcnow() + timedelta(minutes=5)
            )
            await update.message.reply_text("🚫 تم كتمك بسبب تكرار الألفاظ السيئة.")
        else:
            await update.message.reply_text("⚠️ تحذير بسبب ألفاظ غير لائقة.")

# ==========================
# HELP MENU (PRIVATE)
# ==========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📩 تم إرسال القائمة في الخاص.")
    keyboard = [
        [InlineKeyboardButton("🎮 مسابقات", callback_data="help_games")],
        [InlineKeyboardButton("💰 نقاط", callback_data="help_points")],
        [InlineKeyboardButton("👮 إدارة", callback_data="help_admin")],
    ]
    await context.bot.send_message(
        update.effective_user.id,
        "🔥 قائمة بوت Chaos Pro",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "help_games":
        await query.edit_message_text(
            "/competition السؤال | الجواب\n"
            "/stop"
        )
    elif query.data == "help_points":
        await query.edit_message_text(
            "/points\n/top"
        )
    elif query.data == "help_admin":
        await query.edit_message_text(
            "/ban (رد على شخص)\n"
            "/mute\n/unmute"
        )

# ==========================
# COMPETITION
# ==========================

async def competition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    text = " ".join(context.args)
    if "|" not in text:
        await update.message.reply_text("الصيغة:\n/competition السؤال | الجواب")
        return

    question, answer = map(str.strip, text.split("|"))

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT OR REPLACE INTO competitions(chat_id, question, answer, active)
        VALUES(?,?,?,1)
        """, (update.effective_chat.id, question, answer.lower()))
        await db.commit()

    await update.message.reply_text(f"🎯 مسابقة جديدة:\n{question}")

async def stop_comp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        UPDATE competitions SET active=0
        WHERE chat_id=?
        """, (update.effective_chat.id,))
        await db.commit()

    await update.message.reply_text("🛑 تم إيقاف المسابقة.")

async def check_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
        SELECT answer, active FROM competitions
        WHERE chat_id=?
        """, (update.effective_chat.id,)) as cursor:
            row = await cursor.fetchone()

    if row and row[1] == 1:
        if update.message.text.lower() == row[0]:
            await add_points(update.effective_user.id, update.effective_chat.id, 20)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                UPDATE competitions SET active=0
                WHERE chat_id=?
                """, (update.effective_chat.id,))
                await db.commit()

            await update.message.reply_text("🎉 إجابة صحيحة! +20 نقطة")

# ==========================
# ADMIN COMMANDS
# ==========================

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        await context.bot.ban_chat_member(update.effective_chat.id, user_id)
        await update.message.reply_text("✅ تم الحظر.")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            user_id,
            ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text("🔇 تم الكتم.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            user_id,
            ChatPermissions(can_send_messages=True)
        )
        await update.message.reply_text("🔊 تم فك الكتم.")

# ==========================
# POINTS
# ==========================

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pts = await get_points(update.effective_user.id, update.effective_chat.id)
    await update.message.reply_text(f"🏆 نقاطك: {pts}")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
        SELECT user_id, points FROM users
        WHERE chat_id=?
        ORDER BY points DESC LIMIT 10
        """, (update.effective_chat.id,)) as cursor:
            rows = await cursor.fetchall()

    text = "🏆 أفضل 10 لاعبين:\n"
    for i, row in enumerate(rows, 1):
        text += f"{i}- {row[1]} نقطة\n"

    await update.message.reply_text(text)

# ==========================
# MAIN
# ==========================

async def main():
    await init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(help_buttons))
    app.add_handler(CommandHandler("competition", competition))
    app.add_handler(CommandHandler("stop", stop_comp))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("top", top))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_spam))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, profanity_filter))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_answer))

    logger.info("Chaos Pro Bot Started")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
