import os
import json
from datetime import datetime
import gspread
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, Field

# ייבוא המצבים
from .states import PlanningFlow

GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "inventory_events")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CREDENTIALS_FILE = "credentials.json"

planning_activity_router = Router()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 1. מודל הנתונים של ה-AI שהכנת (העברתי לפה כי הוא משמש רק את הקובץ הזה)
class PlanningData(BaseModel):
    bill_of_quantities_section: str = Field(description="שם הסעיף בחוברת הכמויות (אם לא צוין, רשום 'לא צוין')")
    planed_from: str = Field(description="תאריך התחלת העבודה או התכנון בפורמט YYYY-MM-DD. אם לא צוין, השאר ריק")
    planed_to: str = Field(description="תאריך סיום העבודה או התכנון בפורמט YYYY-MM-DD. אם לא צוין, השאר ריק")
    team_leader: str = Field(description="שם מנהל הצוות או הממונה הישיר. אם לא צוין, השאר ריק")
    site_name: str = Field(description="שם האתר או המיקום שבו מתבצעת העבודה. אם לא צוין, רשום 'לא צוין'")
    project_name: str = Field(description="שם הפרויקט או המיזם שבו מתבצעת העבודה. אם לא צוין, רשום 'לא צוין'")
    machine_name: str = Field(description="שם המכונה או הציוד שבו נעשה שימוש. אם לא צוין, רשום 'לא צוין'")
    system_name: str = Field(description="שם המערכת או התהליך שבו מתבצעת העבודה. אם לא צוין, רשום 'לא צוין'")
    number_of_workers: float = Field(description="מספר העובדים המעורבים בעבודה. אם לא צוין, רשום 0")
    workers_hours: float = Field(description="סך שעות העבודה של כל העובדים המעורבים. אם לא צוין, רשום 0")
    notes: str = Field(description="הערות נוספות או מידע רלוונטי אחר (אם לא צוין, רשום 'לא צוין')")

# 2. פונקציית הכתיבה הכפולה לגוגל שיטס (הטאב המרכזי + הטאב הספציפי)
def save_planning_to_sheets(chat_id, message_id, user_name, raw_message, extracted_data):
    try:
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # א) כתיבה ללשונית המרכזית (main_events)
        main_sheet = spreadsheet.worksheet("main_events")
        main_sheet.append_row([current_date_time, chat_id, message_id, "planning", user_name, raw_message])
        
        # ב) כתיבה ללשונית התכנון הייעודית (planning)
        plan_sheet = spreadsheet.worksheet("planning")
        plan_sheet.append_row([
            current_date_time, chat_id, message_id, user_name,
            extracted_data.get("bill_of_quantities_section"),
            extracted_data.get("planed_from"),
            extracted_data.get("planed_to"),
            extracted_data.get("team_leader"),
            extracted_data.get("site_name"),
            extracted_data.get("project_name"),
            extracted_data.get("machine_name"),
            extracted_data.get("system_name"),
            extracted_data.get("number_of_workers"),
            extracted_data.get("workers_hours"),
            extracted_data.get("notes")
        ])
        return True
    except Exception as e:
        print(f"❌ Error writing planning data to sheets: {e}")
        return False

# --- שלב א': פקודה ראשונית ---
@planning_activity_router.message(Command("report_planning"))
async def handle_planning_command(message: types.Message, state: FSMContext):
    await message.answer("📅 אנא הקלד את פרטי התכנון/העבודה בטקסט חופשי (יש להתייחס לשם ה: אתר, פרויקט , המכונה והמערכת ולתאריכי הפעילות. בנוסף שם ראש הצוות כמות האנשים או שעות האדם הנדרשים):")
    await state.set_state(PlanningFlow.waiting_for_plan)

# --- שלב ב': ניתוח ראשוני והצגת תפריט וידאו ---
@planning_activity_router.message(PlanningFlow.waiting_for_plan)
async def process_planning_text(message: types.Message, state: FSMContext):
    user_text = message.text
    await message.answer("💡 Gemini מנתח ומקטלג את פרטי התכנון...")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    prompt = f"היום התאריך הוא {today_str}. חלץ נתוני תכנון ועבודה מתוך הודעת העובד הבאה: {user_text}"
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash-lite', 
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PlanningData,
            ),
        )
        extracted_data = json.loads(response.text)
    except Exception as e:
        print(f"AI Planning Error: {e}")
        extracted_data = {"notes": f"שגיאת AI: {user_text}", "bill_of_quantities_section": "לא צוין"}

    # שמירת נתוני הביניים בזיכרון ה-FSM
    await state.update_data(extracted_data=extracted_data, raw_message=user_text)

    confirmation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 אשר ושמור", callback_data="plan:confirm"),
            InlineKeyboardButton(text="✏️ ערוך / הוסף מידע", callback_data="plan:edit")
        ],
        [InlineKeyboardButton(text="❌ ביטול", callback_data="plan:cancel")]
    ])

    summary_text = (
        f"📋 *אנא ודא את פרטי התכנון:*\n\n"
        f"🧱 *סעיף כמויות:* {extracted_data.get('bill_of_quantities_section')}\n"
        f"📅 *מתאריך:* {extracted_data.get('planed_from') or '-'} *עד:* {extracted_data.get('planed_to') or '-'}\n"
        f"👤 *מנהל צוות:* {extracted_data.get('team_leader') or '-'}\n"
        f"🏗️ *אתר:* {extracted_data.get('site_name')}\n"
        f"💼 *פרויקט:* {extracted_data.get('project_name')}\n"
        f"⚙️ *מכונה:* {extracted_data.get('machine_name')}\n"
        f"🖥️ *מערכת:* {extracted_data.get('system_name')}\n"
        f"👥 *עובדים:* {extracted_data.get('number_of_workers')} | *שעות:* {extracted_data.get('workers_hours')}\n"
        f"📝 *הערות:* {extracted_data.get('notes')}\n\n"
        f"האם הנתונים נכונים?"
    )
    await message.answer(summary_text, parse_mode="Markdown", reply_markup=confirmation_keyboard)
    await state.set_state(PlanningFlow.waiting_for_confirmation)

