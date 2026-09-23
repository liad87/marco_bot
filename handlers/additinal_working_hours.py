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
from .states import AdditionalHoursFlow

GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "inventory_events")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CREDENTIALS_FILE = "credentials.json"

additional_hours_router = Router()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 1. מודל הנתונים של ה-AI לחילוץ פרטי העבודה הנוספת
class AdditionalHoursData(BaseModel):
    site_name: str = Field(description="שם האתר או המיקום שבו בוצעה העבודה. אם לא צוין, רשום 'לא צוין'")
    work_description: str = Field(description="תיאור העבודה החריגה או הנוספת שבוצעה בפועל")
    requested_by: str = Field(description="שם האדם או הלקוח שביקש/הזמין את העבודה הנוספת. אם לא צוין, רשום 'לא צוין'")
    team_leader: str = Field(description="שם ראש הצוות או מנהל העבודה בשטח. אם לא צוין, רשום 'לא צוין'")
    total_man_hours: float = Field(description="סה''כ שעות אדם שהושקעו בעבודה זו (מספר בלבד). אם לא צוין, רשום 0")
    execution_date: str = Field(description="תאריך ביצוע העבודה בפועל בפורמט YYYY-MM-DD. אם מדובר על היום, חלץ את התאריך הנוכחי. אם לא צוין, השאר ריק")
    notes: str = Field(description="הערות נוספות או מידע רלוונטי אחר (אם לא צוין, רשום 'לא צוין')")

# 2. פונקציית הכתיבה הכפולה (main_events + additional_working_hours)
def save_additional_hours_to_sheets(chat_id, message_id, user_name, raw_message, extracted_data):
    try:
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # א) כתיבה ללשונית המרכזית (main_events)
        main_sheet = spreadsheet.worksheet("main_events")
        main_sheet.append_row([current_date_time, "additional_working_hours", user_name, raw_message, chat_id, message_id])
        
        # ב) כתיבה ללשונית הייעודית (additional_working_hours)
        hours_sheet = spreadsheet.worksheet("additional_working_hours")
        hours_sheet.append_row([
            current_date_time, 
            chat_id, 
            message_id, 
            user_name,
            extracted_data.get("site_name"),
            extracted_data.get("work_description"),
            extracted_data.get("requested_by"),
            extracted_data.get("team_leader"),
            extracted_data.get("total_man_hours"),
            extracted_data.get("execution_date"),
            extracted_data.get("notes")
        ])
        return True
    except Exception as e:
        print(f"❌ Error writing additional hours data to sheets: {e}")
        return False

# --- שלב א': פקודה ראשונית ---
@additional_hours_router.message(Command("additional_working_hours"))
async def handle_additional_hours_command(message: types.Message, state: FSMContext):
    await message.answer("🛠️ אנא הקלד את פרטי העבודה הנוספת (חריגה) בטקסט חופשי\n(למשל: עבודה נוספת באתר חיפה לפי בקשת יוסי, תיקון צנרת עוקפת, בוצע אתמול על ידי משה, סה\"כ 6 שעות אדם):")
    await state.set_state(AdditionalHoursFlow.waiting_for_hours)

# --- שלב ב': ניתוח ראשוני והצגת תפריט וידוא ---
@additional_hours_router.message(AdditionalHoursFlow.waiting_for_hours)
async def process_additional_hours_text(message: types.Message, state: FSMContext):
    user_text = message.text
    await message.answer("💡 Gemini מנתח ומקטלג את פרטי העבודה החריגה...")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    prompt = f"היום התאריך הוא {today_str}. חלץ נתוני עבודה חריגה ונוספת מתוך הודעת העובד הבאה: {user_text}"
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash-lite', 
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AdditionalHoursData,
            ),
        )
        extracted_data = json.loads(response.text)
    except Exception as e:
        print(f"AI Additional Hours Error: {e}")
        extracted_data = {"work_description": user_text, "site_name": "לא צוין", "total_man_hours": 0}

    # שמירת נתוני הביניים בזיכרון ה-FSM
    await state.update_data(extracted_data=extracted_data, raw_message=user_text)

    confirmation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 אשר ושמור", callback_data="add_hrs:confirm"),
            InlineKeyboardButton(text="✏️ ערוך / הוסף מידע", callback_data="add_hrs:edit")
        ],
        [InlineKeyboardButton(text="❌ ביטול", callback_data="add_hrs:cancel")]
    ])

    summary_text = (
        f"📋 *אנא ודא את פרטי העבודה הנוספת:*\n\n"
        f"🏗️ *אתר:* {extracted_data.get('site_name')}\n"
        f"📝 *תיאור העבודה:* {extracted_data.get('work_description')}\n"
        f"👤 *מבקש העבודה:* {extracted_data.get('requested_by')}\n"
        f"👨‍קבוצה *ראש הצוות:* {extracted_data.get('team_leader')}\n"
        f"⏱️ *סה\"כ שעות אדם:* {extracted_data.get('total_man_hours')}\n"
        f"📅 *תאריך ביצוע:* {extracted_data.get('execution_date') or '-'}\n"
        f"ℹ️ *הערות:* {extracted_data.get('notes')}\n\n"
        f"האם הנתונים נכונים?"
    )
    await message.answer(summary_text, parse_mode="Markdown", reply_markup=confirmation_keyboard)
    await state.set_state(AdditionalHoursFlow.waiting_for_confirmation)

