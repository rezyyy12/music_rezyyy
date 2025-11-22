import os
import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from yt_dlp import YoutubeDL
import re

logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv("BOT_TOKEN"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DB = "users.db"

langs = {
    "ru": {
        "start": "🎧 Выбери язык",
        "main_menu": "🎵 Главное меню",
        "search": "🔍 Искать трек",
        "profile": "👤 Профиль",
        "settings": "⚙️ Настройки",
        "send_link": "Кидай ссылку или название трека!\nSpotify • YouTube • Apple Music • Deezer • VK • SoundCloud",
        "wrong": "Бро, кидай только ссылку или название трека 😅",
        "error": "❌ Не смог скачать, попробуй другую ссылку или название",
        "search_count": "Ты нашёл треков: {}"
    }
    # другие языки добавишь сам если надо
}

async def get_lang(user_id):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else "ru"

async def set_lang(user_id, lang):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO users (user_id, lang, searches) VALUES (?, ?, COALESCE((SELECT searches FROM users WHERE user_id = ?), 0))", (user_id, lang, user_id))
        await db.commit()

async def add_search(user_id):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET searches = searches + 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_searches(user_id):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT searches FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'ru', searches INTEGER DEFAULT 0)")
        await db.commit()

def main_keyboard(lang):
    t = langs[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["search"], callback_data="search")],
        [InlineKeyboardButton(text=t["profile"], callback_data="profile")],
        [InlineKeyboardButton(text=t["settings"], callback_data="settings")]
    ])

def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_ua")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton(text="🇩🇪 Deutsch", callback_data="lang_de")]
    ])

@dp.message(CommandStart())
async def start(message: Message):
    await set_lang(message.from_user.id, "ru")
    await message.answer(langs["ru"]["start"], reply_markup=lang_keyboard())

@dp.callback_query(lambda c: c.data.startswith("lang_"))
async def set_language(call: CallbackQuery):
    lang = call.data.split("_")[1]
    await set_lang(call.from_user.id, lang)
    t = langs.get(lang, langs["ru"])
    await call.message.edit_text(t["main_menu"], reply_markup=main_keyboard(lang))

@dp.callback_query(lambda c: c.data == "back")
async def back(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    t = langs.get(lang, langs["ru"])
    await call.message.edit_text(t["main_menu"],"], reply_markup=main_keyboard(lang))

@dp.callback_query(lambda c: c.data == "search")
async def search(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    t = langs.get(lang, langs["ru"])
    await call.message.edit_text(t["send_link"])

@dp.callback_query(lambda c: c.data == "profile")
async def profile(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    t = langs.get(lang, langs["ru"])
    searches = await get_searches(call.from_user.id)
    await call.message.edit_text(t["search_count"].format(searches), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]))

@dp.callback_query(lambda c: c.data == "settings")
async def settings(call: CallbackQuery):
    await call.message.edit_text("⚙️ Настройки скоро будут", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]))

# Ругань на всё кроме текста
@dp.message(lambda message: not message.text)
async def wrong(message: Message):
    lang = await get_lang(message.from_user.id)
    t = langs.get(lang, langs["ru"])
    await message.answer(t["wrong"])

# Основная обработка ссылок и поиска
@dp.message()
async def handle_text(message: Message):
    await add_search(message.from_user.id)
    await message.answer("🔍 Ищу…")

    query = message.text.strip()
    search_query = query if re.search(r"https?://", query) else f"ytsearch:{query}"

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'outtmpl': '%(id)s.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=True)
            title = info.get('title', 'Unknown')
            artist = info.get('uploader', info.get('artist', 'Unknown'))
            duration = info.get('duration')
            thumb = info.get('thumbnail')

            files = [f for f in os.listdir('.') if f.endswith('.mp3')]
            if not files:
                lang = await get_lang(message.from_user.id)
                await message.answer(langs.get(lang, langs["ru"])["error"])
                return

            path = max(files, key=os.path.getctime)  # берём самый свежий
            with open(path, 'rb') as audio_file:
                await message.answer_audio(
                    audio=BufferedInputFile(audio_file.read(), filename=f"{title}.mp3"),
                    title=title,
                    performer=artist,
                    duration=duration,
                    thumbnail=thumb
                )
            os.remove(path)
    except Exception as e:
        logging.error(e)
        lang = await get_lang(message.from_user.id)
        await message.answer(langs.get(lang, langs["ru"])["error"])

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
