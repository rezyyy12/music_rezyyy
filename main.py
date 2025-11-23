import os
import asyncio
import logging
import aiosqlite
import re
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from yt_dlp import YoutubeDL
from pydub import AudioSegment
from aiohttp import web
import requests

logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv("BOT_TOKEN"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DB = "users.db"

langs = {
    "ru": {"start":"Выбери язык","main_menu":"Главное меню","search":"Искать трек","profile":"Профиль","settings":"Настройки",
           "send_link":"Кидай ссылку или название трека!\nSpotify • YouTube • Apple Music • Deezer • VK • SoundCloud",
           "searching":"Ищу…","preview":"Превью 30 сек","full":"Полный трек 320kbps","lyrics":"Текст песни",
           "related":"Похожие","save":"В плейлист","error":"Не смог скачать","no_lyrics":"Текст не найден"},
    "en": {"start":"Choose language","main_menu":"Main menu","search":"Search track","profile":"Profile","settings":"Settings",
           "send_link":"Drop link or track name!\nSpotify • YouTube • Apple Music • Deezer • VK • SoundCloud",
           "searching":"Searching…","preview":"30s preview","full":"Full track 320kbps","lyrics":"Lyrics",
           "related":"Related","save":"Save to playlist","error":"Can't download","no_lyrics":"Lyrics not found"}
}

async def get_lang(user_id):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else "ru"

async def set_lang(user_id, lang):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO users(user_id,lang) VALUES(?,?)", (user_id,lang))
        await db.commit()

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'ru')")
        await db.commit()

def lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("English", callback_data="lang_en")]
    ])

def main_kb(lang):
    t = langs[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(t["search"], callback_data="search")]
    ])

def track_kb(entry_id, lang):
    t = langs[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(t["full"], callback_data=f"full_{entry_id}")],
        [InlineKeyboardButton(t["lyrics"], callback_data=f"lyrics_{entry_id}")],
        [InlineKeyboardButton(t["related"], callback_data=f"related_{entry_id}")],
        [InlineKeyboardButton(t["save"], callback_data=f"save_{entry_id}")]
    ])

@dp.message(CommandStart())
async def start(message: Message):
    await set_lang(message.from_user.id, "ru")
    await message.answer(langs["ru"]["start"], reply_markup=lang_kb())

@dp.callback_query(F.data.startswith("lang_"))
async def set_language(call: CallbackQuery):
    lang = call.data.split("_")[1]
    await set_lang(call.from_user.id, lang)
    await call.message.edit_text(langs[lang]["main_menu"], reply_markup=main_kb(lang))

@dp.callback_query(F.data == "search")
async def go_search(call: CallbackQuery):
    lang = await get_lang(call.from_user.id)
    await call.message.edit_text(langs[lang]["send_link"])

# удаляем предыдущее сообщение бота (поиск/превью)
async def delete_bot_messages(message: Message):
    try: await message.delete()
    except: pass

@dp.message(F.text)
async def handle_text(message: Message):
    user_id = message.from_user.id
    lang = await get_lang(user_id)
    t = langs[lang]

    searching = await message.answer(t["searching"])

    query = message.text.strip()
    search = query if re.search(r"https?://", query) else f"ytsearch1:{query}"

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'outtmpl': '%(id)s.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '320'}],
        'noplaylist': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'retries': 10,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search, download=True)
            if not info:
                await searching.edit_text(t["error"])
                return

            entry_id = info.get('id','unknown')
            title = info.get('title','Unknown')
            artist = info.get('uploader') or info.get('artist','Unknown')
            duration = info.get('duration')
            thumb = info.get('thumbnail')

            mp3 = next((f for f in os.listdir('.') if f.startswith(entry_id) and f.endswith('.mp3')), None)
            if not mp3:
                await searching.edit_text(t["error"])
                return

            # превью 30 сек
            audio = AudioSegment.from_mp3(mp3)
            preview = audio[:30000]
            preview_path = "preview.mp3"
            preview.export(preview_path, format="mp3")

            with open(preview_path, "rb") as f:
                await delete_bot_messages(searching)
                await message.answer_audio(
                    BufferedInputFile(f.read(), f"{title} — превью.mp3"),
                    title=title,
                    performer=artist,
                    duration=min(30, duration or 30),
                    thumbnail=thumb,
                    reply_markup=track_kb(entry_id, lang)
                )
            os.remove(preview_path)

            # сохраняем полный файл для кнопки «полный трек»
            os.rename(mp3, f"full_{entry_id}.mp3")

    except Exception as e:
        logging.error(e)
        await searching.edit_text(t["error"])

@dp.callback_query(F.data.startswith("full_"))
async def send_full(call: CallbackQuery):
    entry_id = call.data.split("_",1)[1]
    lang = await get_lang(call.from_user.id)
    t = langs[lang]
    path = f"full_{entry_id}.mp3"
    if not os.path.exists(path):
        await call.answer("Файл удалён, ищи заново")
        return
    with open(path, "rb") as f:
        await call.message.edit_media(
            media=types.InputMediaAudio(f.read(), caption=t["full"]),
            reply_markup=call.message.reply_markup
        )
    os.remove(path)

@dp.callback_query(F.data.startswith("lyrics_"))
async def send_lyrics(call: CallbackQuery):
    entry_id = call.data.split("_",1)[1]
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT title, artist FROM cache WHERE entry_id=?", (entry_id,)) as cur:
            row = await cur.fetchone()
    if row:
        title, artist = row
        try:
            r = requests.get(f"https://api.lyrics.ovh/v1/{artist}/{title}", timeout=5).json()
            lyrics = r.get("lyrics","")
            await call.message.answer(f"📝 {title} — {artist}\n\n{lyrics[:4000]}")
        except:
            await call.answer(langs[await get_lang(call.from_user.id)]["no_lyrics"])
    else:
        await call.answer("Инфо потерялась")

async def web_server():
    app = web.Application()
    app.router.add_get('/', lambda _: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()

async def main():
    await init_db()
    asyncio.create_task(web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
