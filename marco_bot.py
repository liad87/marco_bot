import os
import json
import asyncio
import gspread
from datetime import datetime,timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, Field

# מפתחות והגדרות
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEET_NAME = "inventory_events"
CREDENTIALS_FILE = "credentials.json"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 1. הגדרת המבנה לחילוץ הנתונים (הזמנת רכש)
class InventoryItem(BaseModel):
    item: str = Field(description="שם הפריט או החלק החסר")
    size: str = Field(description="הגודל או המידות")
    quantity: str = Field(description="הכמות המבוקשת")

# 2. הגדרת מצבי ה-FSM
class OrderFlow(StatesGroup):
    waiting_for_order = State()
    waiting_for_reminder = State() # הוספנו את מצב ההמתנה לתזכורת

# 3. פונקציית הצינור המרכזית (Pipeline)
def process_and_route_event(action_name, user_name, raw_message, extracted_ai_data=None):
    try:
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # שלב א': כתיבה קבועה לטאב המרכזי לתיעוד
        main_sheet = spreadsheet.worksheet("main_events")
        main_sheet.append_row([current_time, action_name, user_name, raw_message])
        
        # שלב ב': ניתוב לפי סוג הפעולה
        if action_name == "new_order" and extracted_ai_data:
            order_sheet = spreadsheet.worksheet("orders")
            # כתיבת הנתונים המפורקים מה-AI לעמודות ספציפיות!
            order_sheet.append_row([
                current_time, 
                user_name, 
                extracted_ai_data.get("item", "לא צוין"), 
                extracted_ai_data.get("quantity", "לא צוין"),
                extracted_ai_data.get("size", "לא צוין")
            ])
            
        elif action_name == "set_reminder":
            reminder_sheet = spreadsheet.worksheet("reminders")
            # עבור תזכורת, כרגע נרשום את הטקסט הגולמי
            reminder_sheet.append_row([current_time, user_name, raw_message])
            
        return True
    except Exception as e:
        print(f"❌ Error in routing data: {e}")
        return False

# --- פקודת הזמנה חדשה ---
@dp.message(Command("new_order"))
async def handle_new_order_command(message: types.Message, state: FSMContext):
    await message.answer("🛒 אנא הקלד את פרטי ההזמנה שלך (בטקסט חופשי):")
    await state.set_state(OrderFlow.waiting_for_order)

@dp.message(OrderFlow.waiting_for_order)
async def process_order_text(message: types.Message, state: FSMContext):
    user_name = message.from_user.full_name
    user_text = message.text
    
    await message.answer("💡 Gemini מנתח ומפרק את המשפט שלך...")
    
    # שילוב ה-AI: פנייה לגוגל חילוץ המידע למבנה JSON
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash',
            contents=f"חלץ פרטי מלאי: {user_text}",
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=InventoryItem,
            ),
        )
        extracted_data = json.loads(response.text)
    except Exception as ai_err:
        print(f"AI Error: {ai_err}")
        extracted_data = {"item": user_text, "size": "-", "quantity": "-"}

    # שליחה לפונקציית הניתוב עם הנתונים המפורקים מה-AI!
    success = process_and_route_event(
        action_name="new_order", 
        user_name=user_name, 
        raw_message=user_text,
        extracted_ai_data=extracted_data
    )
    
    if success:
        await message.answer(f"✅ ההזמנה של *{extracted_data.get('item')}* נרשמה בהצלחה בטאב orders!", parse_mode="Markdown")
    else:
        await message.answer("❌ תקלה ברישום ההזמנה באקסל.")
        
    await state.clear()

# --- פקודת תזכורת חדשה (התשובה לשאלה 5 שלך) ---
@dp.message(Command("set_reminder"))
async def handle_reminder_command(message: types.Message, state: FSMContext):
    await message.answer("🔔 על מה תרצה שאזכיר לך להתייעץ ומתי?")
    await state.set_state(OrderFlow.waiting_for_reminder)

@dp.message(OrderFlow.waiting_for_reminder)
async def process_reminder_text(message: types.Message, state: FSMContext):
    user_name = message.from_user.full_name
    user_text = message.text
    
    success = process_and_route_event(
        action_name="set_reminder", 
        user_name=user_name, 
        raw_message=user_text
    )
    
    if success:
        await message.answer("✅ התזכורת נשמרה בהצלחה בטאב reminders!")
    else:
        await message.answer("❌ תקלה ברישום התזכורת.")
        
    await state.clear()

# מודל AI מיוחד לפענוח שאלת החיפוש של המשתמש
class SearchFilters(BaseModel):
    target_date: str = Field(description="התאריך המבוקש בפורמט YYYY-MM-DD בלבד. אם המשתמש לא ציין זמן, רשום 'הכל'")
    search_keyword: str = Field(description="מילת מפתח לחיפוש (למשל שם של פרויקט, פריט או משימה). אם אין, רשום 'הכל'")

class RetrieveFlow(StatesGroup):
    waiting_for_tab_choice = State() # שלב א': בחירת הטאב
    waiting_for_search_query = State() # שלב ב': הזנת השאלה החופשית

