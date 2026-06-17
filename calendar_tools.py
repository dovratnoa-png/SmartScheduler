import os
import os.path
from datetime import datetime, timedelta, timezone
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
        
    if not calendar_ids:
        calendar_ids = ['primary']
        
    now = datetime.utcnow().isoformat() + 'Z'
    all_events = []
    
    for cal_id in calendar_ids:
        try:
            events_result = service.events().list(
                calendarId=cal_id, 
                timeMin=now,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            items = events_result.get('items', [])
            
            # הנה השינוי: לוקחים כל אירוע ומוסיפים לו שדה שמציין מאיזה יומן הוא הגיע
            for item in items:
                item['calendar_id'] = cal_id
                
            all_events.extend(items)
        except Exception as e:
            print(f"Error reading calendar {cal_id}: {e}")
            
    def get_start_time(event):
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
    # פונקציית עזר שמתקנת את אזורי הזמן בלי לשבור כלום
    def parse_dt(iso_str):
        # אם זה אירוע של יום שלם (רק תאריך כמו "2026-06-18"), נוסיף לו חצות כדי שפייתון יוכל להשוות
        if len(iso_str) == 10:
            iso_str += "T00:00:00"
            
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        
        # אם חסר אזור זמן, מגדירים אותו כ-UTC כדי למנוע את שגיאת ה-offset
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    new_start = parse_dt(new_start_iso)
    new_end = parse_dt(new_end_iso)

    for e in existing_events:
        # הלוגיקה שלך: לוקחים גם dateTime וגם date!
        start_val = e['start'].get('dateTime') or e['start'].get('date')
        end_val = e['end'].get('dateTime') or e['end'].get('date')
        
        if not start_val or not end_val:
            continue 
            
        e_start = parse_dt(start_val)
        e_end = parse_dt(end_val)

        if new_start < e_end and new_end > e_start:
            # הלוגיקה שלך: מחזירים את ה-summary!
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


def delete_event(user_id, calendar_id, event_id):
    """מוחק אירוע קיים מגוגל קלנדר"""
    try:
        creds = get_credentials(user_id) # משתמש בפונקציה הקיימת שלך לשליפת הטוקן
        service = build('calendar', 'v3', credentials=creds)
        
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True, "האירוע נמחק בהצלחה."
    except Exception as e:
        print(f"Error deleting event: {e}")
        return False, f"שגיאה במחיקת האירוע: {str(e)}"

def update_event_time(user_id, calendar_id, event_id, new_start_iso, new_end_iso):
    """מעדכן שעות של אירוע קיים (הזזת אירוע)"""
    try:
        creds = get_credentials(user_id)
        service = build('calendar', 'v3', credentials=creds)
        
        # 1. קודם שולפים את האירוע הקיים כדי לא לדרוס לו נתונים אחרים (כמו מיקום או משתתפים)
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # 2. מעדכנים רק את שעת ההתחלה והסיום
        event['start'] = {'dateTime': new_start_iso}
        event['end'] = {'dateTime': new_end_iso}
        
        # 3. דוחפים את העדכון חזרה לגוגל
        updated_event = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
        
        return True, updated_event.get('summary', 'אירוע ללא שם')
    except Exception as e:
        print(f"Error updating event: {e}")
        return False, str(e)