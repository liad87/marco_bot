import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ייבוא הראוטרים מהקבצים הנפרדים
from handlers.orders import orders_router
from handlers.reminders import reminders_router, scheduler
from handlers.retrieve import retrieve_router
from handlers.planning_activity import planning_activity_router

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# 💥 הראוטרים מחוברים בחוץ - ברמת הקובץ הכללית
dp.include_router(orders_router)
dp.include_router(reminders_router)
dp.include_router(retrieve_router)
dp.include_router(planning_activity_router)

# intial start command
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("שלום! המערכת מאורגנת ומקשיבה לפקודות שלך.")

# 💥 פונקציית main() מחזיקה רק את פקודות ההפעלה בפועל
async def main():
    print("הבוט מתניע...")
    
    # הפעלת שעון העצר של התזכורות ברקע
    scheduler.start() 
    
    # הפעלת האזנה הכללית של טלגרם
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())