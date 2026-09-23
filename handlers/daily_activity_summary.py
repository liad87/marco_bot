import os
import json
from datetime import datetime
import gspread
from aiogram import Router, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, Field

from utils import upload_to_google_drive
from .states import DailySummaryFlow

GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "inventory_events")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CREDENTIALS_FILE = "credentials.json"

daily_summary_router = Router()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# --- א. הגדרת המבנים של ה-AI (Pydantic Schemas) ---

class BOQItem(BaseModel):
    boq_section: str = Field(description="סעיף כתב הכמויות הרלוונטי (למשל: '1.1.2')")
    item_description: str = Field(description="תיאור סעיף או פריט כתב הכמויות שבוצע היום")
    unit: str = Field(description="יחידת המידה (למשל: מ'ק, מ''ר, ק\"ג, יח')")
    quantity: float = Field(description="הכמות שבוצעה בפועל מהסעיף הזה (מספר בלבד)")

class DailyActivitySchema(BaseModel):
    execution_date: str = Field(description="תאריך ביצוע הפעילות בפורמט YYYY-MM-DD")
    bill_of_quantities_sections: list[str] = Field(description="רשימת הסעיפים המקוריים מכתב הכמויות הרלוונטיים להיום (למשל: ['1.1.2', '3.4'])")
    site_name: str = Field(description="שם האתר או המיקום")
    project_name: str = Field(description="שם הפרויקט")
    team_leader: str = Field(description="שם ראש הצוות/הממונה")
    work_description: str = Field(description="סיכום מילולי קצר של מה שבוצע היום בשטח")
    boq_items: list[BOQItem] = Field(description="רשימת שורות כתב הכמויות שבוצעו בפועל היום מתוך הטקסט או התמונה")

def save_master_detail_activity(chat_id, message_id, user_name, raw_message, extracted_data, drive_link):
    try:
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        exec_date = extracted_data.get("execution_date")
        boq_secs = ", ".join(extracted_data.get("bill_of_quantities_sections", []))

        # 1. כתיבה ללשונית המרכזית (main_events)
        main_sheet = spreadsheet.worksheet("main_events")
        main_sheet.append_row([current_date_time, "daily_activity_summary", user_name, raw_message, chat_id, message_id])
        
        # 2. כתיבה ללשונית הראשית (daily_activity_summary)
        summary_sheet = spreadsheet.worksheet("daily_activity_summary")
        summary_sheet.append_row([
            current_date_time, chat_id, message_id, user_name,
            exec_date,
            boq_secs,
            extracted_data.get("site_name"),
            extracted_data.get("project_name"),
            extracted_data.get("team_leader"),
            extracted_data.get("work_description"),
            drive_link
        ])
        
        # 3. כתיבה מרוכזת (Bulk Append) ללשונית הפירוט (daily_activity_details)
        details_sheet = spreadsheet.worksheet("daily_activity_details")
        rows_to_append = []
        for item in extracted_data.get("boq_items", []):
            rows_to_append.append([
                chat_id, 
                message_id,
                exec_date,
                item.get("boq_section"),
                item.get("item_description"), 
                item.get("unit"), 
                item.get("quantity")
            ])
            
        if rows_to_append:
            details_sheet.append_rows(rows_to_append) # כותב את כל השורות במכה אחת מהירה!
            
        return True
    except Exception as e:
        print(f"❌ Error in master-detail sheets logic: {e}")
        return False

# --- ג. ה-Handlers של טלגרם ---

@daily_summary_router.message(Command("daily_activity"))
async def handle_daily_command(message: types.Message, state: FSMContext):
    await message.answer("📋 *דיווח סיכום פעילות יומית*\nאנא שלח טקסט חופשי, או **תמונה/קובץ** של יומן העבודה/כתב הכמויות היומי:", parse_mode="Markdown")
    await state.set_state(DailySummaryFlow.waiting_for_file_or_text)

