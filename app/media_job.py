from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.capture_processing import CaptureProcessor
from app.media_protocol import MAX_RESULT_BYTES, MAX_TELEMETRY_BYTES

MAX_PDF_PIXELS = 40_000_000


def run_job(operation: str, input_path: Path, output_path: Path, metadata_path: Path) -> None:
    if operation == "pdf":
        import pymupdf

        with pymupdf.open(str(input_path)) as document:
            page = document.load_page(0)
            width = math.ceil(page.rect.width * 150 / 72)
            height = math.ceil(page.rect.height * 150 / 72)
            if width <= 0 or height <= 0 or width * height > MAX_PDF_PIXELS:
                raise ValueError("Floor plan exceeds the decoded-pixel limit.")
            data = page.get_pixmap(dpi=150).tobytes("png")
        metadata = {"content_type": "image/png"}
    elif operation == "preview":
        result = CaptureProcessor().extract_insp_preview(input_path)
        is_placeholder = "placeholder" in str(result.get("message", "")).lower()
        data = b"" if is_placeholder else result.get("preview_data") or b""
        metadata = {
            "preview_available": bool(result.get("preview_available") and data),
            "preview_format": "jpeg" if data else None,
            "preview_width": int(result.get("preview_width") or 0),
            "preview_height": int(result.get("preview_height") or 0),
            "message": "Preview generated." if data else "Preview could not be generated.",
        }
    elif operation == "telemetry":
        if input_path.stat().st_size > MAX_TELEMETRY_BYTES:
            raise ValueError("Telemetry is too large.")
        telemetry = json.loads(input_path.read_text(encoding="utf-8"))
        data = json.dumps(CaptureProcessor().process(telemetry), allow_nan=False, separators=(",", ":")).encode("utf-8")
        metadata = {"content_type": "application/json"}
    else:
        raise ValueError("Unsupported media operation.")
    if len(data) > MAX_RESULT_BYTES:
        raise ValueError("Media result is too large.")
    output_path.write_bytes(data)
    metadata_path.write_text(json.dumps(metadata, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(2)
    run_job(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))