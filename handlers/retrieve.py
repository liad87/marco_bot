import os
import json
from datetime import datetime, timedelta
import gspread
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, Field

# ייבוא המצבים
from .states import RetrieveFlow

GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "inventory_events")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CREDENTIALS_FILE = "credentials.json"

retrieve_router = Router()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# מודל ה-AI לפענוח פילטר החיפוש
class SearchFilters(BaseModel):
    # תאריך יצירת השורה (מתי פיזית כתבו באקסל)
    report_date: str = Field(description="התאריך שבו הרשומה נוצרה או דווחה בפורמט YYYY-MM-DD. חלץ כאן רק אם המשתמש אמר במפורש מילים כמו 'שדיווחתי אתמול' או 'שכתבתי בשבוע שעבר'. אחרת רשום 'הכל'")
    # תאריך היעד של הפעילות (מתי צריך לבצע/להזכיר)
    target_date: str = Field(description="תאריך היעד, הביצוע, או לתזכור של הפעילות בפורמט YYYY-MM-DD. חלץ כאן אם המשתמש שואל על תוכניות לעתיד, למשל 'מה התכנון שלי למחר' או 'אילו תזכורות יש לי ליום ראשון'. אחרת רשום 'הכל'")
    search_keyword: str = Field(description="מילת מפתח לחיפוש (למשל שם של פריט או משימה). אם אין, רשום 'הכל'")
    limit: int = Field(description="כמות הרשומות המקסימלית שהמשתמש ביקש (למשל 'תן לי את 3 האחרונים' -> 3). אם המשתמש ביקש את 'הכל' או לא ציין כמות, החזר תמיד 5 כברירת מחדל")

# --- 1. פקודה ראשונית והצגת תפריט הטאבים בעברית ---
@retrieve_router.message(Command("retrieve_data"))
async def cmd_retrieve_data(message: types.Message, state: FSMContext):
    # תת תפריט פנימי בעברית לבחירת טאב
    sub_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 לשונית הזמנות (Orders)", callback_data="tab:orders")],
        [InlineKeyboardButton(text="🔔 לשונית תזכורות (Reminders)", callback_data="tab:reminders")]
    ])
    
    await message.answer(
        "🔍 *מערכת שליפת נתונים מהגוגל שיט*\n"
        "מאיזה גיליון (טאב) תרצה שאשלוף עבורך מידע?", 
        reply_markup=sub_menu,
        parse_mode="Markdown"
    )
    await state.set_state(RetrieveFlow.waiting_for_tab_choice)

# --- 2. תפיסת בחירת הטאב ומעבר לשאלת ה-AI ---
@retrieve_router.callback_query(RetrieveFlow.waiting_for_tab_choice)
async def process_tab_choice(callback_query: types.CallbackQuery, state: FSMContext):
    chosen_tab = callback_query.data.split(":")[1]
    
    # שמירת הטאב הנבחר בזיכרון של ה-State
    await state.update_data(target_tab=chosen_tab)
    
    await callback_query.message.edit_text(
        f"📋 בחרת בלשונית: *{chosen_tab}*.\n"
        f"מה תרצה לשלוף? נסח את הבקשה שלך בטקסט חופשי.\n"
        f"💡 *לדוגמה:* 'מה התכנון שלי למחר?' או 'האם הזמנתי מלט השבוע?'",
        parse_mode="Markdown"
    )
    await state.set_state(RetrieveFlow.waiting_for_search_query)

