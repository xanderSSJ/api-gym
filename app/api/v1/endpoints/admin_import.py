from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import bad_request, forbidden
from app.core.security import get_password_hash
from app.db.models.enums import MembershipStatus, UserStatus
from app.db.models.membership import UserMembership
from app.db.models.user import (
    User,
    UserNutritionPreference,
    UserPhysicalProfile,
    UserSafetyProfile,
    UserTrainingPreference,
)
from app.db.session import get_db_session
from app.schemas.admin_import import (
    SQLImportFormatResponse,
    SQLImportDeleteRequest,
    SQLImportDeleteResponse,
    SQLImportRequest,
    SQLImportResponse,
    SQLImportSnapshot,
    SQLImportUserResult,
    SQLImportSnapshotUser,
    SQLImportStatementResult,
)
from app.services.membership_service import (
    create_or_replace_membership,
    replace_with_free_membership,
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
    if not settings.admin_import_require_key:
        return

    expected = settings.admin_import_key.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_IMPORT_KEY is not configured.",
        )
    provided = (admin_key or "").strip()
    if not provided:
        raise forbidden("Missing admin import key.")
    if not secrets.compare_digest(provided, expected):
        raise forbidden("Invalid admin import key.")


def _resolve_admin_import_key(
    *,
    header_key: str | None,
    body_key: str | None,
    query_key: str | None,
) -> str | None:
    for candidate in (header_key, body_key, query_key):
        if candidate and candidate.strip():
            return candidate.strip()
    return None


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


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise bad_request(f"Invalid email: '{email}'.")
    return normalized


def _normalize_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    value = phone.strip()
    return value or None


def _sql_import_format_payload() -> SQLImportFormatResponse:
    return SQLImportFormatResponse(
        endpoint="/v1/admin/sql-import",
        description="Plantilla de formatos para importar/editar/borrar usuarios por Postman.",
        methods=["GET", "POST", "PUT", "DELETE"],
        allowed_tables=sorted(ALLOWED_TABLES),
        users_payload_example={
            "dry_run": False,
            "auto_verify_email": True,
            "default_password": "1234567890",
            "users": [
                {
                    "full_name": "Alumno Demo",
                    "email": "alumno_demo@example.com",
                    "phone": "5551234567",
                    "membership": {"plan_code": "free"},
                }
            ],
        },
        delete_payload_example={
            "email": "alumno_demo@example.com",
            "hard_delete": False,
            "dry_run": False,
        },
        sql_payload_example={
            "dry_run": False,
            "sql": "UPDATE users SET full_name='Alumno Demo Editado' WHERE email='alumno_demo@example.com';",
        },
        db_json_snapshot_endpoint="/v1/demo?response=json&feature=sql",
        db_json_snapshot_note=(
            "Ese endpoint devuelve el snapshot JSON de la base de datos (usuarios, membresias, rutinas y nutricion)."
        ),
    )


def _db_schema_payload() -> dict[str, Any]:
    return {
        "feature": "db_schema",
        "description": "Formato general de tablas principales para importacion/consulta en este proyecto.",
        "tables": {
            "users": {
                "pk": "id (uuid)",
                "fields": {
                    "full_name": "string",
                    "email": "string (unique)",
                    "phone": "string|null",
                    "status": "active|suspended|deleted",
                    "email_verified_at": "datetime|null",
                },
            },
            "user_memberships": {
                "pk": "id (uuid)",
                "fk": {"user_id": "users.id", "plan_id": "membership_plans.id"},
                "fields": {
                    "status": "active|pending_payment|past_due|suspended|canceled",
                    "starts_at": "datetime",
                    "ends_at": "datetime",
                    "provider": "string",
                    "auto_renew": "boolean",
                },
            },
            "training_plans": {
                "pk": "id (uuid)",
                "fk": {"user_id": "users.id"},
                "fields": {
                    "name": "string",
                    "goal": "enum",
                    "level": "enum",
                    "weeks": "integer",
                    "is_current": "boolean",
                },
            },
            "nutrition_plans": {
                "pk": "id (uuid)",
                "fk": {"user_id": "users.id"},
                "fields": {
                    "name": "string",
                    "goal": "enum",
                    "days_count": "integer",
                    "target_calories": "integer",
                    "is_current": "boolean",
                },
            },
        },
        "tip": "Para ver datos reales en JSON usa /v1/demo?response=json&feature=sql",
    }


