import os
import requests
from flask import Flask, request
from google_auth_oauthlib.flow import Flow
import json

def notify_user_login_success(user_id):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # 2. כאן השינוי: עוטפים את ה-reply_markup ב-json.dumps
    payload = {
        "chat_id": user_id,
        "text": "חיבור ה-Google Calendar הצליח! 🎉\nעכשיו בוא נגדיר את היומנים שלך באופן חד-פעמי כדי שאוכל לעזור לך לתכנן את הלו״ז.",
        "reply_markup": json.dumps({
            "inline_keyboard": [[
                {"text": "התחל הגדרת יומנים 🗓️", "callback_data": "start_calendar_setup"}
            ]]
        })
    }
    requests.post(url, json=payload)

app = Flask(__name__)

# חובה כדי שנוכל לבדוק את זה לוקאלית
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

CLIENT_SECRETS_FILE = "client_secret_web.json"
SCOPES = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/tasks.readonly']

# כאן נשמור את התהליך (ה-flow) של כל משתמש כדי שהשרת לא ישכח אותו
active_flows = {}

@app.route('/login/<user_id>')
def login(user_id):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri='https://smartscheduler-pknn.onrender.com/oauth2callback'
    )
    
    auth_url, state = flow.authorization_url(
    access_type='offline',
    include_granted_scopes='true',
    state=user_id,
    prompt='consent'
)
    
    active_flows[user_id] = flow
    
    return f'<h2 style="font-family: Arial; text-align: center; margin-top: 50px;">היי! כדי לחבר את הבוט, <a href="{auth_url}">לחצי כאן לאישור גישה ליומן</a></h2>'

@app.route('/oauth2callback')
def oauth2callback():
    user_id = request.args.get('state') 
    
    # שולפים את אותו אובייקט בדיוק שהתחיל את התהליך (במקום ליצור חדש)
    flow = active_flows.get(user_id)
    
    if not flow:
        return "שגיאה: התהליך לא נמצא. נסי להתחבר מחדש."
    
    flow.fetch_token(authorization_response=request.url)
    
    creds = flow.credentials
    with open(f'token_{user_id}.json', 'w') as token_file:
        token_file.write(creds.to_json())
    notify_user_login_success(user_id) 
    return '<h2 style="font-family: Arial; text-align: center; color: green; margin-top: 50px;">✅ ההתחברות עברה בהצלחה! אפשר לסגור את החלון ולחזור לטלגרם.</h2>'

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)