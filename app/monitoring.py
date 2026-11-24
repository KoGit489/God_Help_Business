from __future__ import annotations

from typing import Any


def sanitize_error_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    exception_values = event.get("exception", {}).get("values", [])
    if not exception_values:
        return None
    sanitized = {key: event[key] for key in ("event_id", "timestamp", "platform", "level", "environment", "sdk") if key in event}
    sanitized_exceptions = []
    for item in exception_values:
        safe_item = {"type": item.get("type", "Exception"), "value": "[redacted]"}
        frames = item.get("stacktrace", {}).get("frames", [])
        if frames:
            safe_item["stacktrace"] = {"frames": [
                {key: frame[key] for key in ("filename", "module", "function", "lineno", "in_app") if key in frame}
                for frame in frames
            ]}
        sanitized_exceptions.append(safe_item)
    sanitized["exception"] = {"values": sanitized_exceptions}
    return sanitized


def configure_error_tracking(dsn: str, environment: str) -> bool:
    if not dsn:
        return False
    import logging

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        send_default_pii=False,
        include_local_variables=False,
        max_breadcrumbs=0,
        traces_sample_rate=0.0,
        auto_enabling_integrations=False,
        integrations=[FastApiIntegration(), StarletteIntegration(), LoggingIntegration(level=None, event_level=logging.ERROR)],
        before_send=sanitize_error_event,
    )
    return True