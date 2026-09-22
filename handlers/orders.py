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

# ייבוא המצבים ופונקציית הצינור המרכזית (אם העברת אותה לקובץ עזר)
from .states import OrderFlow

# מפתחות והגדרות
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "inventory_events")
CREDENTIALS_FILE = "credentials.json"

# אתחול הנתב והקליינט של ה-AI
orders_router = Router()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# המבנה של ה-AI חי פה כי הוא רלוונטי רק להזמנות
class InventoryItem(BaseModel):
    item_name: str = Field(description="שם הפריט או החלק החסר. המר אותו תמיד לצורת היחיד שלו בעברית תקינה! (למשל: 'צינורות' -> 'צינור', 'ברגים' -> 'בורג', 'בלוקים' -> 'בלוק')")
    standart: str = Field(description="התקן או הסטנדרט (אם לא צוין, רשום 'לא צוין')")
    size: int = Field(description="הגודל - מספר בלבד, המידות או הקוטר בצול (אם לא צוין, רשום 0)")
    quantity: int = Field(description="הכמות המבוקשת במטרים. מספר נקי בלבד ללא מילים (למשל: '50', אם לא צוין, רשום 1)")
    notes: str = Field(description="הערות נוספות או מידע רלוונטי אחר (אם לא צוין, רשום 'לא צוין')")


# פונקציית עזר מקומית לכתיבה (ניתן להעביר לקובץ utils.py בעתיד)
def save_order_to_sheets(chat_id, message_id, user_name, raw_message, extracted_data):
    try:
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. כתיבה ללשונית המרכזית
        main_sheet = spreadsheet.worksheet("main_events")
        main_sheet.append_row([current_date_time, chat_id, message_id, "new_order", user_name, raw_message])
        
        # 2. כתיבה ללשונית ההזמנות
        order_sheet = spreadsheet.worksheet("orders")
        order_sheet.append_row([
            current_date_time,
            chat_id,
            message_id,
            user_name, 
            extracted_data.get("item_name", "לא צוין"),
            extracted_data.get("standart", "לא צוין"),
            extracted_data.get("size", "לא צוין"),
            extracted_data.get("quantity", "לא צוין"), 
            extracted_data.get("notes", "לא צוין")
        ])
        return True
    except Exception as e:
        print(f"❌ Error writing order to sheets: {e}")
        return False

# --- פקודה ראשונית ---
@orders_router.message(Command("new_order"))
async def handle_new_order_command(message: types.Message, state: FSMContext):
    await message.answer("🛒 אנא הקלד את פרטי ההזמנה שלך בטקסט חופשי, אני התייחס לפרמטרים: שם הפריט	,תקן, גודל - קוטר, כמות (מטרים) (למשל: צריך 50מטרים של צינור מנירוסטה בעל תקן אא בקוטר צול אחד):")
    await state.set_state(OrderFlow.waiting_for_order)

# --- קבלת הטקסט וניתוח AI ---
@orders_router.message(OrderFlow.waiting_for_order)
async def process_order_text(message: types.Message, state: FSMContext):
    user_text = message.text
    await message.answer("💡 Gemini מנתח ומפרק את המשפט שלך...")
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash-lite', 
            contents=f"חלץ פרטי מלאי: {user_text}",
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=InventoryItem,
            ),
        )
        extracted_data = json.loads(response.text)
    except Exception as e:
        print(f"AI Error: {e}")
        extracted_data = {"item_name": user_text, "standart": "לא צוין", "size": "לא זוהה", "quantity": "0", "notes": "לא צוין"}

    await state.update_data(extracted_data=extracted_data, raw_message=user_text)

    confirmation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 אשר ושמור", callback_data="order:confirm"),
            InlineKeyboardButton(text="✏️ ערוך / הוסף מידע", callback_data="order:edit")
        ],
        [InlineKeyboardButton(text="❌ ביטול", callback_data="order:cancel")]
    ])

    summary_text = (
        f"📋 *אנא ודא את פרטי ההזמנה:*\n\n"
        f"📦 *פריט:* {extracted_data.get('item_name')}\n"
        f"📋 *תקן:* {extracted_data.get('standart')}\n"
        f"📏 *גודל:* {extracted_data.get('size')}\n"
        f"🔢 *כמות:* {extracted_data.get('quantity')}\n"
        f"📝 *הערות:* {extracted_data.get('notes')}\n\n"
        f"האם הנתונים נכונים?"
    )
    await message.answer(summary_text, parse_mode="Markdown", reply_markup=confirmation_keyboard)
    await state.set_state(OrderFlow.waiting_for_confirmation)

# --- תפיסת כפתורי האישור/עריכה/ביטול ---
@orders_router.callback_query(OrderFlow.waiting_for_confirmation)
async def handle_confirmation_buttons(callback_query: types.CallbackQuery, state: FSMContext):
    action = callback_query.data.split(":")[1]
    user_data = await state.get_data()
    extracted_data = user_data.get("extracted_data")
    raw_message = user_data.get("raw_message")
    user_name = callback_query.from_user.full_name
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id

    if action == "confirm":
        await callback_query.message.edit_text("⏳ שומר נתונים באקסל...")
        if save_order_to_sheets(chat_id, message_id, user_name, raw_message, extracted_data):
            await callback_query.message.edit_text("✅ ההזמנה אושרה ונשמרה בהצלחה בגוגל שיטס!")
        else:
            await callback_query.message.edit_text("❌ חלה שגיאה ברישום לאקסל.")
        await state.clear()

    elif action == "cancel":
        await callback_query.message.edit_text("❌ התהליך בוטלה והנתונים נמחקו.")
        await state.clear()

    elif action == "edit":
        await callback_query.message.edit_text("✏️ *הקלד את התיקון או המידע הנוסף שברצונך להוסיף:*", parse_mode="Markdown")
        await state.set_state(OrderFlow.waiting_for_edit)

# --- עיבוד התיקון/עריכה ---
@orders_router.message(OrderFlow.waiting_for_edit)
async def process_order_edit(message: types.Message, state: FSMContext):
    edit_text = message.text
    user_data = await state.get_data()
    old_data = user_data.get("extracted_data")
    
    await message.answer("🔄 Gemini מעדכן את הרשומה לפי התיקון שלך...")
    
    prompt = f"נתונים נוכחיים: {json.dumps(old_data, ensure_ascii=False)}\nבקשת תיקון: \"{edit_text}\"\nעדכן את ה-JSON בהתאם."
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=InventoryItem,
            ),
        )
        updated_data = json.loads(response.text)
    except Exception as e:
        print(f"AI Edit Error: {e}")
        updated_data = old_data

    await state.update_data(extracted_data=updated_data)

    confirmation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 אשר ושמור", callback_data="order:confirm"),
            InlineKeyboardButton(text="✏️ ערוך שוב", callback_data="order:edit")
        ],
        [InlineKeyboardButton(text="❌ ביטול", callback_data="order:cancel")]
    ])

    summary_text = (
        f"📝 *פרטי הדיווח המעודכנים:*\n\n"
        f"📦 *פריט:* {updated_data.get('item_name')}\n"
        f"📋 *תקן:* {updated_data.get('standart')}\n"
        f"📏 *גודל:* {updated_data.get('size')}\n"
        f"🔢 *כמות:* {updated_data.get('quantity')}\n"
        f"📝 *הערות:* {updated_data.get('notes')}\n\n"
        f"האם הנתונים מאושרים כעת?"
    )
    await message.answer(summary_text, parse_mode="Markdown", reply_markup=confirmation_keyboard)
    await state.set_state(OrderFlow.waiting_for_confirmation)