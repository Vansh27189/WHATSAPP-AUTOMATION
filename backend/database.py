from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import DEFAULT_PAGE_SIZE, INDIA_COUNTRY_CODE, MAX_PAGE_SIZE, SEARCH_MAX_LENGTH
from backend.db import SessionLocal
from backend.models import Institute, SchedulerJob, Student, TokenBlocklist

PBKDF2_ITERATIONS = 210_000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def verify_password(password: str, stored_password: str) -> bool:
    if not stored_password:
        return False
    if not stored_password.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(password, stored_password)

    try:
        _, iterations_str, salt_b64, hash_b64 = stored_password.split("$", 3)
        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (TypeError, ValueError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def sanitize_search(search: str) -> str:
    return search.strip()[:SEARCH_MAX_LENGTH]


def normalize_phone(raw_phone: object) -> str:
    cleaned = "".join(ch for ch in str(raw_phone).strip() if ch.isdigit())
    if not cleaned:
        raise ValueError("Phone cannot be empty")
    if not 10 <= len(cleaned) <= 15:
        raise ValueError("Phone must contain 10 to 15 digits after removing separators")

    normalized = cleaned if cleaned.startswith(INDIA_COUNTRY_CODE) else f"{INDIA_COUNTRY_CODE}{cleaned}"
    if not 10 <= len(normalized) <= 15:
        raise ValueError("Phone must be a valid 10 to 15 digit number after country code normalization")
    return normalized


async def get_session() -> AsyncSession:
    return SessionLocal()


async def init_db() -> None:
    return None


async def get_institute_by_name(session: AsyncSession, institute_name: str) -> Optional[Institute]:
    result = await session.execute(select(Institute).where(Institute.name == institute_name.strip()))
    return result.scalar_one_or_none()


async def get_institute_by_username(session: AsyncSession, username: str) -> Optional[Institute]:
    result = await session.execute(select(Institute).where(Institute.username == username.strip()))
    return result.scalar_one_or_none()


async def create_institute(name: str, username: str, password: str) -> bool:
    async with SessionLocal() as session:
        institute = Institute(name=name.strip(), username=username.strip(), password=_hash_password(password))
        session.add(institute)
        try:
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


async def verify_login(username: str, password: str) -> Optional[str]:
    async with SessionLocal() as session:
        institute = await get_institute_by_username(session, username)
        if not institute:
            return None
        if verify_password(password, institute.password):
            if not institute.password.startswith("pbkdf2_sha256$"):
                institute.password = _hash_password(password)
                await session.commit()
            return institute.name
        return None


def _student_payload(student: Student) -> dict[str, Any]:
    return {
        "name": student.name,
        "phone": student.phone,
        "batch": student.batch or "",
        "fee_amount": float(student.fee_amount or 0),
        "fee_due_date": student.fee_due_date or "",
        "institute": student.institute.name if student.institute else "",
        "fee_paid": bool(student.fee_paid),
        "created_at": student.created_at.isoformat() if student.created_at else None,
        "updated_at": student.updated_at.isoformat() if student.updated_at else None,
    }


async def get_all_institutes() -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        result = await session.execute(select(Institute).order_by(Institute.name.asc()))
        institutes = result.scalars().all()
        return [
            {
                "name": institute.name,
                "username": institute.username,
                "created_at": institute.created_at.isoformat() if institute.created_at else None,
                "updated_at": institute.updated_at.isoformat() if institute.updated_at else None,
            }
            for institute in institutes
        ]


async def list_students(
    institute: Optional[str] = None,
    search: str = "",
    fee_status: str = "all",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    safe_search = sanitize_search(search).lower()

    async with SessionLocal() as session:
        query = select(Student).options(selectinload(Student.institute)).join(Institute)
        count_query = select(func.count(Student.id)).join(Institute)

        filters = []
        if institute:
            filters.append(Institute.name == institute)
        if fee_status == "paid":
            filters.append(Student.fee_paid.is_(True))
        elif fee_status == "unpaid":
            filters.append(Student.fee_paid.is_(False))
        if safe_search:
            pattern = f"%{safe_search}%"
            filters.append(
                or_(
                    func.lower(Student.name).like(pattern),
                    Student.phone.like(pattern),
                    func.lower(func.coalesce(Student.batch, "")).like(pattern),
                    func.lower(Institute.name).like(pattern),
                )
            )

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = (await session.execute(count_query)).scalar_one()
        total_pages = max((total + safe_page_size - 1) // safe_page_size, 1)
        rows = await session.execute(
            query.order_by(Student.name.asc()).limit(safe_page_size).offset((safe_page - 1) * safe_page_size)
        )
        students = rows.scalars().all()

        return {
            "students": [_student_payload(student) for student in students],
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
        }


async def get_student(phone: str, institute: str) -> Optional[dict[str, Any]]:
    safe_phone = normalize_phone(phone)
    async with SessionLocal() as session:
        result = await session.execute(
            select(Student)
            .options(selectinload(Student.institute))
            .join(Institute)
            .where(Institute.name == institute, Student.phone == safe_phone)
        )
        student = result.scalar_one_or_none()
        return _student_payload(student) if student else None


async def get_unpaid_students(institute: Optional[str] = None) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        query = (
            select(Student)
            .options(selectinload(Student.institute))
            .join(Institute)
            .where(Student.fee_paid.is_(False))
            .order_by(Student.name.asc())
        )
        if institute:
            query = query.where(Institute.name == institute)
        rows = await session.execute(query)
        return [_student_payload(student) for student in rows.scalars().all()]


async def get_all_students_for_scope(institute: Optional[str] = None) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        query = select(Student).options(selectinload(Student.institute)).join(Institute).order_by(Student.name.asc())
        if institute:
            query = query.where(Institute.name == institute)
        rows = await session.execute(query)
        return [_student_payload(student) for student in rows.scalars().all()]


async def get_dashboard_summary(institute: Optional[str] = None) -> dict[str, Any]:
    async with SessionLocal() as session:
        total_query = select(func.count(Student.id)).join(Institute)
        paid_query = select(func.count(Student.id)).join(Institute).where(Student.fee_paid.is_(True))
        unpaid_query = select(func.count(Student.id)).join(Institute).where(Student.fee_paid.is_(False))
        if institute:
            total_query = total_query.where(Institute.name == institute)
            paid_query = paid_query.where(Institute.name == institute)
            unpaid_query = unpaid_query.where(Institute.name == institute)

        total_students = (await session.execute(total_query)).scalar_one()
        fees_paid = (await session.execute(paid_query)).scalar_one()
        fees_pending = (await session.execute(unpaid_query)).scalar_one()
        institutes = None if institute else (await session.execute(select(func.count(Institute.id)))).scalar_one()

        return {
            "total_students": total_students,
            "fees_paid": fees_paid,
            "fees_pending": fees_pending,
            "institutes": institutes,
        }


async def _resolve_institute(session: AsyncSession, institute_name: str) -> Institute:
    institute = await get_institute_by_name(session, institute_name)
    if not institute:
        raise ValueError("Institute not found")
    return institute


async def mark_paid(phone: str, institute: str) -> int:
    safe_phone = normalize_phone(phone)
    async with SessionLocal() as session:
        inst = await _resolve_institute(session, institute)
        result = await session.execute(
            update(Student)
            .where(Student.institute_id == inst.id, Student.phone == safe_phone)
            .values(fee_paid=True, updated_at=_utcnow())
        )
        await session.commit()
        return result.rowcount or 0


async def mark_unpaid(phone: str, institute: str) -> int:
    safe_phone = normalize_phone(phone)
    async with SessionLocal() as session:
        inst = await _resolve_institute(session, institute)
        result = await session.execute(
            update(Student)
            .where(Student.institute_id == inst.id, Student.phone == safe_phone)
            .values(fee_paid=False, updated_at=_utcnow())
        )
        await session.commit()
        return result.rowcount or 0


def _coerce_fee_amount(value: object) -> float:
    if pd.isna(value):
        return 0.0
    try:
        return float(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("fee_amount must be numeric") from exc


async def import_from_excel(filepath: str, institute_name: str, dry_run: bool = False) -> dict[str, Any]:
    df = pd.read_excel(filepath)
    df.columns = df.columns.str.strip().str.lower()

    required_columns = {"name", "phone"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing_columns))}")

    async with SessionLocal() as session:
        institute = await _resolve_institute(session, institute_name)
        existing_rows = await session.execute(
            select(Student).where(Student.institute_id == institute.id)
        )
        existing_by_phone = {student.phone: student for student in existing_rows.scalars().all()}

        normalized_rows: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        has_errors = False

        for row_number, row in enumerate(df.iterrows(), start=2):
            _, values = row
            try:
                raw_name = values["name"]
                name = "" if pd.isna(raw_name) else str(raw_name).strip()
                if not name:
                    raise ValueError("Student name cannot be empty")
                phone = normalize_phone(values["phone"])
                raw_batch = values.get("batch", "General")
                batch = "General" if pd.isna(raw_batch) else str(raw_batch).strip() or "General"
                fee_amount = _coerce_fee_amount(values.get("fee_amount", 0))
                raw_fee_due_date = values.get("fee_due_date", "")
                fee_due_date = "" if pd.isna(raw_fee_due_date) else str(raw_fee_due_date).strip()
                fee_due_date = fee_due_date or "10 March 2026"
            except ValueError as exc:
                has_errors = True
                results.append({
                    "row": row_number,
                    "status": "error",
                    "message": str(exc),
                })
                continue

            existing = existing_by_phone.get(phone)
            incoming = {
                "name": name,
                "phone": phone,
                "batch": batch,
                "fee_amount": fee_amount,
                "fee_due_date": fee_due_date,
                "institute_id": institute.id,
            }
            if existing is None:
                status = "inserted"
            elif (
                existing.name == name
                and (existing.batch or "General") == batch
                and float(existing.fee_amount or 0) == fee_amount
                and (existing.fee_due_date or "") == fee_due_date
            ):
                status = "skipped"
            else:
                status = "updated"

            results.append({
                "row": row_number,
                "status": status,
                "phone": f"***{phone[-4:]}",
                "name": name,
            })
            normalized_rows.append(incoming | {"status": status})

        if has_errors:
            return {
                "success": False,
                "dry_run": dry_run,
                "institute": institute_name,
                "imported": 0,
                "results": results,
                "counts": _count_results(results),
            }

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "institute": institute_name,
                "imported": sum(1 for row in normalized_rows if row["status"] in {"inserted", "updated"}),
                "results": results,
                "counts": _count_results(results),
            }

        try:
            dialect_name = session.bind.dialect.name if session.bind else "sqlite"
            insert_fn = postgres_insert if dialect_name == "postgresql" else sqlite_insert
            for row in normalized_rows:
                if row["status"] == "skipped":
                    continue
                timestamp = _utcnow()
                values = {
                    "name": row["name"],
                    "phone": row["phone"],
                    "batch": row["batch"],
                    "fee_amount": row["fee_amount"],
                    "fee_due_date": row["fee_due_date"],
                    "institute_id": row["institute_id"],
                    "fee_paid": False,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
                statement = insert_fn(Student).values(**values).on_conflict_do_update(
                    index_elements=["institute_id", "phone"],
                    set_={
                        "name": row["name"],
                        "batch": row["batch"],
                        "fee_amount": row["fee_amount"],
                        "fee_due_date": row["fee_due_date"],
                        "updated_at": timestamp,
                    },
                )
                await session.execute(statement)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        return {
            "success": True,
            "dry_run": False,
            "institute": institute_name,
            "imported": sum(1 for row in normalized_rows if row["status"] in {"inserted", "updated"}),
            "results": results,
            "counts": _count_results(results),
        }


def _count_results(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "error": 0}
    for result in results:
        status = result["status"]
        counts[status] = counts.get(status, 0) + 1
    return counts


async def revoke_token(jti: str, expires_at: datetime) -> None:
    if not jti:
        return
    async with SessionLocal() as session:
        await session.merge(TokenBlocklist(jti=jti, expires_at=expires_at))
        await session.commit()


async def is_token_revoked(jti: str) -> bool:
    if not jti:
        return False
    async with SessionLocal() as session:
        result = await session.execute(select(TokenBlocklist).where(TokenBlocklist.jti == jti))
        return result.scalar_one_or_none() is not None


async def purge_expired_blocklist() -> int:
    async with SessionLocal() as session:
        result = await session.execute(
            TokenBlocklist.__table__.delete().where(TokenBlocklist.expires_at < _utcnow())
        )
        await session.commit()
        return result.rowcount or 0


async def claim_scheduler_run(name: str, next_run: datetime, now: datetime) -> bool:
    async with SessionLocal() as session:
        dialect_name = session.bind.dialect.name if session.bind else "sqlite"
        insert_fn = postgres_insert if dialect_name == "postgresql" else sqlite_insert
        await session.execute(
            insert_fn(SchedulerJob)
            .values(name=name, next_run=None, locked_at=None, updated_at=now)
            .on_conflict_do_nothing(index_elements=["name"])
        )
        result = await session.execute(
            update(SchedulerJob)
            .where(
                SchedulerJob.name == name,
                or_(SchedulerJob.next_run.is_(None), SchedulerJob.next_run <= now),
            )
            .values(next_run=next_run, locked_at=now, updated_at=now)
        )
        await session.commit()
        return (result.rowcount or 0) > 0

