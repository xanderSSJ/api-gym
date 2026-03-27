from __future__ import annotations

from app.api.v1.endpoints.admin_import import router


def test_sql_import_route_supports_put_and_post() -> None:
    methods_by_path: dict[str, set[str]] = {}
    for route in router.routes:
        if not hasattr(route, "methods"):
            continue
        methods_by_path.setdefault(route.path, set()).update(route.methods)

    sql_import_methods = methods_by_path.get("/admin/sql-import")
    assert sql_import_methods is not None
    assert "PUT" in sql_import_methods
    assert "POST" in sql_import_methods
    assert "DELETE" in sql_import_methods
    assert "GET" in sql_import_methods
