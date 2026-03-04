from scheduler import scheduler, send_fee_reminders
import time

print("🚀 CoachingBot Starting...")

# Test: send reminder RIGHT NOW (don't wait for 9 AM)
print("\n--- Testing fee reminder now ---")
send_fee_reminders()

# Start the scheduler (runs in background)
scheduler.start()
print("\n✅ Scheduler started!")
print("⏰ Fee reminders will auto-run at 9 AM and 6 PM daily")
print("Press Ctrl+C to stop\n")

try:
    while True:
        time.sleep(60)  # Keep the program alive
except KeyboardInterrupt:
    scheduler.shutdown()
    print("\n🛑 CoachingBot stopped")
