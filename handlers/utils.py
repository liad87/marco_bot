import os
import gspread

CREDENTIALS_FILE = "credentials.json"

def upload_to_google_drive(local_file_path, file_name, folder_id=None):
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.oauth2.service_account import Credentials
        
        # ✨ מערך Scopes מורחב ומלא הכולל גם את ה-metadata המדויק
        scopes = ["https://www.googleapis.com/auth/drive.file"]
        
        # טעינה ישירה של חשבון השירות
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        
        # חיבור רשמי - ה-build ינהל את ה-token בעצמו
        drive_service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {'name': file_name}
        if folder_id:
            file_metadata['parents'] = [folder_id]
            
        media = MediaFileUpload(local_file_path, resumable=True)
        
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            supportsAllDrives=True,
            fields='id, webViewLink'
        ).execute()
        
        drive_service.permissions().create(
            fileId=uploaded_file.get('id'),
            body={'type': 'anyone', 'role': 'reader'},
            supportsAllDrives=True
        ).execute()
        
        return uploaded_file.get('webViewLink')
        
    except Exception as e:
        import traceback
        print(f"❌ Drive Global Upload Error:\n{traceback.format_exc()}")
        return "שגיאה בהעלאה לדרייב"