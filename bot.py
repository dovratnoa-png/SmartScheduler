import os
import json
import re
from datetime import datetime, timedelta, timezone
from anthropic import AsyncAnthropic  
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from calendar_tools import list_user_calendars, create_event, list_events, is_overlap, list_tasks, delete_event, update_event_time

load_dotenv() 
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# מעבר לקליינט הא-סינכרוני כדי לאפשר למספר משתמשים לדבר במקביל
client = AsyncAnthropic(api_key=CLAUDE_API_KEY)

pending_schedules = {}
chat_histories = {} 

# === פונקציית עזר לבניית מקלדת היומנים ===
def build_calendar_keyboard(calendars, selected_ids):
    keyboard = []
    # אנחנו משתמשים ב-enumerate כדי לקבל מספר סידורי (i) לכל יומן
    for i, cal in enumerate(calendars):
        text = f"✅ {cal['summary']}" if cal['id'] in selected_ids else cal['summary']
        keyboard.append([InlineKeyboardButton(text, callback_data=f"cal_{i}")])
        
    keyboard.append([InlineKeyboardButton("🏁 סיימתי לבחור", callback_data="finish_selection")])
    return InlineKeyboardMarkup(keyboard)

# === פרומפט המערכת של קלוד ===
def get_system_prompt(events_context, calendars_text):
    # 1. הגדרת שעון ישראל כדי שהשרת של Render לא יתבלבל בלילות
    israel_tz = timezone(timedelta(hours=3))
    now = datetime.now(israel_tz)
    
    days = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    
    # 2. בניית "שליף תאריכים" חכם לקלוד - כדי שלא יצטרך לחשב תאריכים לבד!
    upcoming_dates = []
    for i in range(7):
        curr_date = now + timedelta(days=i)
        day_name = days[curr_date.weekday()]
        date_for_json = curr_date.strftime('%Y-%m-%d') # זה מה שחשוב ל-JSON!
        date_for_display = curr_date.strftime('%d/%m/%Y')
        
        if i == 0:
            upcoming_dates.append(f"- היום: יום {day_name} ({date_for_json})")
        elif i == 1:
            upcoming_dates.append(f"- מחר: יום {day_name} ({date_for_json})")
        else:
            upcoming_dates.append(f"- יום {day_name} ({date_for_json})")
            
    dates_cheat_sheet = "\n".join(upcoming_dates)
    
    today_str = (
        f"השעה הנוכחית היא: {now.strftime('%H:%M')}.\n\n"
        f"=== מפתח תאריכים לשבוע הקרוב (חובה להשתמש בתאריכים אלו ב-JSON!) ===\n"
        f"{dates_cheat_sheet}"
    )

    return f"""
    IMPORTANT FORMATTING RULES:
    You are interacting with a Telegram bot configured to parse HTML. You MUST format all your responses using ONLY Telegram-supported HTML tags (<b>, <i>, <u>).
    NEVER use Markdown formatting (do not use * or ** or _ for emphasis). 

    אתה עוזר אישי (Chief of Staff) חכם ויעיל. דבר תמיד בעברית טבעית, זורמת, קלילה וישראלית בגובה העיניים. אל תשתמש בשפה מליצית, רובוטית או בתרגום מכונה. תהיה פרקטי, קצר, נעים, ודבר ישירות למשתמש/ת. כשהמשתמש/ת מבקש/ת משהו, תענה בטבעיות כמו 'מעולה, בוא/י נסדר את זה' או 'קבעתי'.
    
    ===הלו״ז הקיים===
    {events_context}

    {today_str}
    
    {calendars_text}
    


    ===זמן ולוח שנה ישראלי===
    שים לב היטב להגדרת השבועות בישראל. 
    - ״השבוע״ יסתיים ביום שבת הקרוב.
    - יום ראשון הקרוב הוא כבר בשבוע הבא. כשמדברים על השבוע הנוכחי, יום ראשון הקרוב לא נחשב בשבוע הנוכחי
    - בשעות הלילה 00:00-06:00 ישנים! לא להציע דברים כמו לימודים או אימונים לשעות האלה. רק אם המשתמש/ת מבקש/ת ממך ישירות לקבוע שם אירוע.
    - שים לב להבדל בין אירועים לדדליינים: אירועים חוסמים זמן בלו"ז. דדליינים (משימות) הם רק נקודות ציון - הם לא תופסים זמן אמיתי ביום ואפשר לקבוע אירועים
    

    ===חוקי ברזל לעבודה===
    1. שים לב לשעה הנוכחית. לעולם אל תציע לשבץ אירועים היום בשעות שכבר עברו!
    2. תקציר יומי ודדליינים: חובה עליך להציג משפט תקציר על רמת העומס ולהזכיר דדליינים קרובים.
    3. ניהול שיחה: נהל דו-שיח קצר וטבעי וקבל אישור לפני קביעת עובדות.
    4. עברית: כתוב בעברית ישראלית, קלילה וטבעית, השתמש בלוכסנים (זכר/נקבה) היכן שצריך או בשפה ניטרלית. 
    5. חוק ה-JSON (קריטי!): 
    - רק כאשר המשתמש/ת אישר/ה מפורשות לקבוע או לשנות ביומן, הוסף את ה-JSON בסוף התשובה שלך.
    - אל תכתוב "קבעתי" אלא "הכנתי הכל. לחץ/י על הכפתור לאישור".
    - חובה למלא נתונים אמיתיים. אם אין צורך בפעולה מסוימת (למשל אין מחיקות), השאר את הרשימה ריקה [].
    - שים לב לשדה 'override_overlap': אם זיהית שהמשתמש מבקש לקבוע אירוע על זמן שכבר תפוס, עליך להזהיר אותו בשיחה ("יש לך כבר את X בשעה הזו, לקבוע בכל זאת?"). רק אם אישר מפורשות להתעלם מההתנגשות, קבע את הערך ל-true. כברירת מחדל הערך הוא false.
    דוגמה למבנה המלא:
    {{
        "scheduled_events": [{{"title": "...", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM", "calendar_id": "ה-ID של היומן", "override_overlap": false}}],
        "updated_events": [{{"event_id": "ה-ID של האירוע להזזה", "calendar_id": "ה-ID של היומן", "title": "...", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM"}}],
        "deleted_events": [{{"event_id": "ה-ID של האירוע למחיקה", "calendar_id": "ה-ID של היומן"}}]
    }}
    - כתוב את כל התשובה שלך בלי שום קוד, מילים באנגלית או סימני פיסוק מיותרים בתוך השיחה.

    6. משימות Google Tasks ([דדליין]) נועדו לקריאה בלבד! אין להוסיף אותן ל-JSON ואסור לנסות לערוך אותן.
    7. בלילה (00:00-06:00) ישנים!
    8. אל תדבר על שום דבר שאינו ניהול לו"ז ומשימות.
    9. אל תקריא משימה מ-tasks כמו אירוע עם שעת התחלה וסיום. תתייחס לזה אך ורק כדד-ליין עם שעת סיום.
    10. הזזות ומחיקות (הכי חשוב!): כאשר עולה בקשה להזיז, לעדכן או למחוק אירוע קיים, אסור לך להפיק את ה-JSON באופן מיידי!
    קודם כל, נתח את הלוז והצג הודעת סיכום שכוללת:
    - מה מתוכנן בלו״ז קצת לפני הזמן החדש.
    - השעות העדכניות של האירוע שמזיזים.
    - מה מתוכנן בלו״ז קצת אחרי.
    בסוף ההודעה שאל מפורשות: 'האם להכין את זה?' או 'האם לאשר את השינוי?'.
    רק לאחר קבלת אישור מפורש (כמו 'כן', 'בטח' וכדומה), מותר לך לשלוח את תשובת ה-JSON עם הפעולות.
    """

