from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SQLImportMembershipInput(BaseModel):
    plan_code: str | None = None
    status: str | None = None


class SQLImportUserInput(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    user_status: str | None = None
    email_verified: bool | None = None
    membership: SQLImportMembershipInput | None = None


class SQLImportRequest(BaseModel):
    sql: str | None = Field(default=None, min_length=10, max_length=100_000)
    users: list[SQLImportUserInput] = Field(default_factory=list, max_length=500)
    dry_run: bool = False
    auto_verify_email: bool = True
    default_password: str = Field(default="1234567890", min_length=8, max_length=128)


class SQLImportStatementResult(BaseModel):
    statement_no: int
    command: str
    table: str
    rowcount: int | None = None


class SQLImportSnapshotUser(BaseModel):
    user_id: str
    full_name: str
    email: str
    phone: str | None = None


class SQLImportUserResult(BaseModel):
    email: str
    user_id: str
    action: str
    plan_code: str
    email_verified: bool
    created_at: datetime | None = None


class SQLImportSnapshot(BaseModel):
    users_total: int
    memberships_total: int
    recent_users: list[SQLImportSnapshotUser]


class SQLImportResponse(BaseModel):
    dry_run: bool
    executed_statements: int
    results: list[SQLImportStatementResult]
    imported_users: list[SQLImportUserResult] = Field(default_factory=list)
    snapshot: SQLImportSnapshot
