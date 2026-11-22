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
               pg_catalog.pg_has_role(current_user, c.relowner, 'MEMBER') AS can_assume_owner,
               pg_catalog.has_table_privilege(current_user, c.oid, 'TRUNCATE') AS can_truncate
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
    """), {"tables": list(expected)}).all()
    if {row.relname for row in policies} != expected:
        raise RuntimeError("RLS policies are missing from one or more project tables.")
    if any(not row.relrowsecurity or row.can_assume_owner or row.can_truncate for row in policies):
        raise RuntimeError("The application role must be subject to RLS and cannot assume ownership or truncate project tables.")
    if any(not row.relforcerowsecurity for row in policies if row.relname != "share_links"):
        raise RuntimeError("Owner and child project tables must enforce RLS even for their owners.")
    installed_policies = connection.execute(text("""
        SELECT c.relname, p.polname, p.polcmd, p.polpermissive FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
    """), {"tables": list(expected)}).all()
    actual = {(row.relname, row.polname, row.polcmd, row.polpermissive) for row in installed_policies}
    required = {(table, "casai_owner", "*", True) for table in expected}
    required.update((table, "casai_shared_read", "r", True) for table in expected)
    if actual != required:
        raise RuntimeError("Project tables must have only the expected owner and share-read policies.")
    if connection.execute(text("""
        SELECT EXISTS (SELECT 1 FROM pg_roles WHERE (rolsuper OR rolbypassrls)
                       AND pg_has_role(current_user, oid, 'MEMBER'))
    """)).scalar_one():
        raise RuntimeError("The application role must not be a member of a privileged database role.")
    if connection.execute(text("SELECT has_schema_privilege(current_user, 'casai_security', 'CREATE')")).scalar_one():
        raise RuntimeError("The application role must not create objects in the RLS policy schema.")
    if not connection.execute(text("SELECT has_schema_privilege(current_user, 'casai_security', 'USAGE') AND has_function_privilege(current_user, 'casai_security.can_read_shared_project(text, text)', 'EXECUTE')")).scalar_one():
        raise RuntimeError("The application role cannot use the scoped public-share policy.")
