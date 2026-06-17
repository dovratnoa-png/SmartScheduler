import os
import json
import re
from datetime import datetime
import anthropic
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ייבוא כל הפונקציות שלנו מ-calendar_tools
from calendar_tools import list_user_calendars, create_event, list_events, is_overlap, list_tasks

load_dotenv() 
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

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
    now = datetime.now()
    days = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    today_str = f"היום: יום {days[now.weekday()]}, {now.strftime('%d/%m/%Y')}. השעה הנוכחית היא: {now.strftime('%H:%M')}."

    return f"""
    אתה Chief of Staff ויועץ אסטרטגי חכם. 
    
    ===הלו״ז הקיים===
    {events_context}

    {today_str}
    
    {calendars_text}
    
    ===זמן ולוח שנה ישראלי===
    שים לב היטב להגדרת השבועות בישראל. 
    - ״השבוע״ יסתיים ביום שבת הקרוב.
    -  יום ראשון הקרוב הוא כבר בשבוע הבא. כשמדברים על השבוע הנוכחי, יום ראשון הקרוב לא נחשב בשבוע הנוכחי
    - בשעות הלילה 00:00-06:00 ישנים! לא להציע דברים כמו לימודים או אימונים לשעות האלה. רק אם המשתמש מבקש ממך ישירות לקבוע שם אירוע


    IMPORTANT FORMATTING RULES:
    You are interacting with a Telegram bot configured to parse HTML. You MUST format all your responses using ONLY Telegram-supported HTML tags (<b>, <i>, <u>).
    NEVER use Markdown formatting (do not use * or ** or _ for emphasis). 

    ===חוקי ברזל לעבודה===
    1. שים לב לשעה הנוכחית. לעולם אל תציע לשבץ אירועים היום בשעות שכבר עברו!
    2. תקציר יומי ודדליינים: חובה עליך להציג משפט תקציר על רמת העומס ולהזכיר דדליינים קרובים.
    3. ניהול שיחה: נהל דו-שיח קצר וטבעי וקבל אישור לפני קביעת עובדות.
    4. עברית: כתוב בעברית ישראלית, קלילה וטבעית. 
    5. חוק ה-JSON (קריטי!): 
    - רק כאשר המשתמשת אישרה מפורשות לקבוע ביומן, הוסף את ה-JSON.
    - אל תכתוב "קבעתי" אלא "הכנתי הכל. לחצי על הכפתור לאישור".
    - חובה למלא נתונים אמיתיים. במקרה של התנגשות, אל תכלול ב-JSON.
    - הדפס את ה-JSON נקי. הוספנו שדה חדש - calendar_id! דוגמה למבנה:
    {{"scheduled_events": [{{"title": "...", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM", "calendar_id": "ה-ID של היומן הנבחר"}}]}}
    6. משימות Google Tasks ([דדליין]) נועדו לקריאה בלבד! אין להוסיף אותן ל-JSON.
    7. בלילה (00:00-06:00) ישנים!
    8. אל תדבר על שום דבר שאינו ניהול לו"ז ומשימות.
    """

# === פקודות בוט ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "היי! 👋 כיף שבאת :) \nאני לא סתם יומן, אני העוזר האישי שלך \n\n"
        "בקרוב (אחרי שתאשר לי) אהיה מחובר ללו״ז שלך(Google Calendar) ולמשימות שלך (Google Tasks) ואתחיל לארגן, להכניס ולייעץ לך איך לנהל את הזמן נכון.\n\n"
        "הנה כמה דברים שאפשר לבקש ממני:\n"
        "📅 <b>סיכום חכם:</b> 'מה הלו״ז שלי מחר? איפה יש לי אוויר לנשום?'\n"
        "⚡️ <b>פעולות מהירות:</b> 'תקבע לי פגישה עם הצוות מחר ב-10:00.'\n"
        "🧠 <b>ייעוץ ותכנון מורכב:</b> 'אני חייבת למצוא מחר שעה וחצי כדי לסיים עבודה להגשה וממש רוצה גם להכניס אימון. איך אוכל לעשות את זה בצורה הכי אידיאלית'? \n אם צריך - אגיד לך אילו אירועים כדאי להזיז ליום אחר, ואם אני רואה שאת צריכה לשריין זמן עבודה על מטלות נוספות לפי הדד-ליינים שלהן. ועוד טיפים כאלה - אני אגיד לך:)\n\n"
        "כדי להתחיל, פשוט תכתבי לי הודעה. אם עדיין לא התחברת ליומן - מיד אשלח לך לינק!"
    )
    await update.message.reply_text(welcome_text, parse_mode='HTML')

