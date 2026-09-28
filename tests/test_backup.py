import asyncio
import os
import sys

# טעינת משתני הסביבה (ודא שהם קיימים בטרמינל שלך)
#os.environ["GOOGLE_SHEET_NAME"] = "inventory_events"

#add current + parrent path for importing from handlers.backup
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

# ייבוא הפונקציה הכלול בקובץ שיצרת
from handlers.backup import run_daily_backup

async def test_main():
    print("🧪 מתחיל הרצת בדיקה ידנית למנגנון הגיבוי...")
    
    # הפעלה ישירה של הפונקציה באופן אסינכרוני
    await run_daily_backup()
    
    print("🧪 בדיקת הגיבוי הסתיימה. בדוק את תיקיית ה-Drive שלך!")

if __name__ == "__main__":
    # הרצת הבדיקה באמצעות לולאת האירועים של asyncio
    asyncio.run(test_main())