# --- שלב ג': תפיסת לחיצות הכפתורים (אישור/עריכה/ביטול) ---
@additional_hours_router.callback_query(AdditionalHoursFlow.waiting_for_confirmation)
async def handle_hours_confirmation(callback_query: types.CallbackQuery, state: FSMContext):
    action = callback_query.data.split(":")[1]
    user_data = await state.get_data()
    extracted_data = user_data.get("extracted_data")
    raw_message = user_data.get("raw_message")
    user_name = callback_query.from_user.full_name
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id

    if action == "confirm":
        await callback_query.message.edit_text("⏳ שומר שעות חריגות באקסל...")
        success = save_additional_hours_to_sheets(chat_id, message_id, user_name, raw_message, extracted_data)
        if success:
            await callback_query.message.edit_text("✅ הדיווח נשמר בהצלחה בגוגל שיטס!")
        else:
            await callback_query.message.edit_text("❌ חלה שגיאה ברישום לאקסל. ודא שקיים טאב בשם additional_working_hours.")
        await state.clear()

    elif action == "cancel":
        await callback_query.message.edit_text("❌ פעולת הדיווח בוטלה והנתונים נמחקו.")
        await state.clear()

    elif action == "edit":
        await callback_query.message.edit_text("✏️ *הקלד את התיקון או המידע הנוסף שברצונך לעדכן:*", parse_mode="Markdown")
        await state.set_state(AdditionalHoursFlow.waiting_for_edit)

# --- שלב ד': עיבוד טקסט התיקון והצגה מחדש ---
@additional_hours_router.message(AdditionalHoursFlow.waiting_for_edit)
async def process_hours_edit(message: types.Message, state: FSMContext):
    edit_text = message.text
    user_data = await state.get_data()
    old_data = user_data.get("extracted_data")
    
    await message.answer("🔄 Gemini מעדכן את הנתונים לפי התיקון שלך...")
    
    prompt = f"נתוני שעות נוכחיים: {json.dumps(old_data, ensure_ascii=False)}\nבקשת תיקון: \"{edit_text}\"\nעדכן את ה-JSON בהתאם."
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AdditionalHoursData,
            ),
        )
        updated_data = json.loads(response.text)
    except Exception as e:
        print(f"AI Additional Hours Edit Error: {e}")
        updated_data = old_data

    await state.update_data(extracted_data=updated_data)

    confirmation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 אשר ושמור", callback_data="add_hrs:confirm"),
            InlineKeyboardButton(text="✏️ ערוך שוב", callback_data="add_hrs:edit")
        ],
        [InlineKeyboardButton(text="❌ ביטול", callback_data="add_hrs:cancel")]
    ])

    summary_text = (
        f"📝 *פרטי הדיווח המעודכנים (לאחר עריכה):*\n\n"
        f"🏗️ *אתר:* {updated_data.get('site_name')}\n"
        f"📝 *תיאור העבודה:* {updated_data.get('work_description')}\n"
        f"👤 *מבקש העבודה:* {updated_data.get('requested_by')}\n"
        f"👨‍קבוצה *ראש הצוות:* {updated_data.get('team_leader')}\n"
        f"⏱️ *סה\"כ שעות אדם:* {updated_data.get('total_man_hours')}\n"
        f"📅 *תאריך ביצוע:* {updated_data.get('execution_date') or '-'}\n"
        f"ℹ️ *הערות:* {updated_data.get('notes')}\n\n"
        f"האם הנתונים מאושרים כעת?"
    )
    await message.answer(summary_text, parse_mode="Markdown", reply_markup=confirmation_keyboard)
    await state.set_state(AdditionalHoursFlow.waiting_for_confirmation)
