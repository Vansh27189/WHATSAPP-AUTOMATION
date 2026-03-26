import os
import shutil
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

import backend.database as database
from backend.api.app import app


class FakeResponse:
    def __init__(self, ok: bool = True, status_code: int = 200):
        self.ok = ok
        self.status_code = status_code


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ["ADMIN_PASSWORD"] = "admin123"
        os.environ["APP_SECRET"] = "test-secret"
        cls.temp_dir = Path("tests") / ".tmp_api"
        if cls.temp_dir.exists():
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        cls.temp_dir.mkdir(parents=True, exist_ok=True)
        cls.db_path = str((cls.temp_dir / "test.db").resolve())
        database.DB = cls.db_path
        database.init_db()
        database.create_institute("Alpha Institute", "alpha_user", "alpha_pass")
        database.create_institute("Beta Institute", "beta_user", "beta_pass")
        cls._seed_students()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    @classmethod
    def _seed_students(cls):
        rows = [
            ("Aarav", "911111111111", "JEE", 2500, "10 March 2026", 0, "Alpha Institute"),
            ("Siya", "922222222222", "NEET", 3000, "11 March 2026", 1, "Alpha Institute"),
            ("Kabir", "933333333333", "Boards", 2000, "12 March 2026", 0, "Beta Institute"),
        ]
        with sqlite3.connect(cls.db_path) as connection:
            connection.executemany(
                """
                INSERT INTO students (name, phone, batch, fee_amount, fee_due_date, fee_paid, institute)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.commit()

    def login(self, username: str, password: str) -> str:
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)
        return response.json()["token"]

    def test_admin_login_and_summary(self):
        token = self.login("admin", "admin123")
        response = self.client.get("/api/dashboard/summary", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()["summary"]
        self.assertEqual(payload["total_students"], 3)
        self.assertEqual(payload["institutes"], 2)

    def test_institute_scope_students(self):
        token = self.login("alpha_user", "alpha_pass")
        response = self.client.get("/api/students", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        students = response.json()["students"]
        self.assertEqual(len(students), 2)
        self.assertTrue(all(student["institute"] == "Alpha Institute" for student in students))

    def test_mark_paid_changes_status(self):
        token = self.login("alpha_user", "alpha_pass")
        response = self.client.post(
            "/api/students/911111111111/mark-paid",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        self.assertEqual(response.status_code, 200)
        students = database.get_filtered_students("Alpha Institute", fee_status="paid")
        self.assertTrue(any(student["phone"] == "911111111111" for student in students))

    def test_import_and_send_reminders(self):
        token = self.login("beta_user", "beta_pass")
        xlsx_path = cls_path = self.temp_dir / "beta_import.xlsx"
        pd.DataFrame(
            [
                {"name": "Mira", "phone": "944444444444", "batch": "NEET", "fee_amount": 1900, "fee_due_date": "15 March 2026"},
                {"name": "Rohan", "phone": "955555555555", "batch": "JEE", "fee_amount": 2100, "fee_due_date": "18 March 2026"},
            ]
        ).to_excel(xlsx_path, index=False)

        with cls_path.open("rb") as handle:
            import_response = self.client.post(
                "/api/students/import",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("beta_import.xlsx", handle, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        self.assertEqual(import_response.status_code, 200)
        self.assertEqual(import_response.json()["imported"], 2)

        with patch("backend.api.app.send_template", side_effect=[FakeResponse(True, 200), FakeResponse(False, 500)]):
            reminder_response = self.client.post(
                "/api/messages/reminders/send",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )
        self.assertEqual(reminder_response.status_code, 200)
        payload = reminder_response.json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["success_count"], 1)
        self.assertEqual(payload["failure_count"], 1)


if __name__ == "__main__":
    unittest.main()