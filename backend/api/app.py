import asyncio
import os
import time
from contextlib import asynccontextmanager
from tempfile import NamedTemporaryFile
from uuid import uuid4

import sentry_sdk
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.api.schemas import (
    ActionResult,
    AttendanceRequest,
    AuthUser,
    BroadcastRequest,
    DashboardSummaryResponse,
    FeeStatusRequest,
    InstitutesResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    RemindersRequest,
    SendResult,
    StudentsResponse,
)
from backend.api.security import create_token, revoke_serialized_token, require_token
from backend.config import (
    DEFAULT_PAGE_SIZE,
    FRONTEND_ORIGIN,
    MAX_PAGE_SIZE,
    RATE_LIMIT_DEFAULT,
    RATE_LIMIT_LOGIN,
    REQUEST_SIZE_LIMIT_BYTES,
    SENTRY_DSN,
    SENTRY_ENVIRONMENT,
    UPLOAD_SIZE_LIMIT_BYTES,
)
from backend.database import (
    get_all_institutes,
    get_all_students_for_scope,
    get_dashboard_summary,
    get_student,
    get_unpaid_students,
    import_from_excel,
    init_db,
    list_students,
    mark_paid,
    mark_unpaid,
    normalize_phone,
    sanitize_search,
    verify_login,
)
from backend.db import run_migrations
from backend.logging_config import configure_logging, get_logger
from backend.scheduler import purge_blocklist_job, start_scheduler, stop_scheduler
from backend.whatsapp import send_attendance_alert, send_template, send_text

configure_logging()
logger = get_logger("api")
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT_DEFAULT])
ALLOWED_XLSX_MIME_TYPES = {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _redact_sensitive_event(value, key: str | None = None):
    sensitive_keys = {"authorization", "cookie", "password", "refresh_token", "token", "phone"}
    if key and key.lower() in sensitive_keys:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: _redact_sensitive_event(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact_sensitive_event(item) for item in value]
    return value


def _scrub_sentry_event(event, _hint):
    return _redact_sensitive_event(event)


def _json_error(request: Request, status_code: int, content: dict) -> JSONResponse:
    headers = {}
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers["x-request-id"] = request_id
    return JSONResponse(status_code=status_code, content=content, headers=headers)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if SENTRY_DSN:
        sentry_sdk.init(dsn=SENTRY_DSN, environment=SENTRY_ENVIRONMENT, before_send=_scrub_sentry_event)
    await asyncio.to_thread(run_migrations)
    await init_db()
    await purge_blocklist_job()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="CoachingBot API", version="2.0.0", lifespan=lifespan)
app.state.limiter = limiter