# --- 1. הפעלת הפקודה הראשית והצגת תפריט הטאבים ---
@dp.message(Command("retrieve_data"))
async def cmd_retrieve_data(message: types.Message, state: FSMContext):
    # יצירת כפתורי תפריט לבחירת הטאב הרלוונטי
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛒 לשונית הזמנות (Orders)", callback_data="tab:orders"),
            InlineKeyboardButton(text="🔔 לשונית תזכורות (Reminders)", callback_data="tab:reminders")
        ]
    ])
    await message.answer("🔍 מאיזה גיליון תרצה לשלוף מידע?", reply_markup=keyboard)
    await state.set_state(RetrieveFlow.waiting_for_tab_choice)

# --- 2. תפיסת הבחירה של המשתמש בכפתור ה-Inline ---
@dp.callback_query(RetrieveFlow.waiting_for_tab_choice)
async def process_tab_choice(callback_query: types.CallbackQuery, state: FSMContext):
    # חילוץ שם הטאב מתוך ה-callback_data (למשל "orders")
    chosen_tab = callback_query.data.split(":")[1]
    
    # שמירת הטאב הנבחר בזיכרון הזמני של ה-State
    await state.update_data(target_tab=chosen_tab)
    
    await callback_query.message.edit_text(
        f"📋 בחרת בלשונית: *{chosen_tab}*.\n"
        f"מה תרצה לשלוף? נסח את הבקשה שלך בטקסט חופשי.\n"
        f"💡 *לדוגמה:* 'מה התכנון שלי למחר?' או 'האם הזמנתי מלט השבוע?'",
        parse_mode="Markdown"
    )
    await state.set_state(RetrieveFlow.waiting_for_search_query)

# --- 3. קבלת השאלה החופשית, הפעלת Gemini ושליפה מהאקסל ---
@dp.message(RetrieveFlow.waiting_for_search_query)
async def process_search_query(message: types.Message, state: FSMContext):
    user_name = message.from_user.full_name
    user_text = message.text
    
    # שליפת שם הטאב ששמרנו בשלב הקודם
    user_data = await state.get_data()
    target_tab = user_data.get("target_tab")
    
    await message.answer("⏳ Gemini מפענח את הזמנים ומילת המפתח...")
    
    # חישוב זמנים דינמי כדי להזריק ל-AI (כדי שידע מתי זה "היום" או "מחר")
    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    prompt = f"""
    היום התאריך הוא {today_str}, ומחר התאריך הוא {tomorrow_str}.
    תפקידך לפענח את בקשת החיפוש של העובד {user_name}.
    הבקשה: "{user_text}"
    תרגם מילים כמו "מחר" או "היום" לתאריך המדויק בפורמט YYYY-MM-DD.
    החזר אך ורק פורמט JSON לפי המבנה שנדרש.
    """
    
    try:
        # פנייה ל-Gemini לקבלת פילטרים נקיים (תאריך ומילת מפתח)
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SearchFilters,
            ),
        )
        filters = json.loads(response.text)
        target_date = filters.get("target_date")
        keyword = filters.get("search_keyword")
        
        await message.answer(f"🔎 מחפש באקסל שורות עבור המשתמש *{user_name}* בתאריך *{target_date}*...", parse_mode="Markdown")
        
        # התחברות לגוגל שיטס ושליפת הנתונים
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        sheet = spreadsheet.worksheet(target_tab)
        all_records = sheet.get_all_records()
        
        # סינון השורות באקסל לפי שם המשתמש, התאריך ומילת המפתח
        matching_rows = []
        for row in all_records:
            # 1. התאמת שם משתמש (חובה)
            if str(row.get("user_name", "")).lower() != user_name.lower():
                continue
                
            # 2. התאמת תאריך (אם המשתמש ביקש תאריך ספציפי כמו מחר)
            if target_date != "הכל":
                # חילוץ רק ה-date מתוך חותמת הזמן (YYYY-MM-DD)
                row_date = str(row.get("date", "")).split(" ")[0]
                if row_date != target_date:
                    continue
            
            # 3. התאמת מילת מפתח (אם צוינה)
            if keyword != "הכל":
                row_content = str(row.values()).lower()
                if keyword.lower() not in row_content:
                    continue
                    
            matching_rows.append(row)
            
        # --- 4. החזרת התשובה הסופית למשתמש ---
        if not matching_rows:
            await message.answer(f"🤷‍♂️ לא מצאתי רשומות מתאימות עבורך בלשונית {target_tab}.")
        else:
            response_reply = f"📋 *להלן המידע שנמצא עבורך בטאב {target_tab}:*\n\n"
            for idx, row in enumerate(matching_rows, 1):
                response_reply += f"*{idx}.* "
                # הדפסת כל הערכים שיש בשורה בצורה דינמית
                for key, val in row.items():
                    if key != "user_name": # אין טעם להדפיס את השם שלו בכל שורה
                        response_reply += f"• *{key}:* {val} "
                response_reply += "\n"
                
            await message.answer(response_reply, parse_mode="Markdown")
            
    except Exception as e:
        print(f"❌ Error in retrieve pipeline: {e}")
        await message.answer("❌ חלה שגיאה בעיבוד הבקשה או בשליפת הנתונים.")
        
    await state.clear()

if __name__ == "__main__":
    print("הבוט המשולב באוויר ומאזין...")
    asyncio.run(dp.start_polling(bot))