import base64
import hashlib
import hmac
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

import pandas as pd

DB = os.getenv("DB_PATH", "coaching.db")
PBKDF2_ITERATIONS = 210_000


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        "pbkdf2_sha256$"
        f"{PBKDF2_ITERATIONS}$"
        f"{base64.b64encode(salt).decode('utf-8')}$"
        f"{base64.b64encode(digest).decode('utf-8')}"
    )


def _verify_password(password: str, stored_password: str) -> bool:
    if not stored_password:
        return False
    if not stored_password.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(password, stored_password)

    try:
        _, iterations_str, salt_b64, hash_b64 = stored_password.split("$", 3)
        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def _normalize_phone(raw_phone: object) -> str:
    cleaned = "".join(ch for ch in str(raw_phone).strip() if ch.isdigit())
    if not cleaned:
        raise ValueError("Phone cannot be empty")
    return cleaned


def _connect() -> sqlite3.Connection:
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_connect()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS institutes (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    name     TEXT NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    name         TEXT NOT NULL,
                    phone        TEXT NOT NULL,
                    batch        TEXT,
                    fee_amount   REAL,
                    fee_due_date TEXT,
                    fee_paid     INTEGER DEFAULT 0,
                    institute    TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_students_institute_phone
                ON students(institute, phone)
                """
            )
        conn.commit()


def create_institute(name: str, username: str, password: str) -> bool:
    hashed_password = _hash_password(password)
    with closing(_connect()) as conn:
        with closing(conn.cursor()) as cursor:
            try:
                cursor.execute(
                    "INSERT INTO institutes (name, username, password) VALUES (?, ?, ?)",
                    (name.strip(), username.strip(), hashed_password),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False


def verify_login(username: str, password: str) -> Optional[str]:
    with closing(_connect()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(
                "SELECT name, password FROM institutes WHERE username=?",
                (username.strip(),),
            )
            result = cursor.fetchone()
            if not result:
                return None

            institute_name = result["name"]
            stored_password = result["password"]
            if _verify_password(password, stored_password):
                if not stored_password.startswith("pbkdf2_sha256$"):
                    cursor.execute(
                        "UPDATE institutes SET password=? WHERE username=?",
                        (_hash_password(password), username.strip()),
                    )
                    conn.commit()
                return institute_name
            return None


def import_from_excel(filepath: str, institute_name: str) -> int:
    df = pd.read_excel(filepath)
    df.columns = df.columns.str.strip().str.lower()

    required_columns = {"name", "phone"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing_columns))}")

    rows_to_insert = []
    for _, row in df.iterrows():
        name = str(row["name"]).strip()
        if not name:
            raise ValueError("Student name cannot be empty")
        phone = _normalize_phone(row["phone"])
        batch = str(row.get("batch", "General")).strip() or "General"
        fee_amount = float(row.get("fee_amount", 0) or 0)
        fee_due_date = str(row.get("fee_due_date", "")).strip() or "10 March 2026"
        rows_to_insert.append((name, phone, batch, fee_amount, fee_due_date, institute_name))

    with closing(_connect()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("BEGIN")
            cursor.execute("DELETE FROM students WHERE institute=?", (institute_name,))
            cursor.executemany(
                """
                INSERT INTO students (name, phone, batch, fee_amount, fee_due_date, institute)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )
        conn.commit()
    return len(rows_to_insert)


def get_unpaid_students(institute: Optional[str] = None):
    query = """
        SELECT name, phone, batch, fee_amount, fee_due_date, institute, fee_paid
        FROM students
        WHERE fee_paid=0
    """
    params = []
    if institute:
        query += " AND institute=?"
        params.append(institute)

    with closing(_connect()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
    return [dict(row) | {"fee_paid": bool(row["fee_paid"])} for row in rows]


def get_all_students(institute: Optional[str] = None):
    query = """
        SELECT name, phone, batch, fee_amount, fee_due_date, institute, fee_paid
        FROM students
    """
    params = []
    if institute:
        query += " WHERE institute=?"
        params.append(institute)

    with closing(_connect()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
    return [dict(row) | {"fee_paid": bool(row["fee_paid"])} for row in rows]


def get_filtered_students(
    institute: Optional[str] = None,
    search: str = "",
    fee_status: str = "all",
):
    students = get_all_students(institute)
    needle = search.strip().lower()

    if needle:
        students = [
            student
            for student in students
            if needle in student["name"].lower()
            or needle in student["phone"]
            or needle in (student.get("batch") or "").lower()
            or needle in student["institute"].lower()
        ]

    if fee_status == "paid":
        students = [student for student in students if student["fee_paid"]]
    elif fee_status == "unpaid":
        students = [student for student in students if not student["fee_paid"]]

    return students


def get_student(phone: str, institute: str):
    safe_phone = _normalize_phone(phone)
    with closing(_connect()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(
                """
                SELECT name, phone, batch, fee_amount, fee_due_date, institute, fee_paid
                FROM students
                WHERE phone=? AND institute=?
                """,
                (safe_phone, institute),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return dict(row) | {"fee_paid": bool(row["fee_paid"])}


def mark_paid(phone: str, institute: str) -> int:
    safe_phone = _normalize_phone(phone)
    with closing(_connect()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(
                "UPDATE students SET fee_paid=1 WHERE phone=? AND institute=?",
                (safe_phone, institute),
            )
            updated = cursor.rowcount
        conn.commit()
    return updated


def mark_unpaid(phone: str, institute: str) -> int:
    safe_phone = _normalize_phone(phone)
    with closing(_connect()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(
                "UPDATE students SET fee_paid=0 WHERE phone=? AND institute=?",
                (safe_phone, institute),
            )
            updated = cursor.rowcount
        conn.commit()
    return updated


def get_all_institutes():
    with _connect() as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT name, username FROM institutes ORDER BY name ASC")
            rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_dashboard_summary(institute: Optional[str] = None):
    students = get_all_students(institute)
    unpaid = [student for student in students if not student["fee_paid"]]
    return {
        "total_students": len(students),
        "fees_paid": len(students) - len(unpaid),
        "fees_pending": len(unpaid),
        "institutes": len(get_all_institutes()) if institute is None else None,
    }
