import requests
import os
from dotenv import load_dotenv
load_dotenv()

def _get_secret(key):
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val:
            return val
    except Exception:
        pass
    return os.getenv(key)

def send_text(to, message):
    TOKEN = _get_secret("ACCESS_TOKEN")
    PHONE_ID = _get_secret("PHONE_NUMBER_ID")
    url = f"https://graph.facebook.com/v21.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}
    res = requests.post(url, json=payload, headers=headers)
    print(f"Status: {res.status_code} | Response: {res.json()}")
    return res

def send_template(to, template_name, params):
    TOKEN = _get_secret("ACCESS_TOKEN")
    PHONE_ID = _get_secret("PHONE_NUMBER_ID")
    url = f"https://graph.facebook.com/v21.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
        }
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"Status: {res.status_code} | Response: {res.json()}")
    return res

def send_attendance_alert(student_name, phone, institute):
    from datetime import date
    today = date.today().strftime("%d %B %Y")
    message = (
        f"📋 Attendance Alert\n\n"
        f"Dear Parent, *{student_name}* was marked *absent* "
        f"today ({today}) at {institute}.\n\nReply if this is a mistake."
    )
    send_text(phone, message)
    print(f"✅ Attendance alert sent to {phone}")
