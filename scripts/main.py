from backend.scheduler import scheduler, send_fee_reminders
import time

print("🚀 CoachingBot Starting...")

# Fire immediately once to test — don't wait for 9AM
print("\n--- Sending reminders now (test run) ---")
send_fee_reminders()

# Start background scheduler
scheduler.start()
print("\n✅ Scheduler running!")
print("⏰ Auto reminders: 9:00 AM and 6:00 PM daily")
print("Press Ctrl+C to stop\n")

try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    scheduler.shutdown()
    print("\n🛑 CoachingBot stopped")