# --- שלב ג': תפיסת לחיצות הכפתורים (אישור/עריכה/ביטול) ---
@planning_activity_router.callback_query(PlanningFlow.waiting_for_confirmation)
async def handle_planning_confirmation(callback_query: types.CallbackQuery, state: FSMContext):
    action = callback_query.data.split(":")[1]
    user_data = await state.get_data()
    extracted_data = user_data.get("extracted_data")
    raw_message = user_data.get("raw_message")
    user_name = callback_query.from_user.full_name
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id

    if action == "confirm":
        await callback_query.message.edit_text("⏳ שומר תכנון באקסל...")
        success = save_planning_to_sheets(chat_id, message_id, user_name, raw_message, extracted_data)
        if success:
            await callback_query.message.edit_text("✅ התכנון נשמר בהצלחה בגוגל שיטס!")
        else:
            await callback_query.message.edit_text("❌ חלה שגיאה ברישום לאקסל. ודא שקיים טאב בשם planning.")
        await state.clear()

    elif action == "cancel":
        await callback_query.message.edit_text("❌ פעולת התכנון בוטלה והנתונים נמחקו.")
        await state.clear()

    elif action == "edit":
        await callback_query.message.edit_text("✏️ *הקלד את התיקון או המידע הנוסף שברצונך לעדכן:*", parse_mode="Markdown")
        await state.set_state(PlanningFlow.waiting_for_edit)

# --- שלב ד': עיבוד טקסט התיקון והצגה מחדש ---
@planning_activity_router.message(PlanningFlow.waiting_for_edit)
async def process_planning_edit(message: types.Message, state: FSMContext):
    edit_text = message.text
    user_data = await state.get_data()
    old_data = user_data.get("extracted_data")
    
    await message.answer("🔄 Gemini מעדכן את התכנון לפי התיקון שלך...")
    
    prompt = f"נתוני תכנון נוכחיים: {json.dumps(old_data, ensure_ascii=False)}\nבקשת תיקון: \"{edit_text}\"\nעדכן את ה-JSON בהתאם."
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PlanningData,
            ),
        )
        updated_data = json.loads(response.text)
    except Exception as e:
        print(f"AI Planning Edit Error: {e}")
        updated_data = old_data

    await state.update_data(extracted_data=updated_data)

    confirmation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 אשר ושמור", callback_data="plan:confirm"),
            InlineKeyboardButton(text="✏️ ערוך שוב", callback_data="plan:edit")
        ],
        [InlineKeyboardButton(text="❌ ביטול", callback_data="plan:cancel")]
    ])

    summary_text = (
        f"📝 *פרטי התכנון המעודכנים (לאחר עריכה):*\n\n"
        f"🧱 *סעיף כמויות:* {updated_data.get('bill_of_quantities_section')}\n"
        f"📅 *מתאריך:* {updated_data.get('planed_from') or '-'} *עד:* {updated_data.get('planed_to') or '-'}\n"
        f"👤 *מנהל צוות:* {updated_data.get('team_leader') or '-'}\n"
        f"🏗️ *אתר:* {updated_data.get('site_name')}\n"
        f"💼 *פרויקט:* {updated_data.get('project_name')}\n"
        f"⚙️ *מכונה:* {updated_data.get('machine_name')}\n"
        f"🖥️ *מערכת:* {updated_data.get('system_name')}\n"
        f"👥 *עובדים:* {updated_data.get('number_of_workers')} | *שעות:* {updated_data.get('workers_hours')}\n"
        f"📝 *הערות:* {updated_data.get('notes')}\n\n"
        f"האם הנתונים מאושרים כעת?"
    )
    await message.answer(summary_text, parse_mode="Markdown", reply_markup=confirmation_keyboard)
    await state.set_state(PlanningFlow.waiting_for_confirmation)