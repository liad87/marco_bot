import os
import gspread

CREDENTIALS_FILE = "credentials.json"

def upload_to_google_drive(local_file_path, file_name, folder_id=None):
    """מעלה את הקובץ ל-Google Drive (תומך בתיקייה ספציפית) ומחזיר קישור שיתופי ציבורי"""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        
        # שימוש ב-Credentials הקיימים של ה-Service Account
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        creds = client.auth
        
        drive_service = build('drive', 'v3', credentials=creds)
        
        # הגדרת מטא-דאטה (כולל שיוך לתיקייה אם הוגדר folder_id)
        file_metadata = {'name': file_name}
        if folder_id:
            file_metadata['parents'] = [folder_id]
            
        media = MediaFileUpload(local_file_path, resumable=True)
        
        # העלאת הקובץ
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        # פתיחת הרשאות קריאה ללינק (לכל מי שיש לו את הקישור)
        drive_service.permissions().create(
            fileId=uploaded_file.get('id'),
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        return uploaded_file.get('webViewLink')
    except Exception as e:
        print(f"❌ Drive Global Upload Error: {e}")
        return "שגיאה בהעלאה לדרייב"