import os
import os.path
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/tasks.readonly']

CALENDAR_ID = os.getenv('CALENDAR_ID', 'primary')
print(f"DEBUG: Using Calendar ID: {CALENDAR_ID}") 
def get_calendar_service(user_id):
    token_file = f'token_{user_id}.json'
    creds = None
    
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        
    if not creds or not creds.valid:
        return None
        
    return build('calendar', 'v3', credentials=creds)

def list_events(user_id, calendar_ids=None):
    service = get_calendar_service(user_id)
    if not service:
        return None
        
    # אם לא קיבלנו רשימת יומנים ספציפית, נשתמש בראשי כברירת מחדל
    if not calendar_ids:
        calendar_ids = ['primary']
        
    now = datetime.utcnow().isoformat() + 'Z'
    all_events = []
    
    # עוברים על כל יומן שהמשתמש בחר ואוספים ממנו את האירועים
    for cal_id in calendar_ids:
        try:
            events_result = service.events().list(
                calendarId=cal_id, 
                timeMin=now,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            all_events.extend(events_result.get('items', []))
        except Exception as e:
            print(f"Error reading calendar {cal_id}: {e}")
            
    # בגלל שאספנו אירועים מכמה יומנים שונים, צריך למיין אותם מחדש לפי השעה
    def get_start_time(event):
        # מנסה למשוך שעה מדויקת, ואם זה אירוע של יום שלם - מושך רק תאריך
        return event['start'].get('dateTime', event['start'].get('date'))
        
    all_events.sort(key=get_start_time)
    
    return all_events

def create_event(user_id, summary, start_time, end_time, calendar_id='primary'):
    service = get_calendar_service(user_id)
    if not service:
        return "שגיאה בחיבור לגוגל" 
        
    start_dt = datetime.fromisoformat(start_time.replace('Z', ''))
    end_dt = datetime.fromisoformat(end_time.replace('Z', ''))
    start_str = start_dt.isoformat() if start_dt.tzinfo else start_dt.isoformat() + 'Z'
    end_str = end_dt.isoformat() if end_dt.tzinfo else end_dt.isoformat() + 'Z'
    
    event = {
        'summary': summary,
        'start': {'dateTime': start_str},
        'end': {'dateTime': end_str},
    }
    
    return service.events().insert(calendarId=calendar_id, body=event).execute()

def is_overlap(new_start_iso, new_end_iso, existing_events):
    new_start = datetime.fromisoformat(new_start_iso.replace('Z', ''))
    new_end = datetime.fromisoformat(new_end_iso.replace('Z', ''))

    for e in existing_events:
        start_val = e['start'].get('dateTime') or e['start'].get('date')
        end_val = e['end'].get('dateTime') or e['end'].get('date')
        
        if not start_val or not end_val:
            continue 
            
        e_start = datetime.fromisoformat(start_val.replace('Z', ''))
        e_end = datetime.fromisoformat(end_val.replace('Z', ''))

        if new_start < e_end and new_end > e_start:
            return True, e['summary']
    return False, None


def list_tasks(user_id):
    token_file = f'token_{user_id}.json'
    creds = None
    
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        
    if not creds or not creds.valid:
        print(f"⚠️ לא נמצאו הרשאות תקפות למשימות עבור משתמש {user_id}")
        return []
        
    tasks_service = build('tasks', 'v1', credentials=creds)
    try:
        tasks_result = tasks_service.tasklists().list().execute()
        tasklists = tasks_result.get('items', [])
        
        all_tasks = []
        for tasklist in tasklists:
            items = tasks_service.tasks().list(tasklist=tasklist['id']).execute().get('items', [])
            for task in items:
                if task.get('status') == 'completed': continue 
                
                due = task.get('due', None)
                if due:
                    all_tasks.append({
                        'summary': f"[דדליין] {task.get('title', 'משימה')}",
                        'start': {'date': due.split('T')[0]} 
                    })
        return all_tasks
    except Exception as e:
        print(f"❌ שגיאה בשליפת משימות למשתמש {user_id}: {e}")
        return []


def list_user_calendars(user_id):
    """
    שולף את כל היומנים של המשתמש מחשבון הגוגל שלו
    """
    service = get_calendar_service(user_id)
    if not service:
        return None
    
    try:
        # פנייה לגוגל לקבלת רשימת היומנים
        calendar_list = service.calendarList().list().execute()
        items = calendar_list.get('items', [])
        
        calendars = []
        for item in items:
            # אנחנו שומרים רק את ה-ID ואת השם התצוגה של היומן
            calendars.append({
                'id': item['id'],
                'summary': item.get('summary', 'יומן ללא שם')
            })
            
        return calendars
    except Exception as e:
        print(f"Error fetching calendars: {e}")
        return None        