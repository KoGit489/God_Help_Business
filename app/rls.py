from __future__ import annotations

from contextvars import ContextVar

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

_user_id: ContextVar[str] = ContextVar("casai_rls_user_id", default="")
_share_token: ContextVar[str] = ContextVar("casai_rls_share_token", default="")


def set_user_id(user_id: str | None) -> None:
    _user_id.set(user_id or "")


def set_share_token(token: str | None) -> None:
    _share_token.set(token or "")


def _apply_transaction_identity(session: Session, transaction: object, connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text("SELECT set_config('casai.user_id', :user_id, true), set_config('casai.share_token', :share_token, true)"),
        {"user_id": _user_id.get(), "share_token": _share_token.get()},
    )


event.listen(Session, "after_begin", _apply_transaction_identity)


def assert_postgres_rls(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        raise RuntimeError("RLS enforcement requires PostgreSQL.")
    role = connection.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
    if role.rolsuper or role.rolbypassrls:
        raise RuntimeError("The application database role must not be superuser or BYPASSRLS.")
    expected = {"projects", "pins", "annotations", "share_links"}
    policies = connection.execute(text("""
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
               pg_catalog.pg_get_userbyid(c.relowner) = current_user AS is_owner
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
    """), {"tables": list(expected)}).all()
    if {row.relname for row in policies} != expected:
        raise RuntimeError("RLS policies are missing from one or more project tables.")
    if any(not row.relrowsecurity or row.is_owner for row in policies):
        raise RuntimeError("The application role is not subject to RLS on every project table.")
    if any(not row.relforcerowsecurity for row in policies if row.relname != "share_links"):
        raise RuntimeError("Owner and child project tables must enforce RLS even for their owners.")
    policy_count = connection.execute(text("""
        SELECT count(*) FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
    """), {"tables": list(expected)}).scalar_one()
    if policy_count < len(expected) * 2:
        raise RuntimeError("Owner and share-read policies must exist on every project table.")
    if not connection.execute(text("SELECT has_schema_privilege(current_user, 'casai_security', 'USAGE') AND has_function_privilege(current_user, 'casai_security.can_read_shared_project(text, text)', 'EXECUTE')")).scalar_one():
        raise RuntimeError("The application role cannot use the scoped public-share policy.")
