import sqlite3
import pandas as pd

DB = "coaching.db"

def init_db():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS institutes (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            phone        TEXT NOT NULL,
            batch        TEXT,
            fee_amount   REAL,
            fee_due_date TEXT,
            fee_paid     INTEGER DEFAULT 0,
            institute    TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database ready")

def create_institute(name, username, password):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO institutes (name, username, password) VALUES (?, ?, ?)",
            (name, username, password)
        )
        conn.commit()
        print(f"✅ Institute '{name}' created with username '{username}'")
    except sqlite3.IntegrityError:
        print(f"❌ Username '{username}' already exists")
    conn.close()

def verify_login(username, password):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM institutes WHERE username=? AND password=?",
        (username, password)
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def import_from_excel(filepath, institute_name):
    df = pd.read_excel(filepath)
    df.columns = df.columns.str.strip().str.lower()
    
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE institute=?", (institute_name,))
    
    added = 0
    for _, row in df.iterrows():
        cursor.execute('''
            INSERT INTO students (name, phone, batch, fee_amount, fee_due_date, institute)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            str(row["name"]),
            str(row["phone"]),
            str(row.get("batch", "General")),
            float(row.get("fee_amount", 0)),
            str(row.get("fee_due_date", "10 March 2026")),
            institute_name
        ))
        added += 1
    
    conn.commit()
    conn.close()
    print(f"✅ Imported {added} students from {filepath}")

def get_unpaid_students(institute=None):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    if institute:
        cursor.execute(
            "SELECT name, phone, batch, fee_amount, fee_due_date, institute FROM students WHERE fee_paid=0 AND institute=?",
            (institute,)
        )
    else:
        cursor.execute(
            "SELECT name, phone, batch, fee_amount, fee_due_date, institute FROM students WHERE fee_paid=0"
        )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"name": r[0], "phone": r[1], "batch": r[2],
         "fee_amount": r[3], "fee_due_date": r[4], "institute": r[5]}
        for r in rows
    ]

def get_all_students(institute=None):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    if institute:
        cursor.execute(
            "SELECT name, phone, batch, fee_amount, fee_due_date, institute, fee_paid FROM students WHERE institute=?",
            (institute,)
        )
    else:
        cursor.execute(
            "SELECT name, phone, batch, fee_amount, fee_due_date, institute, fee_paid FROM students"
        )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"name": r[0], "phone": r[1], "batch": r[2],
         "fee_amount": r[3], "fee_due_date": r[4],
         "institute": r[5], "fee_paid": bool(r[6])}
        for r in rows
    ]

def mark_paid(phone):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET fee_paid=1 WHERE phone=?", (phone,))
    conn.commit()
    conn.close()
    print(f"✅ Marked {phone} as paid")

def get_all_institutes():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT name, username FROM institutes")
    rows = cursor.fetchall()
    conn.close()
    return [{"name": r[0], "username": r[1]} for r in rows]

def mark_unpaid(phone):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET fee_paid=0 WHERE phone=?", (phone,))
    conn.commit()
    conn.close()
    print(f"↩️ Marked {phone} as unpaid")
