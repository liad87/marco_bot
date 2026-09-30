import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ייבוא הראוטרים מהקבצים הנפרדים
from handlers.orders import orders_router
from handlers.reminders import reminders_router, restore_open_reminders, scheduler
from handlers.retrieve import retrieve_router
from handlers.planning_activity import planning_activity_router
from handlers.additinal_working_hours import additional_hours_router
from handlers.daily_activity_summary import daily_summary_router
from handlers.backup import run_daily_backup
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/telegram/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# 💥 הראוטרים מחוברים בחוץ - ברמת הקובץ הכללית
dp.include_router(orders_router)
dp.include_router(reminders_router)
dp.include_router(retrieve_router)
dp.include_router(planning_activity_router)
dp.include_router(additional_hours_router)
dp.include_router(daily_summary_router)  # הוספת ראוטר לדיווח סיכום פעילות יומית

# intial start command
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("שלום! המערכת מאורגנת ומקשיבה לפקודות שלך.")

# 💥 אתחול האפליקציה מתבצע פעם אחת לפני קבלת עדכוני Telegram
async def on_startup(bot: Bot):
    print("🚀 Starting the bot...")

    # Add the backup job and restore reminders before accepting updates.
    scheduler.add_job(
        run_daily_backup,
        'cron',
        hour=2,
        minute=0
    )

    scheduler.start() 
    await restore_open_reminders(bot)

    if not WEBHOOK_BASE_URL:
        raise RuntimeError("WEBHOOK_BASE_URL must be set, for example https://your-ngrok-url.ngrok-free.app")

    webhook_url = f"{WEBHOOK_BASE_URL.rstrip('/')}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET)
    print(f"✅ Webhook is running at {webhook_url}")


async def on_shutdown(bot: Bot):
    scheduler.shutdown(wait=False)
    await bot.delete_webhook()
    await bot.session.close()


dp.startup.register(on_startup)
dp.shutdown.register(on_shutdown)

app = web.Application()
SimpleRequestHandler(
    dispatcher=dp,
    bot=bot,
    secret_token=WEBHOOK_SECRET,
).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)


if __name__ == "__main__":
    web.run_app(app, host=HOST, port=PORT)