async def _get_user_for_delete(session: AsyncSession, payload: SQLImportDeleteRequest) -> User:
    if not payload.user_id and not payload.email:
        raise bad_request("Provide user_id or email for delete operation.")

    if payload.user_id:
        user = (await session.execute(select(User).where(User.id == payload.user_id).limit(1))).scalar_one_or_none()
        if user:
            return user

    if payload.email:
        normalized_email = _normalize_email(payload.email)
        user = (await session.execute(select(User).where(User.email == normalized_email).limit(1))).scalar_one_or_none()
        if user:
            return user

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")


def _parse_user_status(raw_status: str | None) -> UserStatus:
    if raw_status is None:
        return UserStatus.ACTIVE
    normalized = raw_status.strip().lower()
    if normalized not in {status.value for status in UserStatus}:
        raise bad_request(f"Invalid user_status '{raw_status}'. Allowed: active, suspended, deleted.")
    return UserStatus(normalized)


async def _ensure_profiles_for_user(session: AsyncSession, user_id: str) -> None:
    if (await session.execute(select(UserPhysicalProfile).where(UserPhysicalProfile.user_id == user_id))).scalar_one_or_none() is None:
        session.add(UserPhysicalProfile(user_id=user_id))
    if (await session.execute(select(UserTrainingPreference).where(UserTrainingPreference.user_id == user_id))).scalar_one_or_none() is None:
        session.add(UserTrainingPreference(user_id=user_id))
    if (await session.execute(select(UserNutritionPreference).where(UserNutritionPreference.user_id == user_id))).scalar_one_or_none() is None:
        session.add(UserNutritionPreference(user_id=user_id))
    if (await session.execute(select(UserSafetyProfile).where(UserSafetyProfile.user_id == user_id))).scalar_one_or_none() is None:
        session.add(UserSafetyProfile(user_id=user_id))
    await session.flush()


async def _import_users_payload(
    session: AsyncSession,
    payload: SQLImportRequest,
    start_statement_no: int,
) -> tuple[list[SQLImportStatementResult], list[SQLImportUserResult]]:
    now = datetime.now(UTC)
    statement_no = start_statement_no
    statement_results: list[SQLImportStatementResult] = []
    imported_users: list[SQLImportUserResult] = []

    for item in payload.users:
        email = _normalize_email(item.email)
        full_name = (item.full_name or email.split("@")[0]).strip()
        phone = _normalize_phone(item.phone)
        preferred_password = (item.password or payload.default_password).strip()
        if len(preferred_password) < 8:
            raise bad_request("Password must contain at least 8 characters.")
        requested_status = _parse_user_status(item.user_status)

        existing = (await session.execute(select(User).where(User.email == email).limit(1))).scalar_one_or_none()
        if existing is None:
            user = User(
                full_name=full_name,
                email=email,
                phone=phone,
                password_hash=get_password_hash(preferred_password),
                status=requested_status,
                email_verified_at=now if (payload.auto_verify_email or item.email_verified is True) else None,
            )
            session.add(user)
            await session.flush()
            await _ensure_profiles_for_user(session, user.id)
            action = "created"
        else:
            user = existing
            user.full_name = full_name
            user.phone = phone
            user.status = requested_status
            if item.password:
                user.password_hash = get_password_hash(item.password.strip())
            if payload.auto_verify_email or item.email_verified is True:
                user.email_verified_at = user.email_verified_at or now
            await _ensure_profiles_for_user(session, user.id)
            action = "updated"

        plan_code = (item.membership.plan_code.strip().lower() if item.membership and item.membership.plan_code else "free")
        if plan_code == "free":
            await replace_with_free_membership(
                session=session,
                user_id=user.id,
                provider="admin_import",
            )
        else:
            await create_or_replace_membership(
                session=session,
                user_id=user.id,
                plan_code=plan_code,
                provider="admin_import",
            )

        statement_results.append(
            SQLImportStatementResult(
                statement_no=statement_no,
                command="UPSERT",
                table="users",
                rowcount=None if payload.dry_run else 1,
            )
        )
        statement_no += 1
        statement_results.append(
            SQLImportStatementResult(
                statement_no=statement_no,
                command="UPSERT",
                table="user_memberships",
                rowcount=None if payload.dry_run else 1,
            )
        )
        statement_no += 1

        imported_users.append(
            SQLImportUserResult(
                email=user.email,
                user_id=user.id,
                action=action,
                plan_code=plan_code,
                email_verified=user.email_verified_at is not None,
                created_at=user.created_at,
            )
        )

    return statement_results, imported_users


