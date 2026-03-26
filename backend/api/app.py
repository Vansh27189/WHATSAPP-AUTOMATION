import os
from tempfile import NamedTemporaryFile
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

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
    LogoutResponse,
    RemindersRequest,
    SendResult,
    StudentsResponse,
)
from backend.api.security import create_token, decode_token
from backend.database import (
    get_all_institutes,
    get_dashboard_summary,
    get_filtered_students,
    get_student,
    get_unpaid_students,
    import_from_excel,
    init_db,
    mark_paid,
    mark_unpaid,
    verify_login,
)
from backend.whatsapp import send_attendance_alert, send_template, send_text

app = FastAPI(title="CoachingBot API", version="1.0.0")

allowed_origins = [
    os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173"),
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(allowed_origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    return authorization[len(prefix):]


def current_user(authorization: Optional[str] = Header(default=None)) -> AuthUser:
    token = _extract_token(authorization)
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return AuthUser(
        username=payload["username"],
        role=payload["role"],
        institute=payload.get("institute"),
    )


def require_admin(user: AuthUser = Depends(current_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def resolve_institute(user: AuthUser, requested_institute: Optional[str]) -> Optional[str]:
    if user.role == "admin":
        return requested_institute
    return user.institute


def resolve_target_institute(user: AuthUser, requested_institute: Optional[str]) -> str:
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
        "phone": student["phone"],
        "status_code": response.status_code,
        "success": bool(response.ok),
    }


@app.get("/")
def root():
    return {
        "name": "CoachingBot API",
        "status": "ok",
        "frontend": "Run the React app from ./frontend",
    }


@app.post("/api/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    admin_username = os.getenv("ADMIN_USERNAME", "")
    admin_password = os.getenv("ADMIN_PASSWORD", "")

    if (
        admin_username
        and admin_password
        and payload.username == admin_username
        and payload.password == admin_password
    ):
        user = AuthUser(username=payload.username, role="admin", institute=None)
        token = create_token(user.model_dump())
        return LoginResponse(token=token, user=user)

    institute_name = verify_login(payload.username, payload.password)
    if not institute_name:
        raise HTTPException(status_code=401, detail="Wrong username or password")

    user = AuthUser(username=payload.username, role="institute", institute=institute_name)
    token = create_token(user.model_dump())
    return LoginResponse(token=token, user=user)


@app.post("/api/auth/logout", response_model=LogoutResponse)
def logout():
    return LogoutResponse()


@app.get("/api/auth/me", response_model=AuthUser)
def auth_me(user: AuthUser = Depends(current_user)):
    return user


@app.get("/api/institutes", response_model=InstitutesResponse)
def institutes(_: AuthUser = Depends(require_admin)):
    return InstitutesResponse(institutes=get_all_institutes())


@app.get("/api/students", response_model=StudentsResponse)
def students(
    search: str = "",
    fee_status: str = "all",
    institute: Optional[str] = None,
    user: AuthUser = Depends(current_user),
):
    scoped_institute = resolve_institute(user, institute)
    return StudentsResponse(
        students=get_filtered_students(
            institute=scoped_institute,
            search=search,
            fee_status=fee_status,
        )
    )


@app.get("/api/dashboard/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    institute: Optional[str] = None,
    user: AuthUser = Depends(current_user),
):
    scoped_institute = resolve_institute(user, institute)
    return DashboardSummaryResponse(summary=get_dashboard_summary(scoped_institute))


@app.post("/api/students/import")
async def students_import(
    file: UploadFile = File(...),
    institute: Optional[str] = Form(default=None),
    user: AuthUser = Depends(current_user),
):
    target_institute = resolve_target_institute(user, institute)
    temp_path = None

    try:
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
            temp_file.write(await file.read())
            temp_path = temp_file.name

        imported = import_from_excel(temp_path, target_institute)
        return {
            "success": True,
            "imported": imported,
            "institute": target_institute,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/api/students/{phone}/mark-paid", response_model=ActionResult)
def students_mark_paid(
    phone: str,
    payload: FeeStatusRequest,
    user: AuthUser = Depends(current_user),
):
    target_institute = resolve_target_institute(user, payload.institute)
    updated = mark_paid(phone, target_institute)
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found")
    return ActionResult(success=True, updated=updated, message="Student marked as paid")


@app.post("/api/students/{phone}/mark-unpaid", response_model=ActionResult)
def students_mark_unpaid(
    phone: str,
    payload: FeeStatusRequest,
    user: AuthUser = Depends(current_user),
):
    target_institute = resolve_target_institute(user, payload.institute)
    updated = mark_unpaid(phone, target_institute)
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found")
    return ActionResult(success=True, updated=updated, message="Student marked as unpaid")


@app.post("/api/messages/reminders/send", response_model=SendResult)
def send_reminders(
    payload: RemindersRequest,
    user: AuthUser = Depends(current_user),
):
    target_institute = resolve_target_institute(user, payload.institute)
    students = get_unpaid_students(target_institute)
    results = []

    for student in students:
        response = send_template(
            to=student["phone"],
            template_name="fees_remainder1",
            params=[
                student["name"],
                str(int(student["fee_amount"])),
                student["batch"],
                student["fee_due_date"],
            ],
        )
        results.append(_message_result(student, response))

    success_count = sum(1 for result in results if result["success"])
    return SendResult(
        total=len(results),
        success_count=success_count,
        failure_count=len(results) - success_count,
        results=results,
    )


@app.post("/api/messages/broadcast/send", response_model=SendResult)
def send_broadcast(
    payload: BroadcastRequest,
    user: AuthUser = Depends(current_user),
):
    target_institute = resolve_target_institute(user, payload.institute)
    if payload.target == "unpaid":
        students = get_unpaid_students(target_institute)
    else:
        students = get_filtered_students(institute=target_institute)

    results = []
    for student in students:
        response = send_text(student["phone"], payload.message)
        results.append(_message_result(student, response))

    success_count = sum(1 for result in results if result["success"])
    return SendResult(
        total=len(results),
        success_count=success_count,
        failure_count=len(results) - success_count,
        results=results,
    )


@app.post("/api/messages/attendance/send", response_model=ActionResult)
def send_attendance(
    payload: AttendanceRequest,
    user: AuthUser = Depends(current_user),
):
    target_institute = resolve_target_institute(user, payload.institute)
    student = get_student(payload.phone, target_institute)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    response = send_attendance_alert(payload.student_name, payload.phone, target_institute)
    if not response.ok:
        raise HTTPException(status_code=502, detail="Attendance alert failed")
    return ActionResult(success=True, message="Attendance alert sent")