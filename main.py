import os
import asyncio
import logging
import aiosqlite
import re
import hashlib
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from yt_dlp import YoutubeDL
from pydub import AudioSegment
from aiohttp import web
import requests
from lyricsgenius import Genius

logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv("BOT_TOKEN"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DB = "users.db"
GENIUS_TOKEN = os.getenv("GENIUS_TOKEN", "")

langs = {
    "ru": {
        "start": "🎧 Выбери язык",
        "main_menu": "🎵 Главное меню",
        "search": "🔍 Искать трек",
        "profile": "👤 Профиль",
        "settings": "⚙️ Настройки",
        "send_link": "Кидай ссылку или название трека!\n📱 Spotify • YouTube • Apple Music • Deezer • VK • SoundCloud",
        "wrong": "Бро, кидай только ссылку или название трека 😅",
        "error": "❌ Не смог скачать, попробуй другую ссылку или повтори",
        "searching": "🔍 Ищу…",
        "preview": "▶️ Превью 30 сек",
        "full": "🎵 Полная версия (320kbps)",
        "lyrics": "📝 Текст песни",
        "related": "🔄 Похожие треки",
        "save": "💾 Сохранить в плейлист",
        "search_count": "Ты нашёл треков: {}",
        "cached": "Из кэша! 🚀",
        "no_lyrics": "Текст не найден 😔"
    },
    "en": {
        "start": "🎧 Choose language",
        "main_menu": "🎵 Main menu",
        "search": "🔍 Search track",
        "profile": "👤 Profile",
        "settings": "⚙️ Settings",
        "send_link": "Send link or track name!\n📱 Spotify • YouTube • Apple Music • Deezer • VK • SoundCloud",
        "wrong": "Bro, send only link or track name 😅",
        "error": "❌ Couldn't download, try another link",
        "searching": "🔍 Searching…",
        "preview": "▶️ 30s preview",
        "full": "🎵 Full version (320kbps)",
        "lyrics": "📝 Lyrics",
        "related": "🔄 Related tracks",
        "save": "💾 Save to playlist",
        "search_count": "You found tracks: {}",
        "cached": "From cache! 🚀",
        "no_lyrics": "Lyrics not found 😔"
    },
    "ua": {
        "start": "🎧 Оберіть мову",
        "main_menu": "🎵 Головне меню",
        "search": "🔍 Шукати трек",
        "profile": "👤 Профіль",
        "settings": "⚙️ Налаштування",
        "send_link": "Надішліть посилання або назву треку!\n📱 Spotify • YouTube • Apple Music • Deezer • VK • SoundCloud",
        "wrong": "Бро, надсилай тільки посилання або назву треку 😅",
        "error": "❌ Не зміг завантажити, спробуй інше посилання",
        "searching": "🔍 Шукаю…",
        "preview": "▶️ Прев'ю 30 сек",
        "full": "🎵 Повна версія (320kbps)",
        "lyrics": "📝 Текст пісні",
        "related": "🔄 Схожі треки",
        "save": "💾 Зберегти в плейлист",
        "search_count": "Ти знайшов треків: {}",
        "cached": "З кешу! 🚀",
        "no_lyrics": "Текст не знайдено 😔"
    },
    "de": {
        "start": "🎧 Sprache wählen",
        "main_menu": "🎵 Hauptmenü",
        "search": "🔍 Track suchen",
        "profile": "👤 Profil",
        "settings": "⚙️ Einstellungen",
        "send_link": "Schicke Link oder Track-Namen!\n📱 Spotify • YouTube • Apple Music • Deezer • VK • SoundCloud",
        "wrong": "Bro, schicke nur Link oder Track-Namen 😅",
        "error": "❌ Konnte nicht herunterladen, versuche einen anderen Link",
        "searching": "🔍 Suche…",
        "preview": "▶️ 30s Vorschau",
        "full": "🎵 Volle Version (320kbps)",
        "lyrics": "📝 Songtext",
        "related": "🔄 Ähnliche Tracks",
        "save": "💾 In Playlist speichern",
        "search_count": "Du hast Tracks gefunden: {}",
        "cached": "Aus Cache! 🚀",
        "no_lyrics": "Songtext nicht gefunden 😔"
    }
}

async def get_lang(user_id):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else "ru"

async def set_lang(user_id, lang):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO users (user_id, lang, searches, playlist) VALUES (?, ?, COALESCE((SELECT searches FROM users WHERE user_id = ?), 0), COALESCE((SELECT playlist FROM users WHERE user_id = ?), ''))", (user_id, lang, user_id, user_id))
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

async def cache_track(user_id, entry_id, title, artist, file_path):
    hash_file = hashlib.md5(open(file_path, 'rb').read()).hexdigest()
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO tracks (user_id, entry_id, title, artist, hash) VALUES (?, ?, ?, ?, ?)", (user_id, entry_id, title, artist, hash_file))
        await db.commit()

async def get_cached_track(entry_id, user_id):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT title, artist, hash FROM tracks WHERE entry_id = ? AND user_id = ?", (entry_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return row if row else None

async def get_lyrics(title, artist):
    try:
        url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('lyrics', None)
    except:
        pass
    if GENIUS_TOKEN:
        genius = Genius(GENIUS_TOKEN)
        song = genius.search_song(title, artist)
        return song.lyrics if song else None
    return None

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'ru', searches INTEGER DEFAULT 0, playlist TEXT DEFAULT '')")
        await db.execute("CREATE TABLE IF NOT EXISTS tracks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, entry_id TEXT, title TEXT, artist TEXT, hash TEXT)")
        await db.commit()

