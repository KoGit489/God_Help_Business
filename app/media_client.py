from __future__ import annotations

import io
import os
import socket
from pathlib import Path
from typing import Any, BinaryIO

from app.media_protocol import MAX_RESULT_BYTES, receive_header, receive_stream, send_header, send_stream


def process_media(operation: str, source: BinaryIO, size: int, suffix: str = "") -> tuple[dict[str, Any], bytes]:
    socket_path = os.getenv("MEDIA_WORKER_SOCKET", "").strip()
    if not socket_path or not hasattr(socket, "AF_UNIX"):
        raise RuntimeError("Isolated media worker is not configured.")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(180)
        connection.connect(socket_path)
        send_header(connection, {"operation": operation, "size": size, "suffix": suffix.lower()})
        send_stream(connection, source, size)
        response = receive_header(connection)
        if response.get("ok") is not True:
            raise RuntimeError("Isolated media processing failed.")
        output_size = response.get("size")
        metadata = response.get("metadata")
        if type(output_size) is not int or not 0 <= output_size <= MAX_RESULT_BYTES or not isinstance(metadata, dict):
            raise ValueError("Invalid media worker response.")
        output = io.BytesIO()
        receive_stream(connection, output, output_size)
        return metadata, output.getvalue()


def process_media_path(operation: str, path: Path) -> tuple[dict[str, Any], bytes]:
    with path.open("rb") as source:
        return process_media(operation, source, path.stat().st_size, path.suffix)