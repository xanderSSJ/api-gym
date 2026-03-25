from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import bad_request, forbidden
from app.db.models.membership import UserMembership
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.admin_import import (
    SQLImportRequest,
    SQLImportResponse,
    SQLImportSnapshot,
    SQLImportSnapshotUser,
    SQLImportStatementResult,
)

router = APIRouter(prefix="/admin", tags=["admin"])

MAX_STATEMENTS_PER_IMPORT = 100
ALLOWED_TABLES = {
    "users",
    "user_memberships",
    "user_physical_profiles",
    "user_training_preferences",
    "user_nutrition_preferences",
    "user_safety_profiles",
}
FORBIDDEN_KEYWORDS = {
    "DROP",
    "DELETE",
    "TRUNCATE",
    "ALTER",
    "CREATE",
    "GRANT",
    "REVOKE",
    "COPY",
    "CALL",
    "DO",
}


def _normalize_table_name(raw: str) -> str:
    cleaned = raw.replace('"', "").strip().lower()
    if "." in cleaned:
        cleaned = cleaned.split(".")[-1]
    return cleaned


def _split_sql_statements(script: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    in_single = False
    in_double = False

    for char in script:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        if char == ";" and not in_single and not in_double:
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            continue
        buffer.append(char)

    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def _validate_sql_statement(statement: str) -> tuple[str, str]:
    cleaned = statement.strip()
    if not cleaned:
        raise bad_request("Empty SQL statement is not allowed.")

    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise bad_request("SQL comments are not allowed in import endpoint.")

    upper = cleaned.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            raise forbidden(f"Keyword '{keyword}' is not allowed in SQL import endpoint.")

    insert_match = re.match(r'^\s*INSERT\s+INTO\s+("?[\w\.]+"?)', cleaned, flags=re.IGNORECASE)
    if insert_match:
        table = _normalize_table_name(insert_match.group(1))
        if table not in ALLOWED_TABLES:
            raise forbidden(f"Table '{table}' is not allowed.")
        return "INSERT", table

    update_match = re.match(r'^\s*UPDATE\s+("?[\w\.]+"?)', cleaned, flags=re.IGNORECASE)
    if update_match:
        table = _normalize_table_name(update_match.group(1))
        if table not in ALLOWED_TABLES:
            raise forbidden(f"Table '{table}' is not allowed.")
        return "UPDATE", table

    raise bad_request("Only INSERT and UPDATE statements are allowed.")


def _require_sql_import_enabled() -> None:
    if not settings.enable_sql_import_endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SQL import endpoint is disabled. Set ENABLE_SQL_IMPORT_ENDPOINT=true.",
        )


def _require_admin_key(admin_key: str | None) -> None:
    expected = settings.admin_import_key.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_IMPORT_KEY is not configured.",
        )
    if admin_key != expected:
        raise forbidden("Invalid admin import key.")


async def _build_snapshot(session: AsyncSession) -> SQLImportSnapshot:
    users_total = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    memberships_total = (await session.execute(select(func.count()).select_from(UserMembership))).scalar_one()
    recent_users_rows = (
        await session.execute(select(User).order_by(User.created_at.desc()).limit(20))
    ).scalars()
    recent_users = [
        SQLImportSnapshotUser(user_id=user.id, full_name=user.full_name, email=user.email, phone=user.phone)
        for user in recent_users_rows
    ]
    return SQLImportSnapshot(
        users_total=int(users_total),
        memberships_total=int(memberships_total),
        recent_users=recent_users,
    )


@router.put("/sql-import", response_model=SQLImportResponse)
async def sql_import(
    payload: SQLImportRequest,
    session: AsyncSession = Depends(get_db_session),
    x_admin_import_key: str | None = Header(default=None),
) -> SQLImportResponse:
    _require_sql_import_enabled()
    _require_admin_key(x_admin_import_key)

    statements = _split_sql_statements(payload.sql)
    if not statements:
        raise bad_request("No SQL statements found.")
    if len(statements) > MAX_STATEMENTS_PER_IMPORT:
        raise bad_request(f"Too many statements. Max allowed: {MAX_STATEMENTS_PER_IMPORT}.")

    results: list[SQLImportStatementResult] = []
    for index, statement in enumerate(statements, start=1):
        command, table = _validate_sql_statement(statement)
        if not payload.dry_run:
            try:
                result = await session.execute(text(statement))
            except Exception as exc:
                await session.rollback()
                raise bad_request(f"SQL import failed at statement {index}: {exc}") from exc
            rowcount = int(result.rowcount or 0)
        else:
            rowcount = None
        results.append(
            SQLImportStatementResult(
                statement_no=index,
                command=command,
                table=table,
                rowcount=rowcount,
            )
        )

    if payload.dry_run:
        await session.rollback()
    else:
        await session.commit()

    snapshot = await _build_snapshot(session)
    return SQLImportResponse(
        dry_run=payload.dry_run,
        executed_statements=len(results),
        results=results,
        snapshot=snapshot,
    )