# === פקודות בוט ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    token_file = f'token_{user_id}.json'

    # אם המשתמש כבר מחובר, אנחנו מדלגים על ההרשמה ישר לעבודה
    if os.path.exists(token_file):
        await update.message.reply_text("היי שוב! אנחנו כבר מחוברים ומסונכרנים. מה הלו״ז שלנו להיום? 🗓️")
        return

    # יצירת הלינק הייעודי למשתמש לשרת ה-Render שלך
    login_url = f"https://smartscheduler-pknn.onrender.com/login/{user_id}"

    # הטקסט המעודכן עם תגיות HTML להדגשה
    welcome_text = (
        "היי! 👋 כיף שבאת :)\n\n"
        "בקרוב (אם תאשר/י לי) אהיה מחובר ללו״ז שלך ולמשימות שלך דרך Google ואתחיל לארגן, להכניס ולייעץ לך איך לנהל את הזמן נכון.\n\n"
        "הנה דוגמה לדברים שאפשר לבקש ממני, אבל אני AI אז תרגיש/י חופשי לאתגר אותי:\n\n"
        "📅 <b>סיכום חכם:</b> 'מה הלו״ז שלי מחר? מתי יש לי זמן להתאוורר/ להכניס שיחה?'\n"
        "⚡️ <b>פעולות מהירות:</b> 'תקבע לי פגישה עם הצוות מחר ב-10:00.'\n"
        "🧠 <b>ייעוץ ותכנון מורכב:</b> 'אני חייבת למצוא מחר שעתיים כדי לסיים עבודה ורוצה גם להכניס אימון. ובאופן כללי לא דיברתי עם סבתא הרבה זמן'\n\n"
        "אם צריך - אגיד לך, לדוגמה, אילו אירועים כדאי להזיז ליום אחר, או שצריך לשריין זמן עבודה על דברים נוספים, כי אני רואה את הלו״ז המלא ואת הדד-ליינים.\n"
        "ועוד טיפים כאלה :)\n\n"
        f"כדי שנוכל להתחיל, <a href='{login_url}'>לחץ/י כאן לאישור החיבור ליומן</a> (זה מאובטח 🤓)."
    )

    # שולחים את ההודעה עם HTML
    await update.message.reply_text(welcome_text, parse_mode='HTML')

