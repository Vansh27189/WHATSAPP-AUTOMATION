import time
import os

from backend.whatsapp import send_template

students = [
    {
        "name": "Vansh",
        "phone": "911111111111",
        "batch": "IIT-JEE Morning",
        "fee_amount": "2500",
        "fee_due_date": "10 March 2026"
    },
    {
        "name": "Kartik Gendu",
        "phone": "922222222222",
        "batch": "NEET Evening",
        "fee_amount": "3000",
        "fee_due_date": "10 March 2026"
    },
    {
        "name": "Smarth",
        "phone": "933333333333",
        "batch": "HELLO Evening",
        "fee_amount": "3000",
        "fee_due_date": "10 March 2026"
    },
    {
        "name": "Rehan",
        "phone": "944444444444",
        "batch": "HELLO Evening",
        "fee_amount": "3000",
        "fee_due_date": "10 March 2026"
    },
]

if __name__ == "__main__":
    if os.getenv("ENABLE_QUICK_TEST") != "true":
        raise SystemExit("Set ENABLE_QUICK_TEST=true to run this script.")

    for s in students:
        send_template(
            to            = s["phone"],
            template_name = "fees_remainder1",
            params        = [
                s["name"],
                s["fee_amount"],
                s["batch"],
                s["fee_due_date"]
            ]
        )
        time.sleep(1)
        print(f"✅ Sent to {s['name']} ({s['phone']})")

    print(f"\n🎉 Done! Sent to {len(students)} students.")