@daily_summary_router.message(DailySummaryFlow.waiting_for_file_or_text)
async def process_daily_input(message: types.Message, state: FSMContext):
    bot: Bot = message.bot
    user_name = message.from_user.full_name
    
    local_file_path = None
    drive_link = "לא הועלה קובץ"
    prompt_content = []
    
    # בדיקה האם המשתמש העלה תמונה/קובץ
    if message.photo or message.document:
        await message.answer("⏳ מוריד ומעלה את הקובץ ל-Google Drive...")
        
        # שליפת מזהה הקובץ הגבוה ביותר (התמונה באיכות הכי טובה)
        file_id = message.photo[-1].file_id if message.photo else message.document.file_id
        file_info = await bot.get_file(file_id)
        
        os.makedirs("temp", exist_ok=True)
        local_file_path = f"temp/{file_id}.jpg"
        await bot.download_file(file_info.file_path, local_file_path)
        
        # העלאה לדרייב
        drive_link = upload_to_google_drive(local_file_path, f"Daily_Summary_{user_name}_{file_id[:6]}")
        
        # הכנת הקובץ עבור מנוע ה-AI של Gemini
        with open(local_file_path, "rb") as f:
            file_bytes = f.read()
        
        prompt_content.append({"mime_type": "image/jpeg" if message.photo else "application/pdf", "data": file_bytes})
        user_text = message.caption or "מצורף קובץ כמויות יומי"
    else:
        user_text = message.text

    await message.answer("💡 Gemini מנתח את הנתונים ומחלץ את טבלת הכמויות...")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    main_prompt = f"היום התאריך הוא {today_str}. קרא את הטקסט/תמונה הבאה וחלץ את כל נתוני הפעילות וכתב הכמויות לפי המבנה המדויק הנדרש. טקסט מצורף: {user_text}"
    prompt_content.append(main_prompt)

    try:
        # פנייה למודל Gemini 3.5 Flash החדש והחזק שתומך במולטי-מודאליות (קבצים ותמונות)
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash', 
            contents=prompt_content,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DailyActivitySchema,
            ),
        )
        extracted_data = json.loads(response.text)
    except Exception as e:
        print(f"AI Multimodal Error: {e}")
        extracted_data = {"execution_date": today_str, "boq_items": []}

    # ניקוי הקובץ הזמני מהשרת
    if local_file_path and os.path.exists(local_file_path):
        os.remove(local_file_path)

    # שמירת נתוני הביניים בזיכרון ה-FSM
    await state.update_data(extracted_data=extracted_data, raw_message=user_text, drive_link=drive_link)

    confirmation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 אשר ושמור", callback_data="daily:confirm"),
            InlineKeyboardButton(text="❌ ביטול", callback_data="daily:cancel")
        ]
    ])

    summary_text = (
        f"📋 *סיכום הפעילות שחולץ:*\n\n"
        f"📅 *תאריך ביצוע:* {extracted_data.get('execution_date')}\n"
        f"🏗️ *אתר/פרויקט:* {extracted_data.get('site_name')} - {extracted_data.get('project_name')}\n"
        f"👷‍♂️ *מנהל:* {extracted_data.get('team_leader')} | *תיאור:* {extracted_data.get('work_description')}\n"
        f"🔗 *לינק לדרייב:* {drive_link[:30]}...\n\n"
        f"📊 *שורות כתב הכמויות שזוהו ({len(extracted_data.get('boq_items', []))} שורות):*\n"
    )
    for item in extracted_data.get('boq_items', [])[:5]: # מציג עד 5 שורות ראשונות בתצוגה המקדימה
        summary_text += f"• {item.get('item_description')}: {item.get('quantity')} {item.get('unit')}\n"

    await message.answer(summary_text, parse_mode="Markdown", reply_markup=confirmation_keyboard)
    await state.set_state(DailySummaryFlow.waiting_for_confirmation)

@daily_summary_router.callback_query(DailySummaryFlow.waiting_for_confirmation)
async def handle_daily_confirmation(callback_query: types.CallbackQuery, state: FSMContext):
    action = callback_query.data.split(":")
    user_data = await state.get_data()
    extracted_data = user_data.get("extracted_data")
    raw_message = user_data.get("raw_message")
    drive_link = user_data.get("drive_link")
    user_name = callback_query.from_user.full_name
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id

    if action == "confirm":
        await callback_query.message.edit_text("⏳ מפצל נתונים וכותב לשני הגיליונות במקביל...")
        success = save_master_detail_activity(chat_id, message_id, user_name, raw_message, extracted_data, drive_link)
        if success:
            await callback_query.message.edit_text("✅ סיכום הפעילות ופירוט הכמויות פוצלו ונשמרו בהצלחה!")
        else:
            await callback_query.message.edit_text("❌ חלה שגיאה טכנית. ודא שקיימים הטאבים daily_activity_summary ו-daily_activity_details.")
        await state.clear()
        
    elif action == "cancel":
        await callback_query.message.edit_text("❌ הפעולה בוטלה והנתונים נמחקו.")
        await state.clear()
