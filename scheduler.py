from apscheduler.schedulers.background import BackgroundScheduler
from database import get_unpaid_students
from whatsapp import send_text
import time

def send_fee_reminders():
    print("\n⏰ Running fee reminder job...")
    unpaid = get_unpaid_students()
    if not unpaid:
        print("✅ All fees paid")
        return
    for student in unpaid:
        message = (
            f"📚 Fee Reminder\n\n"
            f"Hi {student['name']}, your fee of ₹{student['fee_amount']} "
            f"for *{student['batch']}* batch is due on {student['fee_due_date']}.\n\n"
            f"Contact {student['institute']} to avoid late charges. 🙏"
        )
        send_text(student["phone"], message)
        time.sleep(1)
        print(f"✅ Sent to {student['name']}")
    print(f"📤 Done — {len(unpaid)} reminders sent\n")

scheduler = BackgroundScheduler()
scheduler.add_job(send_fee_reminders, 'cron', hour=9,  minute=0)
scheduler.add_job(send_fee_reminders, 'cron', hour=18, minute=0)
