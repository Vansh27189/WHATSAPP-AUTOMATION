from backend.database import init_db, create_institute
import os

init_db()

name = os.getenv("NEW_INSTITUTE_NAME")
username = os.getenv("NEW_INSTITUTE_USERNAME")
password = os.getenv("NEW_INSTITUTE_PASSWORD")

if name and username and password:
    create_institute(name=name, username=username, password=password)
else:
    print("Set NEW_INSTITUTE_NAME, NEW_INSTITUTE_USERNAME, and NEW_INSTITUTE_PASSWORD to create an institute.")

# Add more institutes as you onboard them:
# create_institute("Sunrise Classes", "sunrise456", "sunrise@2026")
# create_institute("Bright Future", "bright789", "bright@2026")
