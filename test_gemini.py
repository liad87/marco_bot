import os
import json
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, Field

# 1. משיכת ה-API Key ממשתני הסביבה של המחשב שלך
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ שגיאה: לא נמצא GEMINI_API_KEY במערכת ההפעלה שלך!")
    exit()

# 2. הגדרת המבנה המעודכן ללא מחלקה (Department)
class InventoryItem(BaseModel):
    item: str = Field(description="שם הפריט או החלק החסר")
    size: str = Field(description="הגודל, המידות או הקוטר של הפriט (אם צוין, אחרת רשום לא צוין)")
    quantity: str = Field(description="הכמות המבוקשת - מספר בלבד)")

# אתחול הקליינט של גוגל
client = genai.Client(api_key=GEMINI_API_KEY)

print("🤖 סקריפט בדיקה ל-Gemini API מוכן!")
user_input = input("הקלד הודעת בדיקה (למשל: צריך 50 שקי מלט גדולים): ")

prompt = f"חלץ את פרטי המלאי מתוך הודעת העובד הבאה: {user_input}"

try:
    print("⏳ פונה ל-Gemini 3.5 Flash החדש...")
    response = client.models.generate_content(
        model='gemini-3.5-flash',  # ✨ עודכן למודל הנתמך והעדכני
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=InventoryItem,
        ),
    )
    
    # הדפסת התוצאה המפורקת
    print("\n🎉 תשובה מובנת שהתקבלה מגוגל:")
    parsed_json = json.loads(response.text)
    print(json.dumps(parsed_json, indent=4, ensure_ascii=False))

except Exception as e:
    print(f"❌ שגיאה בפנייה ל-API: {e}")