import os
import json
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 1. טעינת משתני סביבה - הכי חשוב שזה יהיה לפני כל import אחר!
load_dotenv()

import anthropic
from calendar_tools import create_event, list_events
from bidi.algorithm import get_display

# הגדרת הלקוח של קלוד
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# פונקציית בלם חירום - בודקת התנגשויות מתמטית
def is_overlap(new_start_iso, new_end_iso, existing_events):
    new_start = datetime.fromisoformat(new_start_iso.replace('Z', ''))
    new_end = datetime.fromisoformat(new_end_iso.replace('Z', ''))

    for e in existing_events:
        e_start = datetime.fromisoformat(e['start'].get('dateTime', '').replace('Z', ''))
        e_end = datetime.fromisoformat(e['end'].get('dateTime', '').replace('Z', ''))

        # לוגיקה: האם יש חפיפה?
        if new_start < e_end and new_end > e_start:
            return True, e['summary']
    return False, None

# --- שלב 1: שליפת אירועים (חובה לעשות את זה לפני הגדרת ה-Prompt!) ---
existing_events = list_events()

# הופכים את האירועים לטקסט שהבוט יכול להבין
if not existing_events:
    events_context = "היומן ריק."
else:
    events_context = "\n".join([f"- {e['summary']} ביום {e['start'].get('dateTime')}" for e in existing_events])

# --- שלב 2: הגדרת ה-Prompt עם הזרקת הלו"ז ---
system_prompt = f"""
אתה ה-Chief of Staff האישי של המשתמשת.
להלן רשימת האירועים הקיימים ביומן שלה, עליהם אתה חייב להתבסס:
{events_context}

הנחיות עבודה:
1. ניתוח דדליינים: כל משימה עם תאריך יעד היא אילוץ קשיח. אסור לתזמן פעילויות שמתנגשות.
2. אופטימיזציה: אם הלו"ז עמוס, אל תמציא זמן. תציע חלופות או תתריע על חוסר יכולת לבצע.
3. ייעוץ אקטיבי: אם אתה מזהה שדד-ליין מתקרב, תתריע על כך בייעוץ.
4. מבנה פלט JSON חובה:
{{
  "advice": "ניתוח קצר של מצב הלו"ז, דדליינים והמלצות.",
  "scheduled_events": [
    {{"title": "...", "date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM"}}
  ]
}}
"""

user_text = """
יש לי עבודה להגשה למחר בלינארית. אני רוצה להספיק השבוע עוד שני אימוני כוח, ואימון ספינינג. אני גם חייבת לדבר עם סבתא חצי שעה בערך
"""

print(get_display("מנתח את היומן ושולח הוראה לקלוד..."))

message = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1000,
    system=system_prompt,
    messages=[{"role": "user", "content": user_text}]
)

# 3. ניקוי וחילוץ ה-JSON
response_text = message.content[0].text
match = re.search(r'\{.*\}', response_text, re.DOTALL)

if match:
    json_str = match.group(0)
    try:
        data = json.loads(json_str)
        
        # 1. קריאת הייעוץ
        print(f"\n💡 ייעוץ אסטרטגי: {data.get('advice', 'אין ייעוץ')}\n")
        
        events_to_schedule = data.get('scheduled_events', [])
        
        if not events_to_schedule:
            print("הבוט לא הציע אירועים לקביעה.")
        else:
            # 2. הצגת האירועים המוצעים לאישור
            print("הבוט מציע לקבוע את האירועים הבאים:")
            for i, event in enumerate(events_to_schedule):
                print(f"{i+1}. {event['title']} | תאריך: {event['date']} | שעה: {event['start_time']}")

            # 3. "היד על ההדק" - אישור ידני
            user_choice = input("\nהאם לאשר את קביעת האירועים הללו? (y/n): ").lower()

            if user_choice == 'y':
                print("מתחיל בקביעת האירועים...")
                for event in events_to_schedule:
                    start_iso = f"{event['date']}T{event['start_time']}:00+03:00"
                    end_iso = f"{event['date']}T{event['end_time']}:00+03:00"

                    # בדיקת התנגשות (שכבת הגנה נוספת)
                    has_overlap, conflict_name = is_overlap(start_iso, end_iso, existing_events)
                    
                    if has_overlap:
                        print(f"⚠️ דילגתי על '{event['title']}' - מתנגש עם '{conflict_name}'")
                    else:
                        created = create_event(event['title'], start_iso, duration_hours=1)
                        print(f"✅ נקבע בהצלחה: {event['title']} ב-{event['date']} שעה {event['start_time']}")
            else:
                print("❌ האירועים לא נקבעו. השליטה נשארה אצלך!")
                
    except json.JSONDecodeError:
        print("שגיאה בפענוח ה-JSON.")