# --- 3. קבלת השאלה, הפעלת Gemini ושליפה מהאקסל ---
@retrieve_router.message(RetrieveFlow.waiting_for_search_query)
async def process_search_query(message: types.Message, state: FSMContext):
    user_name = message.from_user.full_name
    user_text = message.text
    chat_id = message.chat.id
    message_id = message.message_id
    
    user_data = await state.get_data()
    target_tab = user_data.get("target_tab")
    
    await message.answer("⏳ Gemini מפענח את בקשת החיפוש והזמנים...")
    
    # חישוב זמנים נוכחיים להזרקה לפרומפט
    current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    prompt = f"""
    היום התאריך הוא {today_str} ומחר התאריך הוא {tomorrow_str}.
    תפקידך לפענח את בקשת החיפוש של העובד {user_name} עבור הגיליון {target_tab}.
    הבקשה: "{user_text}"
    
    הנחיות חשובות:
    1. תרגם מילים יחסיות כמו "מחר", "היום" או "אתמול" לתאריך המדויק בפורמט YYYY-MM-DD.
    2. בשדה search_keyword חלץ רק מוצר ספציפי או נושא ספציפי (למשל: 'מלט', 'צינור'), במוסף שים לב לסוג החומר (פלסטיק, נירוסטה וכד').
       המר את המילה תמיד לצורת היחיד שלה בעברית תקינה! (למשל אם העובד חיפש 'צינורות', חלץ 'צינור').
       אם המשתמש אמר מילים כלליות כמו 'הזמנות', 'תזכורות', 'מידע' או 'רשומות' - אל תשים אותן כקיוורד, רשום 'הכל'.
    
    החזר אך ורק פורמט JSON לפי המבנה שנדרש.
    """
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SearchFilters,
            ),
        )
        filters = json.loads(response.text)
        print(f"🤖 [Debug AI Filters] תאריך יעד: {filters.get('target_date')}, תאריך דיווח: {filters.get('report_date')}, מילת מפתח: {filters.get('search_keyword')}, הגבלה: {filters.get('limit')}")
        
        report_date = filters.get("report_date")
        target_date = filters.get("target_date")
        keyword = filters.get("search_keyword")
        
        # שלב א': רישום הפעולה עצמה בטאב המרכזי
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        main_sheet = spreadsheet.worksheet("main_events")
        main_sheet.append_row([current_date_time, chat_id, message_id, "retrieve_data", user_name, user_text])
        
        # שלב ב': שליפת נתונים וסינון מהטאב המבוקש
        sheet = spreadsheet.worksheet(target_tab)
        all_records = sheet.get_all_records()
        
        matching_rows = []

        #filter logic explained: 
        # 1. filter by user_name, 
        # 2. filter by report_date if specified
        # 3. filter by target_date if specified
        # 4. filter by keyword if specified
        
        for row in all_records:
            # 1. סינון קשיח לפי שם המשתמש הנוכחי + מנגנון פול-בק חכם לשם המשתמש:
            # בודק את כל האפשרויות, ולוקח את הראשונה שקיימת בשורה
            row_user = row.get("user_name") or row.get("שם המדווח") or row.get("עובד") or ""
            # אם אף אחד מהשמות לא נמצא, או שהוא לא שווה לשם של המשתמש בטלגרם - דלג
            if str(row_user).lower() != user_name.lower():
                continue
                
            # 2. סינון לפי תאריך במידה וג'מיני חילץ תאריך ספציפי
            if report_date != "הכל":
                # לוקח את עמודת היצירה (current_date_time) ומבודד רק את התאריך YYYY-MM-DD
                row_report_date = str(row.get("current_date_time", "")).split(" ")[0]
                if row_report_date != report_date:
                    continue

            # --- 3. סינון לפי תאריך יעד/ביצוע/לתזכור (אם המשתמש ביקש) ---
            if target_date != "הכל":
                # לוקח את עמודת היעד הספציפית של הטאב (למשל target_date בטאב reminders)
                row_target_date = str(row.get("target_date", "")).split(" ")[0]
                if row_target_date != target_date:
                    continue
            
            # 4. סינון חכם וגמיש לפי מילת מפתח
            if keyword != "הכל":
                row_content = str(row.values()).lower()
                keyword_words = keyword.lower().split()
                
               #לא יכניס את הרשומה לתוצאות אם לא כל המילות מפתח מופיעות ברשומה
                if not all(word in row_content for word in keyword_words):
                    continue
                    
            matching_rows.append(row)
        
        print(matching_rows)

        # --- 4. הגבלת כמות המידע והחזרת התשובה הסופית למשתמש ---
        if not matching_rows:
            await message.answer(f"🤷‍♂️ לא מצאתי רשומות מתאימות עבורך בלשונית {target_tab}.")
        else:
            # א. נהפוך את הרשימה כדי שהתוצאות החדשות ביותר באקסל יופיעו ראשונות למשתמש
            matching_rows.reverse()
            max_allowed = filters.get("limit", 5)
            truncated_rows = matching_rows[:max_allowed]
            has_more = len(matching_rows) > max_allowed

            response_reply = f"📋 *להלן המידע שנמצא עבורך בלשונית {target_tab} (מציג עד {max_allowed} רשומות אחרונות):*\n\n"
            
            # כעת רצים על הרשימה החתוכה (truncated_rows) במקום על matching_rows
            for idx, row in enumerate(truncated_rows, 1):
                response_reply += f"*{idx}.* "
                for key, val in row.items():
                    if key not in ["user_name", "chat_id", "message_id"]:
                        response_reply += f"• *{key}:* {val} "
                response_reply += "\n"
            
            # ה. בונוס לחוויית משתמש: אם היו יותר מ-5 תוצאות, נוסיף הערה קטנה בסוף
            if has_more:
                response_reply += f"\n⚠️ _נמצאו {len(matching_rows)} תוצאות בסך הכל. הבוט מציג מקסימום את 5 האחרונות כדי למנוע עומס._"
                
            await message.answer(response_reply, parse_mode="Markdown")
            
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"❌ Error in retrieve pipeline:\n{error_msg}")
        await message.answer("❌ חלה שגיאה טכנית בעיבוד הנתונים או בשליפה מהאקסל.")
        
    await state.clear()