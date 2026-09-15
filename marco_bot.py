import os
import json
import asyncio
import gspread
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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

if __name__ == "__main__":
    print("הבוט המשולב באוויר ומאזין...")
    asyncio.run(dp.start_polling(bot))