allowed_origins = [FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(allowed_origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, _exc: RateLimitExceeded):
    return _json_error(request, 429, {"detail": "Rate limit exceeded", "error": "too_many_requests"})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return _json_error(request, 422, {"detail": exc.errors()})


@app.middleware("http")
async def request_size_limit_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > REQUEST_SIZE_LIMIT_BYTES:
                return _json_error(request, 413, {"detail": "Request body too large"})
        except ValueError:
            pass

    body = await request.body()
    if len(body) > REQUEST_SIZE_LIMIT_BYTES:
        return _json_error(request, 413, {"detail": "Request body too large"})

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive
    return await call_next(request)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        sentry_sdk.capture_exception(exc)
        logger.exception(
            "request_failed",
            request_id=request_id,
            action=f"{request.method} {request.url.path}",
            duration_ms=duration_ms,
            user=getattr(request.state, "username", None),
            institute=getattr(request.state, "institute", None),
        )
        raise

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["x-request-id"] = request_id
    logger.info(
        "request_complete",
        request_id=request_id,
        action=f"{request.method} {request.url.path}",
        duration_ms=duration_ms,
        status_code=response.status_code,
        user=getattr(request.state, "username", None),
        institute=getattr(request.state, "institute", None),
    )
    if response.status_code >= 500:
        sentry_sdk.capture_message(f"5xx response for {request.method} {request.url.path}")
    return response


def _extract_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    return authorization[len(prefix):]


async def current_user(request: Request, authorization: str | None = Header(default=None)) -> AuthUser:
    token = _extract_token(authorization)
    payload = await require_token(token, expected_type="access")
    user = AuthUser(username=payload["username"], role=payload["role"], institute=payload.get("institute"))
    request.state.username = user.username
    request.state.institute = user.institute
    request.state.token_payload = payload
    request.state.access_token = token
    return user


def require_admin(user: AuthUser = Depends(current_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def resolve_institute(user: AuthUser, requested_institute: str | None) -> str | None:
    return requested_institute if user.role == "admin" else user.institute


def resolve_target_institute(user: AuthUser, requested_institute: str | None) -> str:
    if user.role == "admin":
        if not requested_institute:
            raise HTTPException(status_code=400, detail="Institute is required for admin actions")
        return requested_institute
    if not user.institute:
        raise HTTPException(status_code=400, detail="No institute assigned to user")
    return user.institute


def _message_result(student: dict, response) -> dict:
    return {
        "name": student["name"],
        "phone": f"***{str(student['phone'])[-4:]}",
        "status_code": response.status_code,
        "success": bool(response.ok),
    }


async def _issue_tokens(username: str, role: str, institute: str | None) -> LoginResponse:
    user = AuthUser(username=username, role=role, institute=institute)
    token_payload = user.model_dump()
    return LoginResponse(
        token=create_token(token_payload, token_type="access"),
        refresh_token=create_token(token_payload, token_type="refresh"),
        user=user,
    )


@app.get("/")
async def root():
    return {"name": "CoachingBot API", "status": "ok", "frontend": "Run the React app from ./frontend"}


@app.post("/api/auth/login", response_model=LoginResponse)
@limiter.limit(RATE_LIMIT_LOGIN)
async def login(request: Request, payload: LoginRequest):
    admin_username = os.getenv("ADMIN_USERNAME", "")
    admin_password = os.getenv("ADMIN_PASSWORD", "")

    if admin_username and admin_password and payload.username == admin_username and payload.password == admin_password:
        return await _issue_tokens(payload.username, "admin", None)

    institute_name = await verify_login(payload.username, payload.password)
    if not institute_name:
        raise HTTPException(status_code=401, detail="Wrong username or password")
    return await _issue_tokens(payload.username, "institute", institute_name)


@app.post("/api/auth/refresh", response_model=LoginResponse)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def refresh_token(request: Request, payload: RefreshRequest):
    token_payload = await require_token(payload.refresh_token, expected_type="refresh")
    user = AuthUser(
        username=token_payload["username"],
        role=token_payload["role"],
        institute=token_payload.get("institute"),
    )
    return LoginResponse(
        token=create_token(user.model_dump(), token_type="access"),
        refresh_token=payload.refresh_token,
        user=user,
    )


@app.post("/api/auth/logout", response_model=LogoutResponse)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def logout(request: Request, payload: LogoutRequest | None = None, user: AuthUser = Depends(current_user)):
    access_token = getattr(request.state, "access_token", None)
    if access_token:
        await revoke_serialized_token(access_token)
    if payload and payload.refresh_token:
        await revoke_serialized_token(payload.refresh_token)
    return LogoutResponse()


@app.get("/api/auth/me", response_model=AuthUser)
async def auth_me(user: AuthUser = Depends(current_user)):
    return user


@app.get("/api/institutes", response_model=InstitutesResponse)
async def institutes(user: AuthUser = Depends(require_admin)):
    return InstitutesResponse(institutes=await get_all_institutes())


@app.get("/api/students", response_model=StudentsResponse)
async def students(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str = "",
    fee_status: str = "all",
    institute: str | None = None,
    user: AuthUser = Depends(current_user),
):
    scoped_institute = resolve_institute(user, institute)
    result = await list_students(
        institute=scoped_institute,
        search=sanitize_search(search),
        fee_status=fee_status,
        page=page,
        page_size=page_size,
    )
    return StudentsResponse(**result)


@app.get("/api/dashboard/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(institute: str | None = None, user: AuthUser = Depends(current_user)):
    scoped_institute = resolve_institute(user, institute)
    return DashboardSummaryResponse(summary=await get_dashboard_summary(scoped_institute))


@app.post("/api/students/import")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def students_import(
    request: Request,
    file: UploadFile = File(...),
    institute: str | None = Form(default=None),
    dry_run: bool = False,
    user: AuthUser = Depends(current_user),
):
    target_institute = resolve_target_institute(user, institute)
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx") or file.content_type not in ALLOWED_XLSX_MIME_TYPES:
        raise HTTPException(status_code=422, detail="Only .xlsx uploads are allowed")

    file_bytes = await file.read()
    if len(file_bytes) > UPLOAD_SIZE_LIMIT_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Max 5MB")

    temp_path = None
    try:
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name
        result = await import_from_excel(temp_path, target_institute, dry_run=dry_run)
        if not result["success"]:
            return _json_error(request, 422, {"detail": result})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/api/students/{phone}/mark-paid", response_model=ActionResult)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def students_mark_paid(request: Request, phone: str, payload: FeeStatusRequest, user: AuthUser = Depends(current_user)):
    try:
        normalized_phone = normalize_phone(phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    target_institute = resolve_target_institute(user, payload.institute)
    updated = await mark_paid(normalized_phone, target_institute)
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found")
    return ActionResult(success=True, updated=updated, message="Student marked as paid")


@app.post("/api/students/{phone}/mark-unpaid", response_model=ActionResult)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def students_mark_unpaid(request: Request, phone: str, payload: FeeStatusRequest, user: AuthUser = Depends(current_user)):
    try:
        normalized_phone = normalize_phone(phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    target_institute = resolve_target_institute(user, payload.institute)
    updated = await mark_unpaid(normalized_phone, target_institute)
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found")
    return ActionResult(success=True, updated=updated, message="Student marked as unpaid")


@app.post("/api/messages/reminders/send", response_model=SendResult)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def send_reminders(request: Request, payload: RemindersRequest, user: AuthUser = Depends(current_user)):
    target_institute = resolve_target_institute(user, payload.institute)
    students = await get_unpaid_students(target_institute)
    results = []
    for student in students:
        response = send_template(
            to=student["phone"],
            template_name="fees_remainder1",
            params=[student["name"], str(int(student["fee_amount"])), student["batch"], student["fee_due_date"]],
        )
        results.append(_message_result(student, response))
    success_count = sum(1 for result in results if result["success"])
    return SendResult(total=len(results), success_count=success_count, failure_count=len(results) - success_count, results=results)


@app.post("/api/messages/broadcast/send", response_model=SendResult)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def send_broadcast(request: Request, payload: BroadcastRequest, user: AuthUser = Depends(current_user)):
    target_institute = resolve_target_institute(user, payload.institute)
    students = await get_unpaid_students(target_institute) if payload.target == "unpaid" else await get_all_students_for_scope(target_institute)
    results = []
    for student in students:
        response = send_text(student["phone"], payload.message)
        results.append(_message_result(student, response))
    success_count = sum(1 for result in results if result["success"])
    return SendResult(total=len(results), success_count=success_count, failure_count=len(results) - success_count, results=results)


@app.post("/api/messages/attendance/send", response_model=ActionResult)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def send_attendance(request: Request, payload: AttendanceRequest, user: AuthUser = Depends(current_user)):
    try:
        normalized_phone = normalize_phone(payload.phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    target_institute = resolve_target_institute(user, payload.institute)
    student = await get_student(normalized_phone, target_institute)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    response = send_attendance_alert(payload.student_name, normalized_phone, target_institute)
    if not response.ok:
        raise HTTPException(status_code=502, detail="Attendance alert failed")
    return ActionResult(success=True, message="Attendance alert sent")
