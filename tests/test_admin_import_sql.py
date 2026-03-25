from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.admin_import import (
    _require_admin_key,
    _resolve_admin_import_key,
    _parse_user_status,
    _split_sql_statements,
    _validate_sql_statement,
)
from app.core.config import settings


def test_split_sql_statements_two_inserts() -> None:
    script = """
    INSERT INTO users (id, full_name) VALUES ('1', 'A');
    INSERT INTO user_memberships (id, user_id) VALUES ('2', '1');
    """
    statements = _split_sql_statements(script)
    assert len(statements) == 2
    assert statements[0].upper().startswith("INSERT INTO USERS")
    assert statements[1].upper().startswith("INSERT INTO USER_MEMBERSHIPS")


def test_validate_sql_statement_allows_insert_users() -> None:
    command, table = _validate_sql_statement(
        "INSERT INTO users (id, full_name, email, password_hash, status) VALUES ('1','A','a@b.com','hash','ACTIVE')"
    )
    assert command == "INSERT"
    assert table == "users"


def test_validate_sql_statement_rejects_drop_keyword() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_sql_statement("DROP TABLE users")
    assert exc_info.value.status_code == 403


def test_validate_sql_statement_rejects_non_allowed_table() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_sql_statement("INSERT INTO payment_transactions (id) VALUES ('x')")
    assert exc_info.value.status_code == 403


def test_parse_user_status_accepts_active() -> None:
    status = _parse_user_status("active")
    assert status.value == "active"


def test_parse_user_status_rejects_invalid_status() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _parse_user_status("owner")
    assert exc_info.value.status_code == 400


def test_resolve_admin_import_key_prefers_header() -> None:
    resolved = _resolve_admin_import_key(
        header_key="header-key",
        body_key="body-key",
        query_key="query-key",
    )
    assert resolved == "header-key"


def test_resolve_admin_import_key_falls_back_to_body_then_query() -> None:
    resolved_body = _resolve_admin_import_key(
        header_key=None,
        body_key="body-key",
        query_key="query-key",
    )
    assert resolved_body == "body-key"

    resolved_query = _resolve_admin_import_key(
        header_key="   ",
        body_key=None,
        query_key="query-key",
    )
    assert resolved_query == "query-key"


def test_require_admin_key_accepts_trimmed_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_import_require_key", True, raising=False)
    monkeypatch.setattr(settings, "admin_import_key", "super-secret", raising=False)
    _require_admin_key("  super-secret  ")


def test_require_admin_key_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_import_require_key", True, raising=False)
    monkeypatch.setattr(settings, "admin_import_key", "super-secret", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        _require_admin_key("wrong-secret")
    assert exc_info.value.status_code == 403


def test_require_admin_key_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_import_require_key", False, raising=False)
    monkeypatch.setattr(settings, "admin_import_key", "", raising=False)
    _require_admin_key(None)
