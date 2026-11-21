import io
import json
import socket
import struct
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from app.media_protocol import MAX_HEADER_BYTES, receive_header, receive_stream, send_header, send_stream
from app.media_worker import handle_connection


def test_framed_media_protocol_transfers_binary_without_reformatting() -> None:
    sender, receiver = socket.socketpair()
    payload = b"\x00\xffmedia\x00" * 20000
    sender_thread = threading.Thread(target=lambda: (send_header(sender, {"operation": "preview", "size": len(payload)}), send_stream(sender, io.BytesIO(payload), len(payload))))
    try:
        sender_thread.start()
        assert receive_header(receiver) == {"operation": "preview", "size": len(payload)}
        output = io.BytesIO()
        receive_stream(receiver, output, len(payload))
        sender_thread.join(timeout=5)
        assert not sender_thread.is_alive()
        assert output.getvalue() == payload
    finally:
        sender.close()
        receiver.close()


def test_framed_media_protocol_rejects_oversized_headers_and_truncated_streams() -> None:
    sender, receiver = socket.socketpair()
    try:
        sender.sendall(struct.pack("!I", MAX_HEADER_BYTES + 1))
        with pytest.raises(ValueError, match="header length"):
            receive_header(receiver)
    finally:
        sender.close()
        receiver.close()
    sender, receiver = socket.socketpair()
    try:
        sender.sendall(b"short")
        sender.close()
        with pytest.raises(ValueError, match="closed unexpectedly"):
            receive_stream(receiver, io.BytesIO(), 10)
    finally:
        receiver.close()


@pytest.mark.parametrize("operation,extension,expected_type", [("pdf", ".pdf", "image/png"), ("preview", ".insp", None)])
def test_media_job_converts_real_files_in_an_isolated_interpreter(tmp_path, operation, extension, expected_type) -> None:
    from PIL import Image

    input_path = tmp_path / f"input{extension}"
    output_path = tmp_path / "output.bin"
    metadata_path = tmp_path / "metadata.json"
    Image.new("RGB", (80, 40), (50, 100, 150)).save(input_path, format="PDF" if operation == "pdf" else "JPEG")
    job_script = Path(__file__).resolve().parents[1] / "app" / "media_job.py"
    result = subprocess.run([sys.executable, "-I", str(job_script), operation, str(input_path), str(output_path), str(metadata_path)], capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if expected_type:
        assert metadata["content_type"] == expected_type
        assert output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    else:
        assert metadata["preview_available"] is True
        assert output_path.read_bytes().startswith(b"\xff\xd8\xff")


def test_worker_handles_a_pdf_without_access_to_client_paths(tmp_path) -> None:
    from PIL import Image

    input_path = tmp_path / "plan.pdf"
    Image.new("RGB", (40, 40), "white").save(input_path, format="PDF")
    payload = input_path.read_bytes()
    client, server = socket.socketpair()
    worker = threading.Thread(target=handle_connection, args=(server,))
    try:
        worker.start()
        send_header(client, {"operation": "pdf", "size": len(payload), "suffix": ".pdf"})
        send_stream(client, io.BytesIO(payload), len(payload))
        response = receive_header(client)
        assert response["ok"] is True
        output = io.BytesIO()
        receive_stream(client, output, response["size"])
        assert output.getvalue().startswith(b"\x89PNG\r\n\x1a\n")
        worker.join(timeout=5)
        assert not worker.is_alive()
    finally:
        client.close()
        server.close()


def test_worker_rejects_oversized_input_before_receiving_it() -> None:
    client, server = socket.socketpair()
    worker = threading.Thread(target=handle_connection, args=(server,))
    try:
        worker.start()
        send_header(client, {"operation": "pdf", "size": 101 * 1024 * 1024})
        assert receive_header(client)["ok"] is False
        worker.join(timeout=5)
        assert not worker.is_alive()
    finally:
        client.close()
        server.close()


def test_isolated_preview_rejects_generated_placeholder(tmp_path) -> None:
    input_path = tmp_path / "invalid.insp"
    input_path.write_bytes(b"not a photo")
    output_path = tmp_path / "output"
    metadata_path = tmp_path / "metadata.json"
    job_script = Path(__file__).resolve().parents[1] / "app" / "media_job.py"
    result = subprocess.run([sys.executable, "-I", str(job_script), "preview", str(input_path), str(output_path), str(metadata_path)], capture_output=True, timeout=30, check=False)
    assert result.returncode == 0
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["preview_available"] is False
    assert output_path.read_bytes() == b""


def test_configured_media_worker_handles_pdf_and_telemetry(monkeypatch) -> None:
    from app import main

    calls = []

    def fake_worker(operation, source, size, suffix):
        calls.append((operation, source.read(), size, suffix))
        if operation == "pdf":
            return {"content_type": "image/png"}, b"worker-png"
        return {"content_type": "application/json"}, b'{"status":"ready"}'

    monkeypatch.setenv("MEDIA_WORKER_SOCKET", "/isolated/worker.sock")
    monkeypatch.setattr(main, "process_media", fake_worker)
    assert main._rasterize_floor_plan(b"pdf") == b"worker-png"
    assert main._process_capture_telemetry({"source": "manual"}) == {"status": "ready"}
    assert [call[0] for call in calls] == ["pdf", "telemetry"]