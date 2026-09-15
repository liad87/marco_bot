import os
import asyncio
import gspread
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from oauth2client.service_account import ServiceAccountCredentials

# משיכת הטוקן ישירות ממשתני הסביבה של המחשב (כפי שהגדרת ב-setx)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEET_NAME = "inventory_events"
CREDENTIALS_FILE = "credentials.json"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# פונקציית כתיבה פשוטה לגוגל שיטס
def append_raw_message_to_sheet(user_name, message_text):
    try:
        # Under the hood, this uses the modern google-auth library
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        
        # Open the spreadsheet and access the specific sheet
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("main_events")
        print("✅ Successfully authenticated using modern google-auth framework!")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([current_time, user_name, message_text])
        return True
    
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("שלום! כל הודעה שתכתוב לי כאן תירשם מיד ובאופן אוטומטי בקובץ הגוגל שיטס.")

# מאזין לכל הודעת טקסט רגילה
@dp.message()
async def handle_any_message(message: types.Message):
    user_name = message.from_user.full_name
    user_text = message.text
    print("check_1")
    # שליחה לפונקציית הכתיבה
    success = append_raw_message_to_sheet(user_name, user_text)
    print(success)
    if success:
        await message.answer("✅ ההודעה נרשמה בהצלחה באקסל!")
    else:
        await message.answer("❌ חלה שגיאה ברישום ההודעה.")

if __name__ == "__main__":
    print("הבוט רץ ומאזין להודעות...")
    asyncio.run(dp.start_polling(bot))
