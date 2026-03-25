from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.admin_import import (
    _parse_user_status,
    _split_sql_statements,
    _validate_sql_statement,
)


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
