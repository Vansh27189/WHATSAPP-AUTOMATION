import asyncio
import inspect
import io
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pandas as pd
from fastapi.testclient import TestClient

TEST_DIR = Path("tests") / ".tmp_api"
TEST_DIR.mkdir(parents=True, exist_ok=True)
TEST_DB = (TEST_DIR / "test.db").resolve()

os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123"
os.environ["APP_SECRET"] = "test-secret"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB.as_posix()}"
os.environ["DB_PATH"] = str(TEST_DB)
os.environ["SENTRY_DSN"] = ""

import backend.database as database
from backend.api.app import app
from backend.config import REQUEST_SIZE_LIMIT_BYTES, UPLOAD_SIZE_LIMIT_BYTES
from backend.db import SessionLocal
from backend.models import Student


class FakeResponse:
    def __init__(self, ok: bool = True, status_code: int = 200):
        self.ok = ok
        self.status_code = status_code


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if TEST_DIR.exists():
            shutil.rmtree(TEST_DIR, ignore_errors=True)
        TEST_DIR.mkdir(parents=True, exist_ok=True)
        cls.client_ctx = TestClient(app)
        cls.client = cls.client_ctx.__enter__()
        asyncio.run(database.create_institute("Alpha Institute", "alpha_user", "alpha_pass"))
        asyncio.run(database.create_institute("Beta Institute", "beta_user", "beta_pass"))
        asyncio.run(cls._seed_students())

    @classmethod
    def tearDownClass(cls):
        cls.client_ctx.__exit__(None, None, None)
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    @classmethod
    async def _seed_students(cls):
        async with SessionLocal() as session:
            alpha = await database.get_institute_by_name(session, "Alpha Institute")
            beta = await database.get_institute_by_name(session, "Beta Institute")
            for index in range(1, 61):
                session.add(
                    Student(
                        name=f"Alpha Student {index}",
                        phone=f"91{9000000000 + index}",
                        batch="JEE",
                        fee_amount=2000 + index,
                        fee_due_date="10 March 2026",
                        fee_paid=index % 3 == 0,
                        institute_id=alpha.id,
                    )
                )
            session.add(
                Student(
                    name="Beta Student 1",
                    phone="919888888888",
                    batch="NEET",
                    fee_amount=3000,
                    fee_due_date="11 March 2026",
                    fee_paid=False,
                    institute_id=beta.id,
                )
            )
            await session.commit()

    def setUp(self):
        storage = getattr(app.state.limiter, "_storage", None)
        if storage and hasattr(storage, "reset"):
            result = storage.reset()
            if inspect.isawaitable(result):
                asyncio.run(result)

    def login(self, username: str, password: str) -> dict:
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def auth_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def create_institute_login(self, prefix: str) -> dict:
        suffix = uuid4().hex[:8]
        name = f"{prefix} Institute {suffix}"
        username = f"{prefix.lower()}_{suffix}"
        password = f"{prefix.lower()}_pass"
        created = asyncio.run(database.create_institute(name, username, password))
        self.assertTrue(created)
        payload = self.login(username, password)
        return {"name": name, "username": username, "password": password, "auth": payload}

    @staticmethod
    def excel_bytes(rows: list[dict]) -> bytes:
        buffer = io.BytesIO()
        pd.DataFrame(rows).to_excel(buffer, index=False)
        return buffer.getvalue()

    @staticmethod
    async def add_student(name: str, phone: str, institute_name: str, **kwargs):
        async with SessionLocal() as session:
            institute = await database.get_institute_by_name(session, institute_name)
            session.add(
                Student(
                    name=name,
                    phone=phone,
                    batch=kwargs.get("batch", "General"),
                    fee_amount=kwargs.get("fee_amount", 1000),
                    fee_due_date=kwargs.get("fee_due_date", "10 March 2026"),
                    fee_paid=kwargs.get("fee_paid", False),
                    institute_id=institute.id,
                )
            )
            await session.commit()

    def test_admin_login_and_refresh_token_present(self):
        payload = self.login("admin", "admin123")
        self.assertIn("refresh_token", payload)
        summary = self.client.get("/api/dashboard/summary", headers=self.auth_headers(payload["token"]))
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["summary"]["institutes"], 2)

    def test_logout_revokes_access_and_refresh_tokens(self):
        payload = self.login("alpha_user", "alpha_pass")
        me_before = self.client.get("/api/auth/me", headers=self.auth_headers(payload["token"]))
        self.assertEqual(me_before.status_code, 200)

        logout = self.client.post(
            "/api/auth/logout",
            headers=self.auth_headers(payload["token"]),
            json={"refresh_token": payload["refresh_token"]},
        )
        self.assertEqual(logout.status_code, 200)

        me_after = self.client.get("/api/auth/me", headers=self.auth_headers(payload["token"]))
        self.assertEqual(me_after.status_code, 401)

        refresh = self.client.post("/api/auth/refresh", json={"refresh_token": payload["refresh_token"]})
        self.assertEqual(refresh.status_code, 401)

    def test_refresh_returns_new_access_token(self):
        payload = self.login("alpha_user", "alpha_pass")
        refreshed = self.client.post("/api/auth/refresh", json={"refresh_token": payload["refresh_token"]})
        self.assertEqual(refreshed.status_code, 200)
        body = refreshed.json()
        self.assertNotEqual(body["token"], payload["token"])
        self.assertEqual(body["user"]["username"], "alpha_user")
        me = self.client.get("/api/auth/me", headers=self.auth_headers(body["token"]))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["institute"], "Alpha Institute")

    def test_students_pagination(self):
        payload = self.login("admin", "admin123")
        response = self.client.get(
            "/api/students?page=2&page_size=25&search=Alpha",
            headers=self.auth_headers(payload["token"]),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["page_size"], 25)
        self.assertEqual(body["total"], 60)
        self.assertEqual(len(body["students"]), 25)
        self.assertEqual(body["total_pages"], 3)

    def test_import_dry_run_does_not_commit(self):
        payload = self.login("beta_user", "beta_pass")
        xlsx_path = TEST_DIR / "beta_preview.xlsx"
        pd.DataFrame(
            [
                {"name": "Beta Student 1", "phone": "9888888888", "batch": "NEET", "fee_amount": 3000, "fee_due_date": "11 March 2026"},
                {"name": "Beta Student 2", "phone": "9777777777", "batch": "NEET", "fee_amount": 3200, "fee_due_date": "12 March 2026"},
            ]
        ).to_excel(xlsx_path, index=False)

        with xlsx_path.open("rb") as handle:
            preview = self.client.post(
                "/api/students/import?dry_run=true",
                headers=self.auth_headers(payload["token"]),
                files={"file": ("beta_preview.xlsx", handle, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        self.assertEqual(preview.status_code, 200)
        body = preview.json()
        self.assertTrue(body["dry_run"])
        self.assertEqual(body["counts"]["inserted"], 1)
        self.assertEqual(body["counts"]["skipped"], 1)

        students = self.client.get("/api/students", headers=self.auth_headers(payload["token"]))
        self.assertEqual(students.status_code, 200)
        self.assertEqual(students.json()["total"], 1)

    def test_import_upsert_updates_and_inserts_without_deleting_existing_rows(self):
        created = self.create_institute_login("Gamma")
        asyncio.run(
            self.add_student(
                name="Gamma Student 1",
                phone="919811111111",
                institute_name=created["name"],
                batch="Morning",
                fee_amount=1500,
                fee_due_date="10 March 2026",
            )
        )

        workbook = self.excel_bytes(
            [
                {"name": "Gamma Student 1", "phone": "9811111111", "batch": "Evening", "fee_amount": 1800, "fee_due_date": "15 March 2026"},
                {"name": "Gamma Student 2", "phone": "9822222222", "batch": "Weekend", "fee_amount": 2100, "fee_due_date": "16 March 2026"},
            ]
        )
        response = self.client.post(
            "/api/students/import",
            headers=self.auth_headers(created["auth"]["token"]),
            files={"file": ("gamma.xlsx", io.BytesIO(workbook), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["counts"]["updated"], 1)
        self.assertEqual(body["counts"]["inserted"], 1)

        students = self.client.get("/api/students?search=Gamma", headers=self.auth_headers(created["auth"]["token"]))
        self.assertEqual(students.status_code, 200)
        payload = students.json()
        self.assertEqual(payload["total"], 2)
        updated_row = next(student for student in payload["students"] if student["name"] == "Gamma Student 1")
        self.assertEqual(updated_row["batch"], "Evening")
        self.assertEqual(updated_row["fee_amount"], 1800)

    def test_import_error_rolls_back_without_wiping_existing_rows(self):
        created = self.create_institute_login("Delta")
        asyncio.run(
            self.add_student(
                name="Delta Student 1",
                phone="919833333333",
                institute_name=created["name"],
                batch="NEET",
                fee_amount=2000,
                fee_due_date="10 March 2026",
            )
        )

        workbook = self.excel_bytes(
            [
                {"name": "Delta Student 1", "phone": "9833333333", "batch": "NEET", "fee_amount": 2200, "fee_due_date": "11 March 2026"},
                {"name": "Delta Student 2", "phone": "9844444444", "batch": "NEET", "fee_amount": "oops", "fee_due_date": "12 March 2026"},
            ]
        )
        response = self.client.post(
            "/api/students/import",
            headers=self.auth_headers(created["auth"]["token"]),
            files={"file": ("delta.xlsx", io.BytesIO(workbook), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertFalse(detail["success"])
        self.assertEqual(detail["counts"]["error"], 1)

        students = self.client.get("/api/students?search=Delta", headers=self.auth_headers(created["auth"]["token"]))
        self.assertEqual(students.status_code, 200)
        payload = students.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["students"][0]["fee_amount"], 2000)

    def test_import_rejects_invalid_mimetype(self):
        payload = self.login("alpha_user", "alpha_pass")
        response = self.client.post(
            "/api/students/import",
            headers=self.auth_headers(payload["token"]),
            files={"file": ("students.txt", io.BytesIO(b"not-an-excel-file"), "text/plain")},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Only .xlsx uploads are allowed")

    def test_import_rejects_files_over_five_mb(self):
        payload = self.login("alpha_user", "alpha_pass")
        response = self.client.post(
            "/api/students/import",
            headers=self.auth_headers(payload["token"]),
            files={
                "file": (
                    "oversized.xlsx",
                    io.BytesIO(b"x" * (UPLOAD_SIZE_LIMIT_BYTES + 1)),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"], "File too large. Max 5MB")

    def test_phone_validation_on_mark_paid(self):
        payload = self.login("alpha_user", "alpha_pass")
        response = self.client.post(
            "/api/students/123/mark-paid",
            headers=self.auth_headers(payload["token"]),
            json={},
        )
        self.assertEqual(response.status_code, 422)

    def test_reminders_partial_failures(self):
        payload = self.login("beta_user", "beta_pass")
        with patch("backend.api.app.send_template", side_effect=[FakeResponse(True, 200)]):
            reminder_response = self.client.post(
                "/api/messages/reminders/send",
                headers=self.auth_headers(payload["token"]),
                json={},
            )
        self.assertEqual(reminder_response.status_code, 200)
        body = reminder_response.json()
        self.assertEqual(body["success_count"], 1)
        self.assertEqual(body["failure_count"], 0)

    def test_login_rate_limit_returns_json_429(self):
        for _ in range(10):
            response = self.client.post("/api/auth/login", json={"username": "wrong", "password": "wrong"})
            self.assertIn(response.status_code, {401, 429})
        limited = self.client.post("/api/auth/login", json={"username": "wrong", "password": "wrong"})
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.json()["error"], "too_many_requests")

    def test_request_size_limit_returns_413(self):
        response = self.client.post(
            "/api/auth/login",
            data="x" * (REQUEST_SIZE_LIMIT_BYTES + 1),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"], "Request body too large")


if __name__ == "__main__":
    unittest.main()