def main_keyboard(lang="ru"):
    t = langs.get(lang, langs["ru"])
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

def track_keyboard(entry_id, lang="ru"):
    t = langs.get(lang, langs["ru"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["full"], callback_data=f"full_{entry_id}")],
        [InlineKeyboardButton(text=t["lyrics"], callback_data=f"lyrics_{entry_id}")],
        [InlineKeyboardButton(text=t["related"], callback_data=f"related_{entry_id}")],
        [InlineKeyboardButton(text=t["save"], callback_data=f"save_{entry_id}")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="back")]
    ])

@dp.message(CommandStart())
async def start(message: Message):
    await set_lang(message.from_user.id, "ru")
    await message.answer(langs["ru"]["start"], reply_markup=lang_keyboard())

@dp.callback_query(F.data.startswith("lang_"))
async def set_language(call: CallbackQuery):
    lang = call.data.split("_")[1]
    await set_lang(call.from_user.id, lang)
    t = langs.get(lang, langs["ru"])
    await call.message.edit_text(t["main_menu"], reply_markup=main_keyboard(lang))

@dp.callback_query(F.data == "back")
async def back(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    t = langs.get(lang, langs["ru"])
    await call.message.edit_text(t["main_menu"], reply_markup=main_keyboard(lang))

@dp.callback_query(F.data == "search")
async def search(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    t = langs.get(lang, langs["ru"])
    await call.message.edit_text(t["send_link"])

@dp.callback_query(F.data == "profile")
async def profile(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    t = langs.get(lang, langs["ru"])
    searches = await get_searches(call.from_user.id)
    text = t["search_count"].format(searches)
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]))

@dp.message(F.text.is_empty())
async def wrong(message: Message):
    lang = await get_lang(message.from_user.id)
    t = langs.get(lang, langs["ru"])
    await message.answer(t["wrong"])

