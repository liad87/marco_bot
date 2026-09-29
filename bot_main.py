import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ייבוא הראוטרים מהקבצים הנפרדים
from handlers.orders import orders_router
from handlers.reminders import reminders_router, scheduler
from handlers.retrieve import retrieve_router
from handlers.planning_activity import planning_activity_router
from handlers.additinal_working_hours import additional_hours_router
from handlers.daily_activity_summary import daily_summary_router
from handlers.backup import run_daily_backup
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

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

# 💥 פונקציית main() מחזיקה רק את פקודות ההפעלה בפועל
async def main():
    print("🚀 Starting the bot...")

    #add backup file job to scheduler
    scheduler.add_job(
        run_daily_backup,
        'cron',
        hour=2,
        minute=0
    )

    scheduler.start() 
    
    # telegram bot polling
    await dp.start_polling(bot)
    print("✅ Bot is running!")

if __name__ == "__main__":
    asyncio.run(main())