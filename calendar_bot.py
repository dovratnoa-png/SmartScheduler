import os.path
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ההרשאות שאנחנו צריכות (קריאה וכתיבה ליומן)
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    creds = None
    # הקובץ token.json שומר את האישור שלך כדי שלא תצטרכי להתחבר בכל פעם מחדש
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # אם אין אישור, נריץ את תהליך ההתחברות מול ה-credentials.json
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # נשמור את האישור לקובץ כדי לא להציק לך שוב
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

# פונקציה פשוטה שמושכת את האירועים מהשבוע הקרוב
def list_events():
    service = get_calendar_service()
    now = datetime.datetime.utcnow().isoformat() + 'Z' # זמן נוכחי
    print("שולפת אירועים מהשבוע הקרוב מהיומן...")
    
    # שליפת 10 האירועים הבאים
    events_result = service.events().list(calendarId='primary', timeMin=now,
                                        maxResults=10, singleEvents=True,
                                        orderBy='startTime').execute()
    events = events_result.get('items', [])

    if not events:
        print('לא נמצאו אירועים קרובים.')
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(f"{start} - {event['summary']}")

def create_event(summary, start_time, duration_hours=1):
    service = get_calendar_service()
    
    # חישוב זמן סיום (הוספת שעות לזמן התחלה)
    start_dt = datetime.datetime.fromisoformat(start_time.replace('Z', ''))
    end_dt = start_dt + datetime.timedelta(hours=duration_hours)
    
    event = {
        'summary': summary,
        'start': {
            'dateTime': start_dt.isoformat() + 'Z',
        },
        'end': {
            'dateTime': end_dt.isoformat() + 'Z',
        },
    }
    
    event = service.events().insert(calendarId='primary', body=event).execute()
    print(f'האירוע נוצר בהצלחה: {event.get("htmlLink")}')


if __name__ == '__main__':
    list_events()