async def choose_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # אנחנו צריכות לדעת אם זה הגיע מפקודה או מכפתור, אז נשתמש ב-update.callback_query אם קיים
    if update.callback_query:
        await update.callback_query.answer()
        user_id = str(update.callback_query.message.chat_id)
        reply_func = update.callback_query.message.reply_text
    else:
        user_id = str(update.effective_user.id)
        reply_func = update.message.reply_text

    calendars = list_user_calendars(user_id)
    if not calendars:
        await reply_func("עוד לא התחברת לגוגל, או שלא מצאתי יומנים בחשבון הזה.")
        return

    context.user_data['all_calendars'] = calendars
    if 'selected_calendars' not in context.user_data:
        context.user_data['selected_calendars'] = []

    # ההסבר המפורט שביקשת:
    explainer_text = (
        "<b>בוא נגדיר את היומנים שלך:</b>\n\n"
        "1. <b>קריאה:</b> בחר את היומנים שמהם אני צריך לקרוא נתונים (כדי שאוכל לראות הכל ולמנוע התנגשויות בלו״ז).\n"
        "2. <b>כתיבה חכמה:</b> כשנרצה לקבוע אירוע חדש, אני (ה-AI) אנתח לפי ההקשר לאיזה יומן הכי מתאים להוסיף אותו (עבודה, לימודים, אישי וכו').\n"
        "3. <b>שקיפות:</b> אני תמיד אציג לך לפני אישור לאיזה יומן אני מתכנן להוסיף את האירוע, כדי שתוכל לוודא שזה מתאים לך. 🛡️\n\n"
        "סמן את היומנים הרצויים ולחץ על 'סיימתי'."
    )

    reply_markup = build_calendar_keyboard(context.user_data['all_calendars'], context.user_data['selected_calendars'])
    await reply_func(explainer_text, reply_markup=reply_markup, parse_mode='HTML')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_text = update.message.text
    selected_ids = context.user_data.get('selected_calendars', [])
    events = list_events(user_id, selected_ids)
    
    if events is None:
        login_url = f"https://smartscheduler-pknn.onrender.com/login/{user_id}"
        await update.message.reply_text(
            f"נדיר! 📅\n"
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
    
    events_str_list = []
    for e in existing_events:
        if 'dateTime' in e['start']:
            start_str = e['start'].get('dateTime')
            end_str = e['end'].get('dateTime')
            try:
                start_dt = datetime.fromisoformat(start_str.replace('Z', ''))
                end_dt = datetime.fromisoformat(end_str.replace('Z', ''))
                time_format = f"בתאריך {start_dt.strftime('%d/%m/%Y')} משעה {start_dt.strftime('%H:%M')} עד {end_dt.strftime('%H:%M')}"
                events_str_list.append(f"- אירוע: {e['summary']} ({time_format})")
            except Exception:
                events_str_list.append(f"- אירוע: {e['summary']} מ-{start_str} עד {end_str}")
        else:
            events_str_list.append(f"- [דדליין/משימה] {e['summary']} ב-{e['start'].get('date')}")
            
    events_context = "\n".join(events_str_list)
    
    try:
        message = client.messages.create(
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
                pending_schedules[user_id] = data.get('scheduled_events', [])
                clean_text = bot_reply.replace(json_str, "").strip()
                keyboard = [
                    [InlineKeyboardButton("✅ קבע הכל ביומן", callback_data='confirm')],
                    [InlineKeyboardButton("❌ עזוב, בטל", callback_data='cancel')]
                ]
                await update.message.reply_text(clean_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

            except json.JSONDecodeError:
                await update.message.reply_text(bot_reply, parse_mode='HTML')
        else:
            await update.message.reply_text(bot_reply, parse_mode='HTML')
            
    except Exception as e:
        print(f"❌ שגיאה: {e}")
        await update.message.reply_text(f"משהו השתבש בתקשורת עם ה-AI.\nהשגיאה המדויקת היא:\n`{str(e)}`", parse_mode='Markdown')

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
                "לא בחרת אף יומן. אעבוד עם היומן הראשי (Primary) כברירת מחדל.\n\n"
                "אז מה התוכניות שלנו? מוזמנת לכתוב לי איך תרצי שאסייע! 🗓️"
            )
        else:
            await query.edit_message_text(
                f"מעולה! שמרתי {len(selected)} יומנים בהצלחה. 🚀\n"
                f"מעכשיו אנתח לאיזה יומן כל משימה שייכת.\n\n"
                f"אז... מה בא לך לתכנן? אפשר לבקש ממני למצוא זמן ללימודים או לאימון, לקבוע פגישות, או פשוט לשאול 'מה הלו״ז שלי מחר?' 🗓️"
            )
        return

    if data.startswith("cal_"):
        # שולפים את המספר הסידורי של היומן מתוך הכפתור
        cal_index = int(data.replace("cal_", ""))
        calendars = context.user_data.get('all_calendars', [])
        
        # מוודאים שהמספר תקין
        if cal_index < len(calendars):
            cal_id = calendars[cal_index]['id'] # שולפים את ה-ID האמיתי והארוך מהזיכרון
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
        events = pending_schedules.get(user_id, [])
        selected_ids = context.user_data.get('selected_calendars', [])
        existing_events = list_events(user_id, selected_ids)
        
        await query.edit_message_text("מתחיל בקביעת האירועים...")
        days_heb = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
        
        for e in events:
            start_iso = f"{e['start_date']}T{e['start_time']}:00+03:00"
            end_iso = f"{e['end_date']}T{e['end_time']}:00+03:00"
            
            # שולפים את היומן שקלוד בחר, אם לא בחר - primary
            target_cal_id = e.get('calendar_id', 'primary')
            
            # מוצאים את השם היפה של היומן להודעת הסיום
            cal_name = "ראשי"
            for c in context.user_data.get('all_calendars', []):
                if c['id'] == target_cal_id:
                    cal_name = c['summary']
                    break
            
            overlap, conflict = is_overlap(start_iso, end_iso, existing_events)
            
            if overlap:
                await query.message.reply_text(f"⚠️ דילגתי על '{e['title']}' - מתנגש עם '{conflict}'")
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
        
        await query.message.reply_text("✅ סיימתי לעדכן את היומן!")
    elif data == 'cancel':
        await query.edit_message_text("❌ בוטל. הלו\"ז נשאר נקי.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("calendars", choose_calendar)) # הפקודה החדשה!
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_click))
    app.run_polling()