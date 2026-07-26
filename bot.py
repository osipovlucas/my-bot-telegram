import os
import asyncio
import logging
import uuid
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand
from aiogram.client.session.aiohttp import AiohttpSession
import yt_dlp

# --- CONFIGURATION ---
BOT_TOKEN = "8380665418:AAF2YoA3NO3ogtwmht34_YDMH0UEm4r7Aro"

# GramAds JWT Token
GRAMADS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1NzQ5MyIsImp0aSI6IjNiNmUxOWIwLTRhMDktNGM3Zi1hYzY1LWQzMjBmY2U5ODUxNSIsIm5hbWUiOiJDbGVhbiBWaWRlbyIsImJvdGlkIjoiMjA5NjkiLCJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9uYW1laWRlbnRpZmllciI6IjU3NDkzIiwibmJmIjoxNzg1MDc4MjM5LCJleHAiOjE3ODUyODcwMzksImlzcyI6IlN0dWdub3YiLCJhdWQiOiJVc2VycyJ9.NQeBSXhMGhHzrNo-OEuEtzPR3ze_lFcgJeyltWJXMxM"

# Mandatory Subscription (OP) Settings
SPONSOR_CHANNEL = None  # Например: "@my_channel" или None
SPONSOR_LINK = "https://t.me/your_sponsor_channel"

# Шаблон приветственного текста
START_TEXT = (
    "Hello! 🎬 I can download videos without watermarks from:\n"
    "• TikTok\n"
    "• Instagram (Reels / Posts)\n"
    "• Facebook\n"
    "• YouTube Shorts\n\n"
    "Just send me a link to the video!"
)

# Timeout 300s setup
session = AiohttpSession(timeout=300)
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('adverts')

# --- WEB SERVER FOR RENDER (FREE TIER) ---
async def handle_ping(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")

# --- REGISTRATION OF BOT MENU COMMANDS ---
async def set_bot_commands():
    """Регистрирует кнопки /start и /clear в меню Telegram"""
    commands = [
        BotCommand(command="start", description="🚀 Start / Restart the bot"),
        BotCommand(command="clear", description="🧹 Clear chat history"),
    ]
    await bot.set_my_commands(commands)

# --- GRAMADS FUNCTION ---
async def show_advert(user_id: int):
    """Sends ad post via GramAds API"""
    try:
        async with aiohttp.ClientSession() as session_http:
            async with session_http.post(
                'https://api.gramads.net/ad/SendPost',
                headers={
                    'Authorization': f'Bearer {GRAMADS_TOKEN}',
                    'Content-Type': 'application/json',
                },
                json={'SendToChatId': user_id},
            ) as response:
                if not response.ok:
                    log.error('Gramads Error: %s' % str(await response.json()))
                else:
                    log.info(f"Gramads ad sent to user {user_id}")
    except Exception as e:
        log.error(f"Failed to show Gramads ad: {e}")

# --- OP CHECK FUNCTION ---
async def check_subscription(user_id: int) -> bool:
    """Checks if user is subscribed to the sponsor channel"""
    if not SPONSOR_CHANNEL or SPONSOR_CHANNEL == "@your_sponsor_channel":
        return True

    try:
        member = await bot.get_chat_member(chat_id=SPONSOR_CHANNEL, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logging.error(f"OP check skipped/error: {e}")
        return True

# --- VIDEO DOWNLOAD ENGINE (ИСПРАВЛЕНО ДЛЯ YOUTUBE SHORTS) ---
def download_video_clean(url: str, output_path: str) -> str:
    ydl_opts = {
        # Формат с приоритетом готового MP4 (чтобы не перегружать сервер склейкой)
        'format': 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'concurrent_fragment_downloads': 1,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'extractor_args': {
            'youtube': {
                # Запрос через мобильные API/TV, чтобы обходить блок 403 и "Sign-in required"
                'player_client': ['android', 'ios', 'mweb', 'tv_embedded'],
                'skip': ['webpage', 'configs'],
            },
            'tiktok': {
                'app_version': '1.0.0',
            }
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    
    return output_path

# --- SAFE FILE REMOVAL ---
def safe_remove_file(file_path: str):
    """Safely removes temporary files without throwing Windows permission errors"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logging.warning(f"Could not remove temp file {file_path}: {e}")

# --- COMMAND HANDLERS ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(START_TEXT)

# 🧹 КОМАНДА /clear
@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    curr_id = message.message_id
    for m_id in range(curr_id, curr_id - 10, -1):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=m_id)
        except Exception:
            pass
            
    await message.answer("🧹 **Chat cleaned!**\n\n" + START_TEXT)

# --- LINK HANDLER ---

@dp.message(F.text.contains("http"))
async def process_video_link(message: types.Message):
    user_id = message.from_user.id
    url = message.text.strip()

    # 1. CHECK MANDATORY SUBSCRIPTION (OP)
    is_subscribed = await check_subscription(user_id)
    
    if not is_subscribed:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Subscribe to Channel", url=SPONSOR_LINK)],
            [InlineKeyboardButton(text="✅ I Subscribed", callback_data="check_sub")]
        ])
        await message.answer(
            "🔒 **Access Restricted!**\n\n"
            "To download videos for free, please subscribe to our sponsor channel first.\n"
            "Click the button below and confirm after subscribing:",
            reply_markup=kb
        )
        return

    # 2. DOWNLOAD PROCESS
    status_msg = await message.answer("⏳ *Downloading video, please wait...*", parse_mode="Markdown")
    unique_id = uuid.uuid4().hex[:8]
    file_path = f"video_{user_id}_{unique_id}.mp4"

    try:
        await asyncio.to_thread(download_video_clean, url, file_path)
        
        if not os.path.exists(file_path):
            await status_msg.edit_text("❌ Download failed. File was not created.")
            return

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 50:
            await status_msg.edit_text(
                "❌ File too large!\n"
                f"File size is {file_size_mb:.1f} MB. Telegram Bot API limits uploads to 50 MB max."
            )
            return

        video_file = FSInputFile(file_path)
        
        # 1. Видео с подписью
        await message.answer_video(
            video=video_file, 
            caption="✨ Download completed successfully!"
        )
        
        # 2. Приветственный текст
        await message.answer(START_TEXT)
        
        await status_msg.delete()

        # 3. SHOW GRAMADS BANNER AFTER VIDEO
        await show_advert(user_id)

    except Exception as e:
        logging.error(f"Processing error: {e}")
        await status_msg.edit_text("❌ Download failed. Please verify the link or try another video.")
    
    finally:
        safe_remove_file(file_path)

@dp.callback_query(F.data == "check_sub")
async def recheck_subscription(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed = await check_subscription(user_id)

    if is_subscribed:
        await callback.message.edit_text("✅ **Thank you for subscribing!** Please send your video link again.")
    else:
        await callback.answer("❌ You are not subscribed yet! Please subscribe to unlock downloads.", show_alert=True)

async def main():
    # Запускаем веб-сервер для поддержки бесплатного тарифа Render
    await start_web_server()
    # Устанавливаем команды в меню перед запуском
    await set_bot_commands()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
