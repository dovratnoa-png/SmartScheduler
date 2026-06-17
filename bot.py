import os
import json
import re
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv() 
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from calendar_tools import create_event, list_events, is_overlap, list_tasks

load_dotenv()
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

pending_schedules = {}
chat_histories = {} 

def get_system_prompt(events_context):
    now = datetime.now()
    days = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    today_str = f"היום: יום {days[now.weekday()]}, {now.strftime('%d/%m/%Y')}. השעה הנוכחית היא: {now.strftime('%H:%M')}."

    return f"""
    אתה Chief of Staff ויועץ אסטרטגי חכם. הלו"ז הקיים:

    ===הלו״ז הקיים===
    {events_context}

    {today_str}
    
    ===זמן ולוח שנה ישראלי===
    שים לב היטב להגדרת השבועות בישראל. 
    - ״השבוע״ יסתיים ביום שבת הקרוב.
    -  יום ראשון הקרוב הוא כבר בשבוע הבא. כשמדברים על השבוע הנוכחי, יום ראשון הבא כבר לא נכלל בשבוע הזה
    - בשעות הלילה 00:00-06:00 ישנים! לא להציע דברים כמו לימודים או אימונים לשעות האלה. רק אם המשתמש מבקש ממך ישירות לקבוע שם אירוע

    ===חוקי ברזל לעבודה===
    1.  שים לב לשעה הנוכחית המצוינת למעלה ({now.strftime('%H:%M')}). לעולם אל תציע לשבץ אירועים היום בשעות שכבר עברו!
    2. תקציר יומי ודדליינים: כשאתה מציע חלופות לשעות וימים, חובה עליך להציג משפט תקציר על רמת העומס באותו יום לפי הלו"ז. בנוסף, חובה עליך להזכיר תמיד דדליינים קרובים (אירועים שמוגדרים כ"[דדליין/משימה]") כדי שהיא תוכל לתכנן את זמן הלמידה שלה כראוי.
    3. ניהול שיחה: נהל דו-שיח קצר, טבעי ותכליתי. שאל אותה אם השעות נוחות לה לפני שאתה קובע עובדות.
    4. עברית: כתוב בעברית ישראלית, קלילה, וטבעית. 
    5. חוק ה-JSON (קריטי!): 
    - כל עוד אין הסכמה סופית על השעות - ענה בטקסט חופשי בלבד.
    - רק כאשר המשתמשת אישרה מפורשות לקבוע ביומן, הוסף את ה-JSON.
    - הבנה ארכיטקטונית: אתה רק מכין את הנתונים, אתה לא קובע ביומן בעצמך! לעולם אל תכתוב "קבעתי", "נקבע" או "הוספתי". במקום זאת, כתוב משהו כמו: "מעולה, הכנתי הכל. לחצי על הכפתור למטה כדי לאשר ולהכניס את זה ליומן".
    - חובה עליך למלא את הנתונים האמיתיים (תאריך, כותרת, שעות) בתוך הרשימה.
    - **כלל ביטחון:** אם אתה לא בטוח ב-100% שאירוע מסוים לא מתנגש עם משהו קיים (במיוחד אם יש מילואים או אירועים צפופים באותו יום), **אל תכלול אותו ב-JSON**. במקום זאת, תגיד לי: "נראה שיש פוטנציאל להתנגשות במטלה בלינארית, בוא נבחר זמן אחר", ותחכה שאגיד לך מתי.
    - הדפס את ה-JSON נקי, בלי עטיפות של Markdown. דוגמה למבנה:
    {{"scheduled_events": [{{"title": "...", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM"}}]}}
    6. דדליינים מ-Google Tasks: אירועים שמופיעים עם התג "[דדליין]" הם משימות לקריאה בלבד!
    - מטרתם היחידה היא לתת לך קונטקסט כדי שתדע להזכיר למשתמשת על הגשות קרובות.
    - אסור לך בשום אופן לנסות לקבוע, להזיז, למחוק או לערוך אותם.
    - לעולם אל תכלול אותם בתוך רשימת ה-JSON של האירועים לקביעה. הם שם רק כדי שתייעץ טוב יותר
    7. בשעות הלילה - ישנים! לא לקבוע דברים כמו לימודים, שיחות, אימונים או עבודה
   ֿ 8. אל תדבר על שום דבר שהוא לא תכנון לו״ז, משימות או דברים בסגנון - גם אם מנסים לשאול אותך דברים אחרים!
    """

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    events = list_events(user_id)
    
    if events is None:
        login_url = f"https://smartscheduler-pknn.onrender.com/login/{user_id}"
        await update.message.reply_text(
            f"היי! איזה כיף שבאת 📅\n"
            f"נראה שעוד לא חיברת את היומן שלך. כדי שאוכל להתחיל לעזור לך עם הלו\"ז, צריך לאשר גישה באופן חד-פעמי בלינק הבא:\n"
            f"{login_url}"
        )
        return 
        
    tasks = list_tasks(user_id)
    existing_events = events + tasks

    if user_id not in chat_histories:
        chat_histories[user_id] = []
        
    chat_histories[user_id].append({"role": "user", "content": user_text})
    chat_histories[user_id] = chat_histories[user_id][-10:] # שומרים 10 הודעות אחרונות כדי לא להעמיס
    
    #await update.message.reply_text("קיבלתי. רק רגע...")
    
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
            system=get_system_prompt(events_context),
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
                await update.message.reply_text(clean_text, reply_markup=InlineKeyboardMarkup(keyboard))

            except json.JSONDecodeError:
                await update.message.reply_text(bot_reply)
        else:
            await update.message.reply_text(bot_reply)
            
    except Exception as e:
        print(f"❌ שגיאה: {e}")
        await update.message.reply_text("משהו השתבש בתקשורת עם ה-AI.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "היי! 👋 אני לא סתם יומן, אני העוזר האישי שלך:)\n"
        "אני מחובר ללו״ז שלך ויודע לארגן, להכניס, להזיז ולייעץ לך איך לנהל את הזמן נכון.\n\n"
        "הנה כמה דברים שאפשר לבקש ממני:\n"
        "📅 *סיכום חכם:* 'מה הלו״ז שלי מחר? איפה יש לי אוויר לנשום?'\n"
        "⚡️ *פעולות מהירות:* 'תקבע לי פגישה עם הצוות מחר ב-10:00.'\n"
        "🧠 .ייעוץ ותכנון מורכב:* 'אני חייבת למצוא מחר שעה וחצי לסיים עבודה וממש רוצה גם להכניס אימון. מה הזמן האידיאלי? ואם צריך - תציע לי אילו פגישות כדאי להזיז ליום ראשון. אגב, אם אתה חושב שאני צריכה להכניס עבודה על מטלות נוספות לפי הדד-ליינים שלהן - תציף'\n\n"
        "כדי להתחיל, פשוט תכתבי לי הודעה. אם עדיין לא התחברת ליומן - מיד אשלח לך לינק!"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if query.data == 'confirm':
        events = pending_schedules.get(user_id, [])
        existing_events = list_events(user_id) 
        
        await query.edit_message_text("מתחיל בקביעת האירועים...")
        
        days_heb = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
        
        for e in events:
            start_iso = f"{e['start_date']}T{e['start_time']}:00+03:00"
            end_iso = f"{e['end_date']}T{e['end_time']}:00+03:00"
            
            overlap, conflict = is_overlap(start_iso, end_iso, existing_events)
            
            if overlap:
                await query.message.reply_text(f"⚠️ דילגתי על '{e['title']}' - מתנגש עם '{conflict}'")
            else:
                create_event(user_id,e['title'], start_iso, end_iso) 
                
                try:
                    start_date_obj = datetime.strptime(e['start_date'], "%Y-%m-%d")
                    start_day_name = days_heb[start_date_obj.weekday()]
                    start_date_formatted = start_date_obj.strftime("%d/%m/%Y")
                    
                    if e['start_date'] == e['end_date']:
                        success_msg = f"✅ נקבע: {e['title']} (יום {start_day_name}, {start_date_formatted} בשעות {e['start_time']}-{e['end_time']})"
                    else:
                        end_date_obj = datetime.strptime(e['end_date'], "%Y-%m-%d")
                        end_day_name = days_heb[end_date_obj.weekday()]
                        end_date_formatted = end_date_obj.strftime("%d/%m/%Y")
                        
                        success_msg = f"✅ נקבע: {e['title']}\n(מיום {start_day_name} {start_date_formatted} ב-{e['start_time']} עד יום {end_day_name} {end_date_formatted} ב-{e['end_time']})"
                        
                except Exception:
                    if e.get('start_date') == e.get('end_date'):
                        success_msg = f"✅ נקבע: {e['title']} ({e.get('start_date')} בשעות {e['start_time']}-{e['end_time']})"
                    else:
                        success_msg = f"✅ נקבע: {e['title']} (מ-{e.get('start_date')} {e['start_time']} עד {e.get('end_date')} {e['end_time']})"
                
                await query.message.reply_text(success_msg)
        
        await query.message.reply_text("✅ סיימתי לעדכן את היומן!")
    else:
        await query.edit_message_text("❌ בוטל. הלו\"ז נשאר נקי.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_click))
    app.run_polling()