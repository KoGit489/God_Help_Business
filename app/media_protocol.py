from __future__ import annotations

import json
import struct
from typing import Any, BinaryIO

MAX_HEADER_BYTES = 8192
MAX_MEDIA_INPUT_BYTES = 2 * 1024 * 1024 * 1024
MAX_PDF_INPUT_BYTES = 100 * 1024 * 1024
MAX_TELEMETRY_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 100 * 1024 * 1024
CHUNK_BYTES = 64 * 1024


def receive_exact(connection: Any, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = connection.recv(min(CHUNK_BYTES, size - len(chunks)))
        if not chunk:
            raise ValueError("Media worker connection closed unexpectedly.")
        chunks.extend(chunk)
    return bytes(chunks)


def send_header(connection: Any, header: dict[str, Any]) -> None:
    encoded = json.dumps(header, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if not encoded or len(encoded) > MAX_HEADER_BYTES:
        raise ValueError("Media worker header is too large.")
    connection.sendall(struct.pack("!I", len(encoded)))
    connection.sendall(encoded)


def receive_header(connection: Any) -> dict[str, Any]:
    size = struct.unpack("!I", receive_exact(connection, 4))[0]
    if size < 2 or size > MAX_HEADER_BYTES:
        raise ValueError("Invalid media worker header length.")
    header = json.loads(receive_exact(connection, size).decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("Invalid media worker header.")
    return header


def send_stream(connection: Any, source: BinaryIO, size: int) -> None:
    remaining = size
    while remaining:
        chunk = source.read(min(CHUNK_BYTES, remaining))
        if not chunk:
            raise ValueError("Media input ended unexpectedly.")
        connection.sendall(chunk)
        remaining -= len(chunk)


def receive_stream(connection: Any, destination: BinaryIO, size: int) -> None:
    remaining = size
    while remaining:
        chunk = connection.recv(min(CHUNK_BYTES, remaining))
        if not chunk:
            raise ValueError("Media worker connection closed unexpectedly.")
        destination.write(chunk)
        remaining -= len(chunk)