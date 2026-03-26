from apscheduler.schedulers.background import BackgroundScheduler
from backend.database import get_unpaid_students
from backend.whatsapp import send_template
import time

def send_fee_reminders():
    print("\n⏰ Running fee reminder job...")
    unpaid = get_unpaid_students()
    if not unpaid:
        print("✅ All fees paid")
        return
    for student in unpaid:
        send_template(
            to            = student["phone"],
            template_name = "fees_remainder1",
            params        = [
                student["name"],
                str(int(student["fee_amount"])),
                student["batch"],
                student["fee_due_date"]
            ]
        )
        time.sleep(1)
        print(f"✅ Sent to {student['name']}")
    print(f"📤 Done — {len(unpaid)} reminders sent\n")

scheduler = BackgroundScheduler()
scheduler.add_job(send_fee_reminders, 'cron', hour=9,  minute=0)
scheduler.add_job(send_fee_reminders, 'cron', hour=18, minute=0)
