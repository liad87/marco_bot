print("Starting backup")
import os
import json
from datetime import datetime
import gspread
from dotenv import load_dotenv

load_dotenv()
# שימוש באותם קבצי הגדרות של הפרויקט שלך
#CLIENT_SECRETS_FILE = "oauth_client_id_desktop.json"
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"

# שם קובץ המקור ו-ID של תיקיית הגיבויים שלך
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "inventory_events")
BACKUP_FOLDER_ID = os.getenv("BACKUP_FOLDER_ID")

async def run_daily_backup():
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        
        # 1. טעינת אישור ה-OAuth הקיים של הדרייב האישי שלך
        scopes = ["https://www.googleapis.com/auth/drive"]
        if not os.path.exists(TOKEN_FILE):
            print("❌ שגיאת גיבוי: לא נמצא קובץ token.json פעיל")
            return
            
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes)
        drive_service = build('drive', 'v3', credentials=creds)
        print(GOOGLE_SHEET_NAME)

        # 2. חיפוש ומציאת ה-ID של קובץ המקור (inventory events) באקסל
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        source_file_id = spreadsheet.id

        print(source_file_id)

        # 3. יצירת השם המבוקש בפורמט ie_d_m_yy (ללא אפסים מובילים, שנה ב-2 ספרות)
        now = datetime.now()
        # %y נותן שנה ב-2 ספרות, הפיכת היום והחודש ל-int מורידה אפסים מובילים
        backup_name = f"ie_{int(now.day)}_{int(now.month)}_{now.strftime('%y')}"
        
        # 4. ביצוע השכפול (Copy) ישירות בתוך הדרייב לתוך תיקיית הגיבויים
        copied_file_metadata = {
            'name': backup_name,
            'parents': [BACKUP_FOLDER_ID]
        }
        
        print(f"⏳ מתחיל גיבוי אוטומטי לקובץ האקסל. שם קובץ מתוכנן: {backup_name}...")
        
        drive_service.files().copy(
            fileId=source_file_id,
            body=copied_file_metadata
        ).execute()
        
        print(f"✅ הגיבוי האוטומטי {backup_name} הסתיים בהצלחה!")
        
    except Exception as e:
        import traceback
        print(f"❌ שגיאה בהרצת הגיבוי האוטומטי:\n{traceback.format_exc()}")