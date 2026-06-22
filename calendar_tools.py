import os
import os.path
import json
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from pymongo import MongoClient

SCOPES = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/tasks.readonly']

CALENDAR_ID = os.getenv('CALENDAR_ID', 'primary')
print(f"DEBUG: Using Calendar ID: {CALENDAR_ID}") 

# Connect to MongoDB
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["smart_scheduler"]
tokens_collection = db["tokens"]

def get_credentials(user_id):
    # Retrieve user token from MongoDB
    user_token = tokens_collection.find_one({"user_id": str(user_id)})
    if user_token and "token" in user_token:
        creds = Credentials.from_authorized_user_info(user_token["token"], SCOPES)
        if creds:
            if creds.valid:
                return creds
            # Refresh expired token and update database
            elif creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    tokens_collection.update_one(
                        {"user_id": str(user_id)},
                        {"$set": {"token": json.loads(creds.to_json())}}
                    )
                    return creds
                except Exception as e:
                    print(f"Error refreshing token for {user_id}: {e}")
    return None

def get_calendar_service(user_id):
    creds = get_credentials(user_id)
    if not creds:
        return None
    return build('calendar', 'v3', credentials=creds)

def list_events(user_id, calendar_ids=None):
    service = get_calendar_service(user_id)
    if not service:
        return None
        
    if not calendar_ids:
        calendar_ids = ['primary']
        
    now_dt = datetime.utcnow()
    now = now_dt.isoformat() + 'Z'
    
    # Fetch events for the next 21 days
    max_dt = now_dt + timedelta(days=21)
    time_max = max_dt.isoformat() + 'Z'
    
    all_events = []
    
    for cal_id in calendar_ids:
        try:
            events_result = service.events().list(
                calendarId=cal_id, 
                timeMin=now,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            items = events_result.get('items', [])
            
            for item in items:
                item['calendar_id'] = cal_id
                
            all_events.extend(items)
        except Exception as e:
            print(f"Error reading calendar {cal_id}: {e}")
            
    def get_start_time(event):
        return event['start'].get('dateTime', event['start'].get('date'))
        
    all_events.sort(key=get_start_time)
    
    return all_events

def create_event(user_id, summary, start_time, end_time, calendar_id='primary', location=None, disable_reminders=False):
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
    
    if location:
        event['location'] = location
        
    if disable_reminders:
        event['reminders'] = {'useDefault': False, 'overrides': []}
    
    return service.events().insert(calendarId=calendar_id, body=event).execute()

def is_overlap(new_start_iso, new_end_iso, existing_events):
    def parse_dt(iso_str):
        if len(iso_str) == 10:
            iso_str += "T00:00:00"
            
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    new_start = parse_dt(new_start_iso)
    new_end = parse_dt(new_end_iso)

    for e in existing_events:
        start_val = e['start'].get('dateTime') or e['start'].get('date')
        end_val = e['end'].get('dateTime') or e['end'].get('date')
        
        if not start_val or not end_val:
            continue 
            
        e_start = parse_dt(start_val)
        e_end = parse_dt(end_val)

        if new_start < e_end and new_end > e_start:
            return True, e['summary']
            
    return False, None

def list_tasks(user_id):
    # Fetch tasks using credentials from MongoDB
    creds = get_credentials(user_id)
        
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
    service = get_calendar_service(user_id)
    if not service:
        return None
    
    try:
        calendar_list = service.calendarList().list().execute()
        items = calendar_list.get('items', [])
        
        calendars = []
        for item in items:
            calendars.append({
                'id': item['id'],
                'summary': item.get('summary', 'יומן ללא שם')
            })
            
        return calendars
    except Exception as e:
        print(f"Error fetching calendars: {e}")
        return None        

def delete_event(user_id, calendar_id, event_id):
    try:
        creds = get_credentials(user_id) 
        service = build('calendar', 'v3', credentials=creds)
        
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True, "האירוע נמחק בהצלחה."
    except Exception as e:
        print(f"Error deleting event: {e}")
        return False, f"שגיאה במחיקת האירוע: {str(e)}"

def update_event_time(user_id, calendar_id, event_id, new_start_iso=None, new_end_iso=None, new_summary=None, new_location=None, disable_reminders=False):
    try:
        creds = get_credentials(user_id)
        service = build('calendar', 'v3', credentials=creds)
        
        # 1. Fetch existing event from Google Calendar
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # 2. Update provided fields
        if new_start_iso:
            event['start'] = {'dateTime': new_start_iso}
        if new_end_iso:
            event['end'] = {'dateTime': new_end_iso}
        if new_summary:
            event['summary'] = new_summary
            
        if new_location:
            event['location'] = new_location
            
        if disable_reminders:
            event['reminders'] = {'useDefault': False, 'overrides': []}
        
        # 3. Push updates back to Google API
        updated_event = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
        
        return True, updated_event.get('summary', 'אירוע ללא שם')
    except Exception as e:
        print(f"Error updating event: {e}")
        return False, str(e)