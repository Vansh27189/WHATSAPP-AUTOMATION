from typing import Literal, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class LogoutResponse(BaseModel):
    success: bool = True


class AuthUser(BaseModel):
    username: str
    role: Literal["admin", "institute"]
    institute: Optional[str] = None


class LoginResponse(BaseModel):
    token: str
    user: AuthUser
    refresh_token: Optional[str] = None


class StudentsResponse(BaseModel):
    students: list[dict]
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 1


class InstitutesResponse(BaseModel):
    institutes: list[dict]


class DashboardSummaryResponse(BaseModel):
    summary: dict


class FeeStatusRequest(BaseModel):
    institute: Optional[str] = None


class BroadcastRequest(BaseModel):
    message: str = Field(min_length=1)
    target: Literal["all", "unpaid"] = "all"
    institute: Optional[str] = None


class AttendanceRequest(BaseModel):
    phone: str
    student_name: str
    institute: Optional[str] = None


class RemindersRequest(BaseModel):
    institute: Optional[str] = None


class ActionResult(BaseModel):
    success: bool
    updated: Optional[int] = None
    message: str


class SendResult(BaseModel):
    total: int
    success_count: int
    failure_count: int
    results: list[dict]
