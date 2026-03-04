from database import init_db, create_institute

init_db()

# ── Add new institute here ──
create_institute(
    name     = "Shree Coaching Centre",
    username = "shree123",
    password = "shree@2026"
)

# Add more institutes as you onboard them:
# create_institute("Sunrise Classes", "sunrise456", "sunrise@2026")
# create_institute("Bright Future", "bright789", "bright@2026")
