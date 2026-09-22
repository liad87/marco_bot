import os
import json
from datetime import datetime
import gspread
from aiogram import Router, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, Field

# ייבוא המצב של התזכורות וייבוא ה-scheduler שנגדיר בבוט הראשי
from .states import ReminderFlow
from apscheduler.schedulers.asyncio import AsyncIOScheduler

GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "inventory_events")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CREDENTIALS_FILE = "credentials.json"

reminders_router = Router()
ai_client = genai.Client(api_key=GEMINI_API_KEY)
#start ASYNC Scheduler instance
scheduler = AsyncIOScheduler()

# 1. מבנה ה-AI לחילוץ פרטי התזכורת
class ReminderItem(BaseModel):
    topic: str = Field(description="נושא או גוף התזכורת בלבד (ללא תיאורי הזמן, למשל: 'להתייעץ עם משה')")
    target_date: str = Field(description="התאריך המבוקש לתזכורת בפורמט YYYY-MM-DD בלבד")
    target_time: str = Field(description="השעה המבוקשת לתזכורת בפורמט HH:MM בלבד (בפורמט 24 שעות). אם לא צוינה שעה, ברירת המחדל היא 09:00")

# 2. פונקציה שנפלטת אוטומטית על ידי ה-Scheduler ברגע שהזמן מגיע
async def send_scheduled_reminder(bot: Bot, chat_id: int, topic: str):
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=f"⏰ *תזכורת אוטומטית!*\n\nהגיע הזמן לבצע:\n📌 {topic}",
            parse_mode="Markdown"
        )
        print(f"🔔 נוטיפיקציה נשלחה בהצלחה ל-Chat ID: {chat_id}")
    except Exception as e:
        print(f"❌ שגיאה בשליחת נוטיפיקציה מתוזמנת: {e}")

# 3. פונקציית הכתיבה הכפולה לגוגל שיטס
def save_reminder_to_sheets(chat_id, message_id, user_name, raw_message, extracted_data):
    try:
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # א) כתיבה ללשונית המרכזית
        main_sheet = spreadsheet.worksheet("main_events")
        main_sheet.append_row([current_date_time, chat_id, message_id, "set_reminder", user_name, raw_message])
        
        # ב) כתיבה ללשונית התזכורות המורחבת (5 עמודות)
        reminder_sheet = spreadsheet.worksheet("reminders")
        reminder_sheet.append_row([
            current_date_time,
            chat_id,
            message_id,
            user_name, 
            extracted_data.get("topic"), 
            extracted_data.get("target_date"), 
            extracted_data.get("target_time")
        ])
        return True
    except Exception as e:
        print(f"❌ Error writing reminder to sheets: {e}")
        return False

# --- פקודה ראשונית ---
@reminders_router.message(Command("set_reminder"))
async def handle_reminder_command(message: types.Message, state: FSMContext):
    await message.answer("🔔 על מה תרצה שאזכיר לך להתייעץ ומתי? (כתוב בטקסט חופשי, למשל: 'תזכיר לי להתייעץ עם משה מחר ב-14:00'):")
    await state.set_state(ReminderFlow.waiting_for_reminder)

# --- קבלת ההודעה, עיבוד Gemini ותזמון הנוטיפיקציה ---
@reminders_router.message(ReminderFlow.waiting_for_reminder)
async def process_reminder_text(message: types.Message, state: FSMContext):
    user_name = message.from_user.full_name
    chat_id = message.chat.id
    message_id = message.message_id
    user_text = message.text
    
    await message.answer("💡 Gemini מנתח את זמני התזכורת...")
    
    # הזרקת התאריך והשעה הנוכחיים כדי שג'מיני ידע לחשב מילים יחסיות כמו "מחר" או "בעוד יומיים"
    today_str = datetime.now().strftime("%Y-%m-%d")
    current_date_time_str = datetime.now().strftime("%H:%M")
    
    prompt = f"""
    היום התאריך הוא {today_str} והשעה הנוכחית היא {current_date_time_str}.
    חלץ את נושא התזכורת, התאריך המבוקש והשעה המבוקשת מתוך הודעת העובד הבאה.
    הודעה: "{user_text}"
    תרגם מילים כמו מחר, מחרתיים, או יום ראשון הבא לתאריכים מדויקים.
    החזר אך ורק פורמט JSON תקין.
    """
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ReminderItem,
            ),
        )
        extracted_data = json.loads(response.text)
    except Exception as e:
        print(f"AI Reminder Error: {e}")
        extracted_data = {"topic": user_text, "target_date": today_str, "target_time": "09:00"}

    # שמירה באקסל (כתיבה כפולה במכה אחת)
    success = save_reminder_to_sheets(chat_id, message_id, user_name, user_text, extracted_data)
    
    if success:
        topic = extracted_data.get("topic")
        t_date = extracted_data.get("target_date")
        t_time = extracted_data.get("target_time")
        
        # ⏰ --- שלב התזמון האוטומטי (APScheduler) ---
        try:
            # המרת מחרוזות התאריך והשעה של ג'מיני לאובייקט datetime של פייתון
            run_date = datetime.strptime(f"{t_date} {t_time}", "%Y-%m-%d %H:%M")
            
            # הוספת המשימה לטיימר של השרת
            scheduler.add_job(
                send_scheduled_reminder,
                'date',
                run_date=run_date,
                args=[message.bot, chat_id, topic]
            )
            
            await message.answer(
                f"✅ התזכורת נשמרה באקסל!\n"
                f"📌 *נושא:* {topic}\n"
                f"📅 *אזכיר לך בתאריך:* {t_date} *בשעה:* {t_time}",
                parse_mode="Markdown"
            )
        except Exception as sched_err:
            print(f"Scheduling error: {sched_err}")
            await message.answer("⚠️ הנתונים נשמרו באקסל, אך חלה שגיאה טכנית בהפעלת הנוטיפיקציה לעתיד.")
            
    else:
        await message.answer("❌ תקלה ברישום התזכורת באקסל.")
        
    await state.clear()