import os
from datetime import date

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

TIMEOUT_SECONDS = float(os.getenv("WHATSAPP_TIMEOUT_SECONDS", "15"))


def _session():
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"POST"},
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def _get_secret(key: str) -> str:
    value = os.getenv(key)
    if value:
        return value
    raise RuntimeError(f"Missing required secret: {key}")


def _send(payload: dict):
    token = _get_secret("ACCESS_TOKEN")
    phone_id = _get_secret("PHONE_NUMBER_ID")
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    response = _session().post(url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
    response_body = response.json() if response.content else {}
    attempted_to = str(payload.get("to", ""))[-4:]
    print(f"Status: {response.status_code} | Send attempted for {attempted_to}")
    if not response.ok:
        print(f"Error response: {response_body}")
    return response


def send_text(to: str, message: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    return _send(payload)


def send_template(to: str, template_name: str, params: list[str]):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": value} for value in params],
                }
            ],
        },
    }
    return _send(payload)


def send_attendance_alert(student_name: str, phone: str, institute: str):
    today = date.today().strftime("%d %B %Y")
    message = (
        "Attendance Alert\n\n"
        f"Dear Parent, *{student_name}* was marked *absent* "
        f"today ({today}) at {institute}.\n\nReply if this is a mistake."
    )
    return send_text(phone, message)