async def choose_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. זיהוי המשתמש (בלי לקבוע מראש איך לשלוח את ההודעה)
    if update.callback_query:
        await update.callback_query.answer()
        user_id = str(update.callback_query.message.chat_id)
    else:
        user_id = str(update.effective_user.id)

    # 2. שליפת היומנים מגוגל
    calendars = list_user_calendars(user_id)
    if not calendars:
        error_msg = "עוד לא התחברת לגוגל, או שלא מצאתי יומנים בחשבון הזה."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return

    # שמירה בזיכרון של הבוט
    context.user_data['all_calendars'] = calendars
    if 'selected_calendars' not in context.user_data:
        context.user_data['selected_calendars'] = []

    # 3. הטקסט החדש והנקי (משלב את ההצלחה ואת ההסבר)
    text = (
        "כדי שאוכל לנהל את הלו״ז שלך בצורה חכמה, בוא/י נגדיר פעם אחת את היומנים:\n\n"
        "👁 <b>קריאה:</b> אקרא מכל היומנים שתבחרי מטה כדי למנוע התנגשויות.\n"
        "✍️ <b>כתיבה חכמה:</b> אנתח כל משימה ואשבץ ליומן המתאים מאלה שתבחרי (עבודה, לימודים, אישי וכו').\n"
        "🛡 <b>שליטה שלך:</b> תמיד אציג לך לאיזה יומן אני משבץ לאישור סופי.\n\n"
        "👇 סמן/י את היומנים הרלוונטיים למטה ולחץ/י 'סיימתי':"
    )

    reply_markup = build_calendar_keyboard(context.user_data['all_calendars'], context.user_data['selected_calendars'])
    
    # 4. רגע האמת של ה-UX: עריכה מול שליחה חדשה
    if update.callback_query:
        # כאן קורה הקסם: ההודעה הקיימת משתנה במקום להוסיף אחת חדשה!
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        # הגעה מפקודה רגילה (כמו /calendars)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_text = update.message.text
    selected_ids = context.user_data.get('selected_calendars', [])
    events = list_events(user_id, selected_ids)
    
    if events is None:
        login_url = f"https://smartscheduler-pknn.onrender.com/login/{user_id}"
        await update.message.reply_text(
            f"כדי שאוכל להתחיל לעזור לך עם הלו\"ז, צריך לאשר גישה באופן חד-פעמי בלינק הבא (זה מאובטח):\n"
            f"{login_url}"
        )
        return 
        
    tasks = list_tasks(user_id)
    existing_events = events + tasks

    # --- יצירת הקשר היומנים עבור קלוד ---
    selected_ids = context.user_data.get('selected_calendars', [])
    all_cals = context.user_data.get('all_calendars', [])
    active_cals = [cal for cal in all_cals if cal['id'] in selected_ids]
    
    if active_cals:
        calendars_text = "=== יומנים זמינים לקביעת אירועים ===\n"
        calendars_text += "When creating an event in the JSON, analyze the context to choose the most appropriate 'calendar_id' from this list:\n"
        for cal in active_cals:
            calendars_text += f"- Name: '{cal['summary']}', calendar_id: '{cal['id']}'\n"
        calendars_text += "IMPORTANT: In your natural language reply to the user, explicitly state the NAME of the calendar you chose. If unsure, use 'primary' as the ID."
    else:
        calendars_text = "The user has not selected any specific calendars. Use 'primary' as the calendar_id in the JSON."
    # -----------------------------------

    if user_id not in chat_histories:
        chat_histories[user_id] = []
        
    chat_histories[user_id].append({"role": "user", "content": user_text})
    chat_histories[user_id] = chat_histories[user_id][-10:] 
    
    regular_events = []
    deadlines = []
    
    for e in existing_events:
        cal_id = e.get('calendar_id', 'primary')
        event_id = e.get('id', 'unknown_id')
        title = e.get('summary', 'ללא נושא')

        # שולפים בבטחה את הנתונים כדי למנוע קריסות
        start_data = e.get('start', {})

        if 'dateTime' in start_data:
            start_str = start_data.get('dateTime')
            end_str = e.get('end', {}).get('dateTime', '')
            try:
                start_dt = datetime.fromisoformat(start_str.replace('Z', ''))
                end_dt = datetime.fromisoformat(end_str.replace('Z', ''))
                
                # --- קסם הדדליינים ---
                # אם האירוע הוגדר מהשעה 00:00 עד 23:00/23:59, הבוט יבין שזה רק ציון דרך ולא חוסם את היום!
                if start_dt.hour == 0 and start_dt.minute == 0 and end_dt.hour >= 23:
                    deadlines.append(f"- 📌 [דדליין] {title} | ID: {event_id} | יומן: {cal_id} ({start_dt.strftime('%d/%m/%Y')})")
                else:
                    time_format = f"בתאריך {start_dt.strftime('%d/%m/%Y')} משעה {start_dt.strftime('%H:%M')} עד {end_dt.strftime('%H:%M')}"
                    regular_events.append(f"- 📅 אירוע: {title} | ID: {event_id} | יומן: {cal_id} ({time_format})")
            except Exception:
                # למקרה שהתאריך לא בפורמט צפוי
                regular_events.append(f"- 📅 אירוע: {title} | ID: {event_id} | יומן: {cal_id} מ-{start_str} עד {end_str}")
        else:
            # אלו אירועי "יום שלם" אמיתיים או משימות בלי שעות בכלל
            date_str = start_data.get('date', 'תאריך לא ידוע')
            deadlines.append(f"- 📌 [דדליין/משימה] {title} | ID: {event_id} ב-{date_str}")
            
    # בונים את הטקסט לקלוד בשני בלוקים מופרדים לחלוטין
    events_context = "=== אירועים ביומן (זמן תפוס) ===\n" 
    events_context += "\n".join(regular_events) if regular_events else "אין אירועים."
    
    events_context += "\n\n=== משימות ודדליינים (לא תופסים זמן בלוז!) ===\n" 
    events_context += "\n".join(deadlines) if deadlines else "אין דדליינים כרגע."
    
    try:
        # הקריאה לקלוד הפכה לא-סינכרונית עם הפקודה await
        message = await client.messages.create(
            model="claude-sonnet-4-6", 
            max_tokens=1000,
            system=get_system_prompt(events_context, calendars_text),
            messages=chat_histories[user_id] 
        )
        
        bot_reply = message.content[0].text
        chat_histories[user_id].append({"role": "assistant", "content": bot_reply})
        
        match = re.search(r'\{.*\}', bot_reply, re.DOTALL)
        
        if match:
            json_str = match.group(0)
            try:
                data = json.loads(json_str)
                if 'pending_actions' not in context.user_data:
                    context.user_data['pending_actions'] = {}
                context.user_data['pending_actions'][user_id] = data
                
                # --- חיתוך אגרסיבי ונקי ---
                # מוצאים את המיקום המדויק שבו ה-JSON (הסוגר המסולסל הראשון) מתחיל
                json_start_idx = bot_reply.find('{')
                # לוקחים רק את מה שקורה לפני ה-JSON
                clean_text = bot_reply[:json_start_idx].strip()
                
                # מנקים באופן מוחלט שאריות כמו גרשים או המילה json שנותרו ממש לפני ה-JSON
                for garbage in ["```json", "```", "json:", "json"]:
                    if clean_text.endswith(garbage):
                        clean_text = clean_text[:-len(garbage)].strip()
                # --------------------------
                
                keyboard = [
                    [InlineKeyboardButton("✅ אשר שינויים ביומן", callback_data='confirm')],
                    [InlineKeyboardButton("❌ עזוב, בטל", callback_data='cancel')]
                ]
                await update.message.reply_text(clean_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

            except json.JSONDecodeError:
                await update.message.reply_text(bot_reply, parse_mode='HTML')
        else:
            await update.message.reply_text(bot_reply, parse_mode='HTML')
            
    except Exception as e:
        print(f"❌ שגיאה: {e}")
        await update.message.reply_text("משהו השתבש בתקשורת עם ה-AI. נסה שוב מאוחר יותר.", parse_mode='Markdown')

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    data = query.data

    if data == "start_calendar_setup":
        await choose_calendar(update, context)
        return
        
    # --- לוגיקת בחירת יומנים ---
    if data == "finish_selection":
        selected = context.user_data.get('selected_calendars', [])
        if not selected:
            await query.edit_message_text(
                "לא נבחר אף יומן. אעבוד עם היומן הראשי (Primary) כברירת מחדל.\n\n"
                "אז מה התוכניות שלנו? אפשר פשוט לכתוב לי איך אוכל לסייע! 🗓️"
            )
        else:
            await query.edit_message_text(
                f"מעולה! שמרתי 🚀\n"
                f"אז... מה בא לך לתכנן? אפשר לבקש ממני למצוא זמן ללימודים או לאימון, לקבוע פגישות, או פשוט לשאול 'מה הלו״ז שלי מחר?' 🗓️"
            )
        return

    if data.startswith("cal_"):
        cal_index = int(data.replace("cal_", ""))
        calendars = context.user_data.get('all_calendars', [])
        
        if cal_index < len(calendars):
            cal_id = calendars[cal_index]['id'] 
            selected = context.user_data.get('selected_calendars', [])
            
            if cal_id in selected:
                selected.remove(cal_id)
            else:
                selected.append(cal_id)
                
            context.user_data['selected_calendars'] = selected
            reply_markup = build_calendar_keyboard(calendars, selected)
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        return

    # --- לוגיקת אישור/ביטול אירועים ---
    if data == 'confirm':
        # שולפים את כל הפעולות ששמרנו בזיכרון
        pending_data = context.user_data.get('pending_actions', {}).get(user_id, {})
        
        scheduled = pending_data.get('scheduled_events', [])
        updated_events_list = pending_data.get('updated_events', [])
        deleted = pending_data.get('deleted_events', [])
        
        selected_ids = context.user_data.get('selected_calendars', [])
        existing_events = list_events(user_id, selected_ids)
        
        await query.edit_message_text("מתחיל לארגן את היומן... ⏳")
        days_heb = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
        
        # 1. ביצוע מחיקות
        for e in deleted:
            cal_id = e.get('calendar_id')
            event_id = e.get('event_id')
            success, msg = delete_event(user_id, cal_id, event_id)
            if success:
                await query.message.reply_text("🗑️ אירוע נמחק מהיומן בהצלחה.")
            else:
                await query.message.reply_text(f"⚠️ שגיאה במחיקה: {msg}")

        # 2. ביצוע הזזות ועדכונים
        for e in updated_events_list:
            cal_id = e.get('calendar_id')
            event_id = e.get('event_id')
            start_iso = f"{e['start_date']}T{e['start_time']}:00+03:00"
            end_iso = f"{e['end_date']}T{e['end_time']}:00+03:00"
            
            success, msg = update_event_time(user_id, cal_id, event_id, start_iso, end_iso)
            if success:
                await query.message.reply_text(f"🔄 עודכן בהצלחה:\n<b>{msg}</b> (הוזז ל-{e['start_time']} עד {e['end_time']})", parse_mode='HTML')
            else:
                await query.message.reply_text(f"⚠️ שגיאה בעדכון: {msg}")

        # 3. יצירת אירועים חדשים
        for e in scheduled:
            start_iso = f"{e['start_date']}T{e['start_time']}:00+03:00"
            end_iso = f"{e['end_date']}T{e['end_time']}:00+03:00"
            target_cal_id = e.get('calendar_id', 'primary')
            
            cal_name = "ראשי"
            for c in context.user_data.get('all_calendars', []):
                if c['id'] == target_cal_id:
                    cal_name = c['summary']
                    break
            
            overlap, conflict = is_overlap(start_iso, end_iso, existing_events)
            
            # בודקים אם קלוד העביר את הסיסמה לעקוף את החסימה
            override = e.get('override_overlap', False)
            
            if overlap and not override:
                await query.message.reply_text(f"⚠️ דילגתי על '{e['title']}' - מזהה התנגשות עם '{conflict}'.\n(אם זה בכוונה, פשוט תכתב/י לי: 'תקבע בכל זאת').")
            else:
                create_event(user_id, e['title'], start_iso, end_iso, calendar_id=target_cal_id) 
                
                try:
                    start_date_obj = datetime.strptime(e['start_date'], "%Y-%m-%d")
                    start_day_name = days_heb[start_date_obj.weekday()]
                    start_date_formatted = start_date_obj.strftime("%d/%m/%Y")
                    
                    if e['start_date'] == e['end_date']:
                        success_msg = f"✅ נקבע ביומן '<b>{cal_name}</b>':\n{e['title']} (יום {start_day_name}, {start_date_formatted} בשעות {e['start_time']}-{e['end_time']})"
                    else:
                        end_date_obj = datetime.strptime(e['end_date'], "%Y-%m-%d")
                        end_day_name = days_heb[end_date_obj.weekday()]
                        end_date_formatted = end_date_obj.strftime("%d/%m/%Y")
                        success_msg = f"✅ נקבע ביומן '<b>{cal_name}</b>':\n{e['title']}\n(מיום {start_day_name} {start_date_formatted} ב-{e['start_time']} עד יום {end_day_name} {end_date_formatted} ב-{e['end_time']})"
                        
                except Exception:
                    success_msg = f"✅ נקבע ביומן '<b>{cal_name}</b>':\n{e['title']}"
                
                await query.message.reply_text(success_msg, parse_mode='HTML')
        
        # מנקים את הזיכרון אחרי שסיימנו
        if user_id in context.user_data.get('pending_actions', {}):
            del context.user_data['pending_actions'][user_id]
            
        await query.message.reply_text("✅ סיימתי! הלו״ז שלך מעודכן ומסודר.")
        
    elif data == 'cancel':
        # ניקוי הזיכרון גם במקרה של ביטול
        if user_id in context.user_data.get('pending_actions', {}):
            del context.user_data['pending_actions'][user_id]
        await query.edit_message_text("❌ בוטל. הלו\"ז נשאר כמו שהיה.")


# === פונקציית השרת ברקע לטובת Render ===
def run_web_server():
    port = int(os.environ.get("PORT", 5000))
    # ודאי שהמשתנה flask_app שהבאנו בתחילת הקובץ אכן מוגדר נכון
    flask_app.run(host="0.0.0.0", port=port)


if __name__ == '__main__':
    
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("calendars", choose_calendar)) 
    telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    telegram_app.add_handler(CallbackQueryHandler(button_click))
    
    telegram_app.run_polling()