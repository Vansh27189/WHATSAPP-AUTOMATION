from whatsapp import send_text
from database import get_unpaid_students
import time

students = get_unpaid_students()
print(f"📤 Sending to {len(students)} students...\n")

for student in students:
    message = (
        f"📚 Fee Reminder\n\n"
        f"Hi {student['name']}, your fee of ₹{student['fee_amount']} "
        f"for *{student['batch']}* batch is due on {student['fee_due_date']}.\n\n"
        f"Contact {student['institute']} to avoid late charges. 🙏"
    )
    send_text(student["phone"], message)
    time.sleep(1)
    print(f"✅ Sent to {student['name']} ({student['phone']})\n")

print(f"🎉 Done! Sent to {len(students)} students.")
