import os
import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from yt_dlp import YoutubeDL
from pydub import AudioSegment
from aiohttp import web
import requests

logging.basicConfig(level=logging.INFO)
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("Русский", callback_data="lang_ru"),
         InlineKeyboardButton("English", callback_data="lang_en")]
    ])

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("Искать трек", callback_data="search")]
    ])

def track_kb(entry_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("Полный трек 320kbps", callback_data=f"full_{entry_id}")],
        [InlineKeyboardButton("Текст песни", callback_data=f"lyrics_{entry_id}")],
        [InlineKeyboardButton("Похожие", callback_data=f"related_{entry_id}")]
    ])

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Выбери язык", reply_markup=start_kb())

@dp.callback_query(lambda c: c.data in ["lang_ru", "lang_en"])
async def set_lang(call: CallbackQuery):
    await call.message.edit_text("Готово! Кидай ссылку или название", reply_markup=main_kb())

@dp.callback_query(lambda c: c.data == "search")
async def go_search(call: CallbackQuery):
    await call.message.edit_text("Кидай ссылку или название трека!\nSpotify • YouTube • Apple • Deezer • VK • SoundCloud")

@dp.message()
async def handle(message: types.Message):
    query = message.text.strip()
    if not query: return

    status = await message.answer("Ищу…")

    search = query if re.search(r"https?://", query) else f"ytsearch1:{query}"

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': False,
        'outtmpl': '%(id)s.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
        'noplaylist': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'retries': 15,
        'fragment_retries': 15,
        'socket_timeout': 30,
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search, download=True)

        entry_id = info['id']
        title = info.get('title', 'Unknown')
        artist = info.get('artist') or info.get('uploader', 'Unknown')
        duration = info.get('duration')
        thumb = info.get('thumbnail')

        mp3 = None
        for f in os.listdir('.'):
            if entry_id in f and f.endswith('.mp3'):
                mp3 = f
                break

        if not mp3:
            await status.edit_text("Не смог скачать аудио")
            return

        # превью 30 сек
        audio = AudioSegment.from_mp3(mp3)
        preview = audio[:30000]
        preview_path = f"prev_{entry_id}.mp3"
        preview.export(preview_path, format="mp3")

        await status.delete()
        with open(preview_path, "rb") as f:
            await message.answer_audio(
                audio=BufferedInputFile(f.read(), f"{title} — превью.mp3"),
                title=title,
                performer=artist,
                duration=30,
                thumbnail=thumb,
                reply_markup=track_kb(entry_id)
            )
        os.remove(preview_path)
        os.rename(mp3, f"full_{entry_id}.mp3")

    except Exception as e:
        logging.error(e)
        await status.edit_text("Ошибка. Попробуй другую ссылку")

@dp.callback_query(lambda c: c.data.startswith("full_"))
async def send_full(call: CallbackQuery):
    entry_id = call.data.split("_", 1)[1]
    path = f"full_{entry_id}.mp3"
    if not os.path.exists(path):
        await call.answer("Файл удалён — ищи заново", show_alert=True)
        return
    with open(path, "rb") as f:
        await call.message.edit_media(
            media=types.InputMediaAudio(f.read(), caption="Полный трек 320kbps"),
            reply_markup=call.message.reply_markup
        )
    os.remove(path)

@dp.callback_query(lambda c: c.data.startswith("lyrics_"))
async def lyrics(call: CallbackQuery):
    title = call.message.audio.title if hasattr(call.message, "audio") else "Unknown"
    artist = call.message.audio.performer if hasattr(call.message, "audio") else "Unknown"
    try:
        r = requests.get(f"https://api.lyrics.ovh/v1/{artist}/{title}", timeout=5).json()
        text = r.get("lyrics", "Текст не найден")
        await call.message.answer(f"📝 {title} — {artist}\n\n{text[:3900]}")
    except:
        await call.answer("Текст не найден", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("related_"))
async def related(call: CallbackQuery):
    await call.answer("Скоро добавлю", show_alert=True)

async def web_server():
    app = web.Application()
    app.router.add_get('/', lambda _: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()

async def main():
    asyncio.create_task(web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
