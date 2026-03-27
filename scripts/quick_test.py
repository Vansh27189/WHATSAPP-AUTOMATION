import os
import time

from backend.logging_config import configure_logging, get_logger
from backend.whatsapp import send_template

configure_logging()
logger = get_logger("quick_test")

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

    for student in students:
        send_template(
            to=student["phone"],
            template_name="fees_remainder1",
            params=[student["name"], student["fee_amount"], student["batch"], student["fee_due_date"]],
        )
        time.sleep(1)
        logger.info("quick_test_sent", action="quick_test", student=student["name"], recipient=f"***{student['phone'][-4:]}")

    logger.info("quick_test_complete", action="quick_test", total=len(students))
