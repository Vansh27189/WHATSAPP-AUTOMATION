"""initial schema"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_phone(raw_phone) -> str:
    cleaned = "".join(ch for ch in str(raw_phone or "").strip() if ch.isdigit())
    if not cleaned:
        raise RuntimeError("Legacy student row has an empty phone number")
    if not 10 <= len(cleaned) <= 15:
        raise RuntimeError(f"Legacy phone '{raw_phone}' is invalid after stripping separators")
    normalized = cleaned if cleaned.startswith("91") else f"91{cleaned}"
    if not 10 <= len(normalized) <= 15:
        raise RuntimeError(f"Legacy phone '{raw_phone}' is invalid after country code normalization")
    return normalized


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _create_institutes_table() -> None:
    op.create_table(
        "institutes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username", name="uq_institutes_username"),
    )


def _create_students_table() -> None:
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("batch", sa.String(length=255), nullable=True),
        sa.Column("fee_amount", sa.Float(), nullable=True),
        sa.Column("fee_due_date", sa.String(length=255), nullable=True),
        sa.Column("fee_paid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("institute_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["institute_id"], ["institutes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("institute_id", "phone", name="uq_students_institute_phone"),
    )
    op.create_index("ix_students_institute_id", "students", ["institute_id"])


def _create_support_tables(bind) -> None:
    tables = _table_names(bind)
    if "token_blocklist" not in tables:
        op.create_table(
            "token_blocklist",
            sa.Column("jti", sa.String(length=64), primary_key=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )
        op.create_index("ix_token_blocklist_expires_at", "token_blocklist", ["expires_at"])
    if "scheduler_jobs" not in tables:
        op.create_table(
            "scheduler_jobs",
            sa.Column("name", sa.String(length=100), primary_key=True),
            sa.Column("next_run", sa.DateTime(timezone=True), nullable=True),
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def _upgrade_legacy_institutes(bind) -> None:
    now = _utcnow()
    op.rename_table("institutes", "institutes_legacy")
    _create_institutes_table()
    legacy_rows = bind.execute(
        sa.text("SELECT id, name, username, password FROM institutes_legacy ORDER BY id")
    ).mappings().all()
    if legacy_rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO institutes (id, name, username, password, created_at, updated_at)
                VALUES (:id, :name, :username, :password, :created_at, :updated_at)
                """
            ),
            [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "username": row["username"],
                    "password": row["password"],
                    "created_at": now,
                    "updated_at": now,
                }
                for row in legacy_rows
            ],
        )
    op.drop_table("institutes_legacy")


def _upgrade_legacy_students(bind) -> None:
    now = _utcnow()
    institutes = bind.execute(sa.text("SELECT id, name FROM institutes")).mappings().all()
    institute_ids = {row["name"]: row["id"] for row in institutes}

    op.rename_table("students", "students_legacy")
    _create_students_table()

    legacy_rows = bind.execute(
        sa.text(
            """
            SELECT id, name, phone, batch, fee_amount, fee_due_date, fee_paid, institute
            FROM students_legacy
            ORDER BY id
            """
        )
    ).mappings().all()

    payload_rows = []
    seen_keys = set()
    for row in legacy_rows:
        institute_name = (row["institute"] or "").strip()
        institute_id = institute_ids.get(institute_name)
        if institute_id is None:
            raise RuntimeError(f"Legacy student '{row['name']}' references unknown institute '{institute_name}'")
        normalized_phone = _normalize_phone(row["phone"])
        unique_key = (institute_id, normalized_phone)
        if unique_key in seen_keys:
            raise RuntimeError(
                f"Legacy data contains duplicate phone '{normalized_phone}' for institute '{institute_name}'"
            )
        seen_keys.add(unique_key)
        payload_rows.append(
            {
                "id": row["id"],
                "name": row["name"],
                "phone": normalized_phone,
                "batch": row["batch"],
                "fee_amount": row["fee_amount"],
                "fee_due_date": row["fee_due_date"],
                "fee_paid": bool(row["fee_paid"]),
                "institute_id": institute_id,
                "created_at": now,
                "updated_at": now,
            }
        )

    if payload_rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO students (
                    id, name, phone, batch, fee_amount, fee_due_date, fee_paid,
                    institute_id, created_at, updated_at
                )
                VALUES (
                    :id, :name, :phone, :batch, :fee_amount, :fee_due_date, :fee_paid,
                    :institute_id, :created_at, :updated_at
                )
                """
            ),
            payload_rows,
        )
    op.drop_table("students_legacy")


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "institutes" not in tables:
        _create_institutes_table()
    elif not {"created_at", "updated_at"}.issubset(_column_names(bind, "institutes")):
        _upgrade_legacy_institutes(bind)

    tables = _table_names(bind)
    if "students" not in tables:
        _create_students_table()
    else:
        student_columns = _column_names(bind, "students")
        if "institute_id" not in student_columns or "created_at" not in student_columns or "updated_at" not in student_columns:
            _upgrade_legacy_students(bind)

    _create_support_tables(bind)


def downgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "scheduler_jobs" in tables:
        op.drop_table("scheduler_jobs")
    tables = _table_names(bind)
    if "token_blocklist" in tables:
        if "ix_token_blocklist_expires_at" in {index["name"] for index in sa.inspect(bind).get_indexes("token_blocklist")}:
            op.drop_index("ix_token_blocklist_expires_at", table_name="token_blocklist")
        op.drop_table("token_blocklist")

    tables = _table_names(bind)
    if "students" in tables:
        op.rename_table("students", "students_new")
        op.create_table(
            "students",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("phone", sa.Text(), nullable=False),
            sa.Column("batch", sa.Text(), nullable=True),
            sa.Column("fee_amount", sa.Float(), nullable=True),
            sa.Column("fee_due_date", sa.Text(), nullable=True),
            sa.Column("fee_paid", sa.Integer(), nullable=True, server_default=sa.text("0")),
            sa.Column("institute", sa.Text(), nullable=True),
        )
        rows = bind.execute(
            sa.text(
                """
                SELECT s.id, s.name, s.phone, s.batch, s.fee_amount, s.fee_due_date, s.fee_paid, i.name AS institute
                FROM students_new s
                JOIN institutes i ON i.id = s.institute_id
                ORDER BY s.id
                """
            )
        ).mappings().all()
        if rows:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO students (id, name, phone, batch, fee_amount, fee_due_date, fee_paid, institute)
                    VALUES (:id, :name, :phone, :batch, :fee_amount, :fee_due_date, :fee_paid, :institute)
                    """
                ),
                [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "phone": row["phone"],
                        "batch": row["batch"],
                        "fee_amount": row["fee_amount"],
                        "fee_due_date": row["fee_due_date"],
                        "fee_paid": int(bool(row["fee_paid"])),
                        "institute": row["institute"],
                    }
                    for row in rows
                ],
            )
        if "ix_students_institute_id" in {index["name"] for index in sa.inspect(bind).get_indexes("students_new")}:
            op.drop_index("ix_students_institute_id", table_name="students_new")
        op.drop_table("students_new")

    tables = _table_names(bind)
    if "institutes" in tables:
        op.rename_table("institutes", "institutes_new")
        op.create_table(
            "institutes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("username", sa.Text(), nullable=False, unique=True),
            sa.Column("password", sa.Text(), nullable=False),
        )
        rows = bind.execute(
            sa.text("SELECT id, name, username, password FROM institutes_new ORDER BY id")
        ).mappings().all()
        if rows:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO institutes (id, name, username, password)
                    VALUES (:id, :name, :username, :password)
                    """
                ),
                rows,
            )
        op.drop_table("institutes_new")
