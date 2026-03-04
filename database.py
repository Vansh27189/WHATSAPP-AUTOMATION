from datetime import date

# Student list — each student is a dict
students = [
    {
        "name": "Vansh",
        "phone": "919350365703",    # ← your own number (already whitelisted)
        "batch": "IIT-JEE Morning",
        "fee_amount": 2500,
        "fee_due_date": "10 March 2026",
        "fee_paid": False,
        "institute": "Shree Coaching Centre"
    },
    {
        "name": "kartik gendu",
        "phone": "918168366780",    # ← add another whitelisted number or remove this
        "batch": "NEET Evening",
        "fee_amount": 3000,
        "fee_due_date": "10 March 2026",
        "fee_paid": False,
        "institute": "Shree Coaching Centre"
    },
    {
        "name": "SMARTH",
        "phone": "917419082088",    # ← add another whitelisted number or remove this
        "batch": "HELLO Evening",
        "fee_amount": 3000,
        "fee_due_date": "10 March 2026",
        "fee_paid": False,
        "institute": "Shree Coaching Centre"
    },
    {
        "name": "REHAN",
        "phone": "917082186156",    # ← add another whitelisted number or remove this
        "batch": "HELLO Evening",
        "fee_amount": 3000,
        "fee_due_date": "10 March 2026",
        "fee_paid": False,
        "institute": "Shree Coaching Centre"
    }
]

def get_unpaid_students():
    """Return all students who haven't paid fee"""
    return [s for s in students if not s["fee_paid"]]

def mark_paid(phone):
    """Mark student as paid"""
    for s in students:
        if s["phone"] == phone:
            s["fee_paid"] = True
            print(f"✅ {s['name']} marked as paid")
