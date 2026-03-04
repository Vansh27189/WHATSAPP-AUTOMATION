from apscheduler.schedulers.background import BackgroundScheduler
from database import get_unpaid_students
from whatsapp import send_text, send_template

def send_fee_reminders():
    """Runs every day at 9 AM — sends reminder to unpaid students"""
    print("\n⏰ Running fee reminder job...")
    unpaid = get_unpaid_students()
    
    if not unpaid:
        print("✅ All fees paid — no reminders needed")
        return

    for student in unpaid:
        # Using plain text (works without template approval)
        message = (
            f"📚 Fee Reminder\n\n"
            f"Hi {student['name']}, your fee of ₹{student['fee_amount']} "
            f"for *{student['batch']}* batch is due on {student['fee_due_date']}.\n\n"
            f"Please contact {student['institute']} to avoid late charges.\n\n"
            f"Thank you! 🙏"
        )
        send_text(student["phone"], message)

    print(f"📤 Sent reminders to {len(unpaid)} students\n")


def send_attendance_alert(student_name, phone, institute):
    """Call this manually when marking attendance"""
    from datetime import date
    today = date.today().strftime("%d %B %Y")
    message = (
        f"📋 Attendance Alert\n\n"
        f"Dear Parent, *{student_name}* was marked *absent* today ({today}) "
        f"at {institute}.\n\n"
        f"Reply to this message if this is a mistake."
    )
    send_text(phone, message)


# Setup the scheduler
scheduler = BackgroundScheduler()

# Fee reminder — runs every day at 9:00 AM [web:87]
scheduler.add_job(send_fee_reminders, 'cron', hour=9, minute=0)

# Optional: Second reminder at 6 PM for still-unpaid students
scheduler.add_job(send_fee_reminders, 'cron', hour=18, minute=0)
