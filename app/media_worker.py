from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from app.media_protocol import (
    MAX_MEDIA_INPUT_BYTES,
    MAX_PDF_INPUT_BYTES,
    MAX_RESULT_BYTES,
    MAX_TELEMETRY_BYTES,
    receive_header,
    receive_stream,
    send_header,
    send_stream,
)

OPERATIONS = {
    "pdf": (MAX_PDF_INPUT_BYTES, ".pdf"),
    "preview": (MAX_MEDIA_INPUT_BYTES, None),
    "telemetry": (MAX_TELEMETRY_BYTES, ".json"),
}
PREVIEW_SUFFIXES = {".insp", ".insv", ".mp4", ".zip", ".jpg", ".jpeg", ".png"}
JOB_TIMEOUT_SECONDS = 120


def handle_connection(connection: socket.socket) -> None:
    connection.settimeout(JOB_TIMEOUT_SECONDS)
    try:
        header = receive_header(connection)
        operation = header.get("operation")
        size = header.get("size")
        if operation not in OPERATIONS or type(size) is not int or size < 0 or size > OPERATIONS[operation][0]:
            raise ValueError("Invalid media request.")
        suffix = OPERATIONS[operation][1]
        if operation == "preview":
            suffix = header.get("suffix")
            if not isinstance(suffix, str) or suffix not in PREVIEW_SUFFIXES:
                raise ValueError("Invalid media suffix.")
        with tempfile.TemporaryDirectory(prefix="media-job-") as temporary_dir:
            job_dir = Path(temporary_dir)
            input_path = job_dir / f"input{suffix}"
            output_path = job_dir / "output"
            metadata_path = job_dir / "metadata.json"
            with input_path.open("wb") as destination:
                receive_stream(connection, destination, size)
            environment = {
                "PATH": os.defpath,
                "HOME": temporary_dir,
                "TMPDIR": temporary_dir,
                "CAPTURE_PROCESSOR": os.getenv("CAPTURE_PROCESSOR", "manual"),
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
            }
            process = subprocess.Popen(
                [sys.executable, "-I", str(Path(__file__).with_name("media_job.py")), operation, str(input_path), str(output_path), str(metadata_path)],
                cwd=temporary_dir,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=os.name == "posix",
            )
            try:
                if process.wait(timeout=JOB_TIMEOUT_SECONDS) != 0:
                    raise ValueError("Media processing failed.")
            finally:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif process.poll() is None:
                    process.kill()
                process.wait()
            output_size = output_path.stat().st_size
            if output_size > MAX_RESULT_BYTES or metadata_path.stat().st_size > 4096:
                raise ValueError("Invalid media result.")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("Invalid media metadata.")
            send_header(connection, {"ok": True, "size": output_size, "metadata": metadata})
            with output_path.open("rb") as source:
                send_stream(connection, source, output_size)
    except Exception:
        try:
            send_header(connection, {"ok": False, "error": "Media processing failed."})
        except OSError:
            pass


def main() -> None:
    socket_path = Path(os.getenv("MEDIA_WORKER_SOCKET", "/run/media-worker/worker.sock"))
    socket_path.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        os.chmod(socket_path, 0o660)
        server.listen(8)
        while True:
            connection, _ = server.accept()
            with connection:
                handle_connection(connection)


if __name__ == "__main__":
    main()