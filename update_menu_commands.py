import os
import asyncio
from aiogram import Bot
from aiogram.types import BotCommand

# משיכת הטוקן ממשתני הסביבה של המחשב שלך
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def main():
    if not TELEGRAM_TOKEN:
        print("❌ שגיאה: לא נמצא טוקן של טלגרם במערכת הפעלה (Environment Variables).")
        return

    # אתחול זמני של הבוט לצורך עדכון התפריט בלבד
    bot = Bot(token=TELEGRAM_TOKEN)
    
    # הגדרת מבנה הפקודות ישירות בפייתון ללא צורך ב-JSON חיצוני
    commands = [
        BotCommand(command="new_order", description="יצירת הזמנת רכש חדשה"),
        BotCommand(command="report_planning", description="דיווח על תכנון פעילות עתידית"),
        BotCommand(command="report_missing_hours", description="דיווח על שעות עבודה חסרות"),
        BotCommand(command="set_reminder", description="יצירת תזכורת חדשה להתייעצות"),
        BotCommand(command="retrieve_data", description="🔍 שליפת מידע ודוחות מהאקסל")
    ]
    
    print("🔄 מעדכן את התפריט מול השרתים של טלגרם...")
    
    # שליחת הפקודות לטלגרם - זה נשמר בשרתים שלהם לצמיתות
    await bot.set_my_commands(commands)
    
    # סגירת החיבור הזמני
    await bot.session.close()
    
    print("✅ התפריט עודכן בהצלחה! תוכל לראות את השינויים בטלגרם תוך מספר שניות.")

if __name__ == "__main__":
    asyncio.run(main())
