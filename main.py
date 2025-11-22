import os
import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from yt_dlp import YoutubeDL
import re
import tempfile

logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv("BOT_TOKEN"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DB = "users.db"

# Языки
langs = {
    "ru": {"start": "🎧 Выбери язык / Обери мову", "main_menu": "🎵 Главное меню", "search": "🔍 Искать трек", "profile": "👤 Профиль", "settings": "⚙️ Настройки",
           "send_link": "Кидай ссылку на трек!\nПоддерживаю: Spotify, YouTube, Apple Music, Deezer, VK, SoundCloud", "search_count": "Вы искали треков: {}", "add_track": "🎤 Добавить свой трек (кинь mp3 файл)", 
           "support": "📞 Поддержка", "donate": "💰 Донат", "donate_text": "Вы можете задонатить для поддержки бота ❤️\n@t.me/send?start=IVOVPkOps64C", "lang": "🌍 Язык", "choose_lang": "Выберите язык:"},
    "ua": {"start": "🎧 Обери мову", "main_menu": "🎵 Головне меню", "search": "🔍 Шукати трек", "profile": "👤 Профіль", "settings": "⚙️ Налаштування",
           "send_link": "Кидай посилання на трек!\nПідтримую: Spotify, YouTube, Apple Music, Deezer, VK, SoundCloud", "search_count": "Ви шукали треків: {}", "add_track": "🎤 Додати свій трек (кинь mp3)", 
           "support": "📞 Підтримка", "donate": "💰 Донат", "donate_text": "Ви можете задонатити для підтримки ❤️\n@t.me/send?start=IVOVPkOps64C", "lang": "🌍 Мова", "choose_lang": "Оберіть мову:"},
    "en": {"start": "🎧 Choose language", "main_menu": "🎵 Main menu", "search": "🔍 Search track", "profile": "👤 Profile", "settings": "⚙️ Settings",
           "send_link": "Send track link!\nSupported: Spotify, YouTube, Apple Music, Deezer, VK, SoundCloud", "search_count": "Tracks searched: {}", "add_track": "🎤 Add your track (send mp3)", 
           "support": "📞 Support", "donate": "💰 Donate", "donate_text": "You can donate to support the bot ❤️\n@t.me/send?start=IVOVPkOps64C", "lang": "🌍 Language", "choose_lang": "Choose language:"},
    "de": {"start": "🎧 Sprache wählen", "main_menu": "🎵 Hauptmenü", "search": "🔍 Titel suchen", "profile": "👤 Profil", "settings": "⚙️ Einstellungen",
           "send_link": "Link zum Titel schicken!\nUnterstützt: Spotify, YouTube, Apple Music, Deezer, VK, SoundCloud", "search_count": "Titel gesucht: {}", "add_track": "🎤 Eigenen Titel hinzufügen (mp3 senden)", 
           "support": "📞 Support", "donate": "💰 Spende", "donate_text": "Du kannst spenden um den Bot zu unterstützen ❤️\n@t.me/send?start=IVOVPkOps64C", "lang": "🌍 Sprache", "choose_lang": "Sprache wählen:"}
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
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'ru',
            searches INTEGER DEFAULT 0
        )""")
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
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
         InlineKeyboardButton("🇺🇦 Українська", callback_data="lang_ua")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
         InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")]
    ])

def settings_keyboard(lang):
    t = langs[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["support"], url="https://t.me/the_rezyyy")],
        [InlineKeyboardButton(text=t["donate"], callback_data="donate")],
        [InlineKeyboardButton(text=t["lang"], callback_data="change_lang")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ])

class AddTrack(StatesGroup):
    waiting = State()

@dp.message(CommandStart())
async def start(message: Message):
    await set_lang(message.from_user.id, "ru")
    await message.answer(langs["ru"]["start"], reply_markup=lang_keyboard())

@dp.callback_query(lambda c: c.data.startswith("lang_"))
async def set_language(call: CallbackQuery):
    lang = call.data.split("_")[1]
    await set_lang(call.from_user.id, lang)
    t = langs[lang]
    await call.message.edit_text(t["main_menu"], reply_markup=main_keyboard(lang))

@dp.callback_query(lambda c: c.data == "back")
async def back(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    await call.message.edit_text(langs[lang]["main_menu"], reply_markup=main_keyboard(lang))

@dp.callback_query(lambda c: c.data == "search")
async def search(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    t = langs[lang]
    await call.message.edit_text(t["send_link"])

@dp.callback_query(lambda c: c.data == "profile")
async def profile(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    t = langs[lang]
    searches = await get_searches(call.from_user.id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["add_track"], callback_data="add_own")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ])
    await call.message.edit_text(t["search_count"].format(searches), reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "add_own")
async def add_own(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(call.from_user.id)
    t = langs[lang]
    await state.set_state(AddTrack.waiting)
    await call.message.edit_text(t["add_track"])

@dp.message(AddTrack.waiting)
async def receive_own_track(message: Message, state: FSMContext):
    if not message.audio and not message.document:
        return
    lang = await get_lang(message.from_user.id)
    t = langs[lang]
    await add_search(message.from_user.id)
    file = message.audio or message.document
    await message.answer_audio(
        audio=file.file_id,
        title=file.title or "Your track",
        performer=file.performer or message.from_user.username or "Unknown"
    )
    await state.clear()
    await message.answer(t["main_menu"], reply_markup=main_keyboard(lang))

@dp.callback_query(lambda c: c.data == "settings")
async def settings(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    await call.message.edit_text("⚙️", reply_markup=settings_keyboard(lang))

@dp.callback_query(lambda c: c.data == "change_lang")
async def change_lang(call: CallbackQuery):
    await call.message.edit_reply_markup(reply_markup=lang_keyboard())

@dp.callback_query(lambda c: c.data == "donate")
async def donate(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    t = langs[lang]
    await call.message.edit_text(t["donate_text"], reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("🔙 Назад", callback_data="back")]]))

# ============ ОБРАБОТКА ССЫЛОК ============
SPOTIFY_REGEX = re.compile(r"https?://open\.spotify\.com/track/([a-zA-Z0-9]+)")
YOUTUBE_REGEX = re.compile(r"https?://(www\.)?(youtube\.com|youtu\.be)/.+")
APPLE_REGEX = re.compile(r"https?://music\.apple\.com/.+/song/.+")
DEEZER_REGEX = re.compile(r"https?://deezer\.com/.+/track/\d+")
SOUNDCLOUD_REGEX = re.compile(r"https?://soundcloud\.com/.+/.+")
VK_REGEX = re.compile(r"https?://vk\.com/audio.+")

async def download_and_send(url: str, message: Message):
    await add_search(message.from_user.id)
    await message.answer("🔍")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'outtmpl': '%(id)s.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
    }
    
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url if "ytsearch" in url or "youtube" in url else f"ytsearch:{url}", download= not ("youtube.com" in url or "youtu.be" in url))
            if not info:
                info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown')
            artist = info.get('uploader', info.get('artist', 'Unknown'))
            duration = info.get('duration')
            thumb = info.get('thumbnail')

            files = [f for f in os.listdir('.') if f.startswith(info.get('id', 'temp')) and f.endswith('.mp3')]
            if not files:
                await message.answer("❌ Не удалось скачать")
                return
            path = files[0]
            
            with open(path, 'rb') as f:
                await message.answer_audio(
                    audio=BufferedInputFile(f.read(), f"{title}.mp3"),
                    title=title,
                    performer=artist,
                    duration=duration,
                    thumbnail=thumb
                )
            os.remove(path)
        except Exception as e:
            await message.answer(f"❌ Ошибка")

@dp.message()
async def handle_message(message: Message):
    text = message.text or ""
    if any(r.search(text) for r in [SPOTIFY_REGEX, YOUTUBE_REGEX, APPLE_REGEX, DEEZER_REGEX, SOUNDCLOUD_REGEX, VK_REGEX]):
        await download_and_send(text, message)
    else:
        await download_and_send(f"ytsearch:{text}", message)

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
