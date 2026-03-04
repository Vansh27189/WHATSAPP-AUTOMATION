from database import init_db, import_from_excel, get_all_students

# Step 1: Create database
init_db()

# Step 2: Import Excel
import_from_excel("student_fee_records.xlsx", "Shree Coaching Centre")

# Step 3: Check what was imported
students = get_all_students()
print(f"\n📋 {len(students)} students in database:")
for s in students:
    print(f"  → {s['name']} | {s['phone']} | {s['batch']} | ₹{s['fee_amount']}")
