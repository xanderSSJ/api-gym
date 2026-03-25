from __future__ import annotations

from pydantic import BaseModel, Field


class SQLImportRequest(BaseModel):
    sql: str = Field(min_length=10, max_length=100_000)
    dry_run: bool = False


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


class SQLImportSnapshot(BaseModel):
    users_total: int
    memberships_total: int
    recent_users: list[SQLImportSnapshotUser]


class SQLImportResponse(BaseModel):
    dry_run: bool
    executed_statements: int
    results: list[SQLImportStatementResult]
    snapshot: SQLImportSnapshot
