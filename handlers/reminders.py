import os
import json
from datetime import datetime, timedelta
import gspread
from aiogram import Router, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv()
# ייבוא המצב של התזכורות וייבוא ה-scheduler שנגדיר בבוט הראשי
from .states import ReminderFlow
from apscheduler.schedulers.asyncio import AsyncIOScheduler

GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "inventory_events")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CREDENTIALS_FILE = "credentials.json"
REMINDER_STATUS_COLUMN = int(os.getenv("REMINDER_STATUS_COLUMN", 8) )

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
def _get_reminder_sheet():
    client = gspread.service_account(filename=CREDENTIALS_FILE)
    spreadsheet = client.open(GOOGLE_SHEET_NAME)
    return spreadsheet.worksheet("reminders")


def _set_reminder_status(row_number, status):
    reminder_sheet = _get_reminder_sheet()
    reminder_sheet.update_cell(row_number, REMINDER_STATUS_COLUMN, status)


async def send_scheduled_reminder(
    bot: Bot,
    chat_id: int,
    topic: str,
    row_number: int,
    was_delayed: bool = False,
):
    try:
        if was_delayed:
            reminder_text = (
                "⏰ *תזכורת אוטומטית שנשלחה באיחור*\n\n"
                "השרת לא היה פעיל בזמן שנקבע, ולכן התזכורת נשלחה עכשיו:\n"
                f"📌 {topic}"
            )
        else:
            reminder_text = f"⏰ *תזכורת אוטומטית!*\n\nהגיע הזמן לבצע:\n📌 {topic}"

        await bot.send_message(
            chat_id=chat_id,
            text=reminder_text,
            parse_mode="Markdown"
        )
        _set_reminder_status(row_number, "sent")
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
        
        # ב) כתיבה ללשונית התזכורות המורחבת
        reminder_sheet = spreadsheet.worksheet("reminders")
        reminder_sheet.append_row([
            current_date_time,
            chat_id,
            message_id,
            user_name, 
            extracted_data.get("topic"), 
            extracted_data.get("target_date"), 
            extracted_data.get("target_time"),
            "set"
        ])

        # Find the row by the unique chat ID and message ID pair.
        for row_number, row in reversed(list(enumerate(reminder_sheet.get_all_values(), start=1))):
            if len(row) >= 3 and row[1] == str(chat_id) and row[2] == str(message_id):
                return row_number
        return None
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
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    current_date_time_str = now.strftime("%H:%M")
    
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

    topic = extracted_data.get("topic")
    t_date = extracted_data.get("target_date")
    t_time = extracted_data.get("target_time")

    try:
        run_date = datetime.strptime(f"{t_date} {t_time}", "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        await message.answer("❌ פורמט התאריך או השעה אינו תקין.")
        await state.clear()
        return

    if run_date <= datetime.now():
        await message.answer("Can not set reminder on historical date")
        await state.clear()
        return

    # Save the reminder as set so a restart can restore it before delivery.
    reminder_row = save_reminder_to_sheets(
        chat_id,
        message_id,
        user_name,
        user_text,
        extracted_data,
    )

    if reminder_row:
        try:
            scheduler.add_job(
                send_scheduled_reminder,
                "date",
                run_date=run_date,
                id=f"reminder_{chat_id}_{message_id}",
                replace_existing=True,
                args=[message.bot, chat_id, topic, reminder_row],
            )

            await message.answer(
                f"✅ התזכורת נשמרה באקסל!\n"
                f"📌 *נושא:* {topic}\n"
                f"📅 *אזכיר לך בתאריך:* {t_date} *בשעה:* {t_time}",
                parse_mode="Markdown",
            )
        except Exception as sched_err:
            print(f"Scheduling error: {sched_err}")
            await message.answer("⚠️ הנתונים נשמרו באקסל, אך חלה שגיאה טכנית בהפעלת הנוטיפיקציה לעתיד.")
    else:
        await message.answer("❌ תקלה ברישום התזכורת באקסל.")
        
    await state.clear()


async def restore_open_reminders(bot: Bot):
    """Restore reminders that were still open when the process last stopped."""
    try:
        reminder_sheet = _get_reminder_sheet()
        rows = reminder_sheet.get_all_values()
        if not rows:
            return

        now = datetime.now()
        restored_count = 0

        for row_number, row in enumerate(rows[1:], start=2):
            if len(row) < REMINDER_STATUS_COLUMN or row[REMINDER_STATUS_COLUMN - 1].strip().lower() != "set":
                continue

            try:
                chat_id = int(row[1])
                topic = row[4]
                run_date = datetime.strptime(
                    f"{row[5]} {row[6]}",
                    "%Y-%m-%d %H:%M",
                )
                was_delayed = run_date <= now
                scheduled_run_date = now + timedelta(seconds=1) if was_delayed else run_date

                scheduler.add_job(
                    send_scheduled_reminder,
                    "date",
                    run_date=scheduled_run_date,
                    id=f"reminder_{chat_id}_{row_number}",
                    replace_existing=True,
                    args=[bot, chat_id, topic, row_number, was_delayed],
                )
                restored_count += 1
            except (ValueError, IndexError) as row_error:
                print(f"⚠️ Skipping invalid open reminder in row {row_number}: {row_error}")

        print(f"🔄 Restored {restored_count} open reminder(s) from Google Sheets")
    except Exception as e:
        print(f"❌ Error restoring reminders from Google Sheets: {e}")