async def _sql_import_handler(
    payload: SQLImportRequest,
    session: AsyncSession,
    x_admin_import_key: str | None,
    admin_import_key: str | None,
) -> SQLImportResponse:
    _require_sql_import_enabled()
    resolved_admin_key = _resolve_admin_import_key(
        header_key=x_admin_import_key,
        body_key=payload.admin_import_key,
        query_key=admin_import_key,
    )
    _require_admin_key(resolved_admin_key)

    results: list[SQLImportStatementResult] = []
    imported_users: list[SQLImportUserResult] = []

    if payload.sql:
        statements = _split_sql_statements(payload.sql)
        if not statements:
            raise bad_request("No SQL statements found.")
        if len(statements) > MAX_STATEMENTS_PER_IMPORT:
            raise bad_request(f"Too many statements. Max allowed: {MAX_STATEMENTS_PER_IMPORT}.")

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

    if payload.users:
        start_no = len(results) + 1
        try:
            user_results, imported_users = await _import_users_payload(session, payload, start_no)
        except Exception:
            await session.rollback()
            raise
        results.extend(user_results)

    if not payload.sql and not payload.users:
        raise bad_request("Provide 'sql' or 'users' payload for import.")

    if payload.dry_run:
        await session.rollback()
    else:
        await session.commit()

    snapshot = await _build_snapshot(session)
    return SQLImportResponse(
        dry_run=payload.dry_run,
        executed_statements=len(results),
        results=results,
        imported_users=imported_users,
        snapshot=snapshot,
    )


@router.put("/sql-import", response_model=SQLImportResponse)
async def sql_import_put(
    payload: SQLImportRequest,
    session: AsyncSession = Depends(get_db_session),
    x_admin_import_key: str | None = Header(default=None),
    admin_import_key: str | None = Query(default=None),
) -> SQLImportResponse:
    return await _sql_import_handler(payload, session, x_admin_import_key, admin_import_key)


@router.post("/sql-import", response_model=SQLImportResponse)
async def sql_import_post(
    payload: SQLImportRequest,
    session: AsyncSession = Depends(get_db_session),
    x_admin_import_key: str | None = Header(default=None),
    admin_import_key: str | None = Query(default=None),
) -> SQLImportResponse:
    return await _sql_import_handler(payload, session, x_admin_import_key, admin_import_key)


@router.get("/sql-import", response_model=dict[str, Any])
async def sql_import_get_format(
    view: str = Query(
        default="template",
        pattern="^(template|users|delete|sql|db_schema)$",
        description="template|users|delete|sql|db_schema",
    ),
) -> dict[str, Any]:
    _require_sql_import_enabled()
    payload = _sql_import_format_payload().model_dump()
    if view == "template":
        return payload
    if view == "users":
        return {
            "feature": "users_payload_example",
            "method": "POST/PUT",
            "endpoint": payload["endpoint"],
            "json": payload["users_payload_example"],
        }
    if view == "delete":
        return {
            "feature": "delete_payload_example",
            "method": "DELETE",
            "endpoint": payload["endpoint"],
            "json": payload["delete_payload_example"],
        }
    if view == "sql":
        return {
            "feature": "sql_payload_example",
            "method": "POST/PUT",
            "endpoint": payload["endpoint"],
            "json": payload["sql_payload_example"],
        }
    return _db_schema_payload()


@router.delete("/sql-import", response_model=SQLImportDeleteResponse)
async def sql_import_delete(
    payload: SQLImportDeleteRequest,
    session: AsyncSession = Depends(get_db_session),
    x_admin_import_key: str | None = Header(default=None),
    admin_import_key: str | None = Query(default=None),
) -> SQLImportDeleteResponse:
    _require_sql_import_enabled()
    resolved_admin_key = _resolve_admin_import_key(
        header_key=x_admin_import_key,
        body_key=payload.admin_import_key,
        query_key=admin_import_key,
    )
    _require_admin_key(resolved_admin_key)

    user = await _get_user_for_delete(session, payload)
    previous_status = user.status.value
    user_email = user.email
    user_id = user.id
    now = datetime.now(UTC)

    if payload.hard_delete:
        await session.delete(user)
        action = "hard_deleted"
    else:
        user.status = UserStatus.DELETED
        await session.execute(
            update(UserMembership)
            .where(
                UserMembership.user_id == user_id,
                UserMembership.status.in_(
                    [
                        MembershipStatus.ACTIVE,
                        MembershipStatus.PENDING_PAYMENT,
                        MembershipStatus.PAST_DUE,
                        MembershipStatus.SUSPENDED,
                    ]
                ),
            )
            .values(
                status=MembershipStatus.CANCELED,
                canceled_at=now,
                auto_renew=False,
            )
        )
        action = "soft_deleted"

    if payload.dry_run:
        await session.rollback()
    else:
        await session.commit()

    snapshot = await _build_snapshot(session)
    return SQLImportDeleteResponse(
        dry_run=payload.dry_run,
        action=action,
        user_id=user_id,
        email=user_email,
        previous_status=previous_status,
        snapshot=snapshot,
    )
