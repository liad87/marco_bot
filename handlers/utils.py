import os
import gspread

CREDENTIALS_FILE = "credentials.json"
CLIENT_SECRETS_FILE = "oauth_client_id_desktop.json"
TOKEN_FILE = "token.json"

def upload_to_google_drive(local_file_path, file_name, folder_id=None):
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        
        scopes = ["https://www.googleapis.com/auth/drive"]
        
        creds = None
        
        # 2. בדיקה האם המשתמש כבר עבר אישור בעבר ויש לנו טוקן שמור
        if os.path.exists(TOKEN_FILE):
            # ✨ שים לב - כאן השימוש ב-google.oauth2.credentials הוא נכון! כי זה יוזר אנושי
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes)
            
        # 3. אם אין טוקן או שהוא פג תוקף - נפתח דפדפן לאישור אנושי חד-פעמי
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            else:
                # טעינת קובץ הדסקטופ ופתיחת זרם האימות בדפדפן
                flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes)
                creds = flow.run_local_server(port=0)
                
            # שמירת הטוקן שקיבלנו לקובץ מקומי כדי שלא נצטרך דפדפן בריצה הבאה
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())
                
        # 4. חיבור לשירות הדרייב האישי שלך
        drive_service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {'name': file_name}
        if folder_id:
            file_metadata['parents'] = [folder_id]
            
        media = MediaFileUpload(local_file_path, resumable=True)
        
        # 5. העלאת הקובץ ישירות לחשבון הדרייב שלך
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        # 6. יצירת הרשאת צפייה לקישור (כדי שמי שילחץ באקסל יוכל לראות)
        drive_service.permissions().create(
            fileId=uploaded_file.get('id'),
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        return uploaded_file.get('webViewLink')
        
    except Exception as e:
        import traceback
        print(f"❌ OAuth 2.0 Drive Upload Error:\n{traceback.format_exc()}")
        return "שגיאה בהעלאה לדרייב"