@dp.message(F.text)
async def handle_text(message: Message):
    user_id = message.from_user.id
    await add_search(user_id)
    lang = await get_lang(user_id)
    t = langs.get(lang, langs["ru"])
    await message.answer(t["searching"])

    query = message.text.strip()
    is_url = re.search(r"https?://", query)
    search = query if is_url else f"ytsearch1:{query}"

    if "spotify.com/track/" in query:
        search = re.sub(r'spotify.com/track/[^?]+', lambda m: f"ytsearch:{m.group(0).split('/')[-1]} spotify", query)
    elif "music.apple.com/" in query:
        search = re.sub(r'music.apple.com/[^/]+/[^/]+/[^?]+', lambda m: f"ytsearch:{m.group(0).split('/')[-2]} {m.group(0).split('/')[-1]} apple music", query)

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'outtmpl': '%(extractor_key)s_%(id)s.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search, download=True)
            if not info:
                raise Exception("No info")
            entry_id = info.get('id', 'unknown')
            title = info.get('title', 'Unknown')
            artist = info.get('uploader', info.get('artist', 'Unknown'))
            duration = info.get('duration', 0)
            thumb = info.get('thumbnail')

            cached = await get_cached_track(entry_id, user_id)
            if cached:
                title, artist, file_hash = cached
                await message.answer(f"{t['cached']} {title} - {artist}")
                await message.answer_audio(
                    audio=BufferedInputFile.from_file(f"{entry_id}.mp3", f"{title}.mp3"),
                    title=title, performer=artist, duration=duration, thumbnail=thumb
                )
                return

            file_path = f"{info.get('extractor_key', 'unknown')}_{entry_id}.mp3"
            if os.path.exists(file_path):
                audio = AudioSegment.from_mp3(file_path)
                preview = audio[:30000]
                preview.export("preview.mp3", format="mp3")
                with open("preview.mp3", 'rb') as f:
                    await message.answer_audio(
                        audio=BufferedInputFile(f.read(), f"{title} {t['preview']}.mp3"),
                        title=f"{title} - {t['preview']}",
                        performer=artist,
                        duration=min(30, duration),
                        thumbnail=thumb,
                        reply_markup=track_keyboard(entry_id, lang)
                    )
                os.remove("preview.mp3")
                await cache_track(user_id, entry_id, title, artist, file_path)

            if duration < 60:
                with open(file_path, 'rb') as f:
                    await message.answer_audio(
                        audio=BufferedInputFile(f.read(), f"{title}.mp3"),
                        title=title, performer=artist, duration=duration, thumbnail=thumb
                    )
                os.remove(file_path)

    except Exception as e:
        logging.error(e)
        await message.answer(t["error"])

@dp.callback_query(F.data.startswith("full_"))
async def send_full(call: CallbackQuery):
    entry_id = call.data.split("_")[1]
    await call.answer("Скачиваю full...")

@dp.callback_query(F.data.startswith("lyrics_"))
async def send_lyrics(call: CallbackQuery):
    entry_id = call.data.split("_")[1]
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT title, artist FROM tracks WHERE entry_id = ?", (entry_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                title, artist = row
                lyrics = await get_lyrics(title, artist)
                text = lyrics if lyrics else langs["ru"]["no_lyrics"]
                await call.message.answer(f"📝 {title} - {artist}\n\n{text[:4096]}")
    await call.answer()

@dp.callback_query(F.data.startswith("related_"))
async def send_related(call: CallbackQuery):
    entry_id = call.data.split("_")[1]
    ydl_opts = {'quiet': True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"{entry_id}", download=False)
        related = info.get('related_entries', [])[:3]
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{r.get('title', '')[:30]}", callback_data=f"search_{r.get('id', '')}")] for r in related])
        await call.message.answer("🔄 Похожие:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("save_"))
async def save_to_playlist(call: CallbackQuery):
    entry_id = call.data.split("_")[1]
    user_id = call.from_user.id
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT playlist FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            pl = row[0] + f",{entry_id}" if row and row[0] else entry_id
            await db.execute("UPDATE users SET playlist = ? WHERE user_id = ?", (pl, user_id))
            await db.commit()
    await call.answer("💾 Сохранено!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', lambda _: web.Response(text="Bot alive!"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Web server on port {port}")

async def main():
    await init_db()
    asyncio.create_task(web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
