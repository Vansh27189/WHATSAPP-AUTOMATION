import requests, os
from dotenv import load_dotenv
load_dotenv()

TOKEN    = os.getenv("ACCESS_TOKEN")
PHONE_ID = os.getenv("PHONE_NUMBER_ID")

def send_text(to, message):
    url = f"https://graph.facebook.com/v21.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.json()}")
    return res

def send_template(to, template_name, params):
    url = f"https://graph.facebook.com/v21.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": p} for p in params
                ]
            }]
        }
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.json()}")
    return res
