from whatsapp import send_template
import time

students = [
    {
        "name": "Vansh",
        "phone": "919350365703",
        "batch": "IIT-JEE Morning",
        "fee_amount": "2500",
        "fee_due_date": "10 March 2026"
    },
    {
        "name": "Kartik Gendu",
        "phone": "918168366780",
        "batch": "NEET Evening",
        "fee_amount": "3000",
        "fee_due_date": "10 March 2026"
    },
    {
        "name": "Smarth",
        "phone": "917419082088",
        "batch": "HELLO Evening",
        "fee_amount": "3000",
        "fee_due_date": "10 March 2026"
    },
    {
        "name": "Rehan",
        "phone": "917082186156",
        "batch": "HELLO Evening",
        "fee_amount": "3000",
        "fee_due_date": "10 March 2026"
    },
]

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
