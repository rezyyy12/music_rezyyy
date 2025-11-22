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
