"""Hand-rolled, streaming ``multipart/form-data`` parsing.

``cgi.FieldStorage`` is removed in this repo's Python version (3.14), so this
module exists in its place. Compliance corpora under ``compliance-files/``
run up to roughly 219MB / ~7,900 files (the ``deonticbench`` domain), so
buffering an entire upload request body in memory before parsing it is a
real risk, not a hypothetical one -- this parser scans for boundary markers
incrementally from a file-like request stream (``self.rfile`` from
``http.server``) and streams file-part bytes straight to disk, never holding
more than a small, bounded read-chunk in memory at once.

Kept dependency-free on purpose, matching ``ui/backend``'s stated stdlib-only
design (see ``ui/contracts.md``).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, BinaryIO, Callable

# Generous relative to the largest domain corpus in this repo (~219MB); an
# early, explicit rejection here is far cheaper than discovering an
# oversized request mid-stream.
MAX_UPLOAD_BYTES = 500_000_000

_CHUNK_SIZE = 1 << 16  # 64KiB read granularity from the socket
_MAX_HEADER_LINE = 8192  # guards against a pathological/malformed header line


class MultipartError(ValueError):
    """Malformed multipart body, or an upload that fails a size/path guard."""


class UploadTooLarge(MultipartError):
    """The declared ``Content-Length`` exceeds the configured upload limit."""


_PARAM_RE = re.compile(
    r'(?P<key>[A-Za-z0-9_.-]+)=(?:"(?P<qval>(?:[^"\\]|\\.)*)"|(?P<val>[^;]+))'
)


def _parse_params(header_value: str) -> dict[str, str]:
    """Parse the ``key=value`` / ``key="quoted value"`` parameters of a header."""
    params: dict[str, str] = {}
    for match in _PARAM_RE.finditer(header_value or ""):
        key = match.group("key").lower()
        if match.group("qval") is not None:
            value = match.group("qval").replace('\\"', '"').replace("\\\\", "\\")
        else:
            value = match.group("val").strip()
        params[key] = value
    return params


def _extract_boundary(content_type: str) -> bytes:
    media_type, _, rest = (content_type or "").partition(";")
    if media_type.strip().lower() != "multipart/form-data":
        raise MultipartError(f"unsupported content type for multipart parsing: {content_type!r}")
    boundary = _parse_params(rest).get("boundary")
    if not boundary:
        raise MultipartError("multipart/form-data request is missing a boundary parameter")
    return boundary.encode("latin-1")


def _safe_relative_path(raw: str) -> str:
    """Validate and normalize a part's ``filename`` into a safe relative path.

    Rejects an empty path, an absolute path (leading ``/`` or a Windows
    drive letter), and any ``..`` path-traversal segment.
    """
    if raw is None or not raw.strip():
        raise MultipartError("upload part is missing a filename")
    candidate = raw.replace("\\", "/")
    if candidate.startswith("/") or (len(candidate) > 1 and candidate[1] == ":"):
        raise MultipartError(f"absolute paths are not allowed in an upload: {raw!r}")
    segments = [segment for segment in candidate.split("/") if segment not in ("", ".")]
    if not segments:
        raise MultipartError(f"upload part resolves to an empty filename: {raw!r}")
    if any(segment == ".." for segment in segments):
        raise MultipartError(f"path traversal is not allowed in an upload: {raw!r}")
    return "/".join(segments)


class _Scanner:
    """Incremental boundary scanner over a length-bounded binary stream."""

    def __init__(self, source: BinaryIO, content_length: int, boundary: bytes) -> None:
        self._source = source
        self._remaining = max(0, int(content_length))
        self._buf = bytearray()
        self._boundary = boundary
        self._delimiter = b"\r\n--" + boundary
        self._eof = False

    def _fill(self, target: int) -> None:
        while len(self._buf) < target and not self._eof:
            if self._remaining <= 0:
                self._eof = True
                break
            chunk = self._source.read(min(_CHUNK_SIZE, self._remaining))
            if not chunk:
                self._eof = True
                break
            self._buf.extend(chunk)
            self._remaining -= len(chunk)

    def _peek(self, n: int) -> bytes:
        if len(self._buf) < n and not self._eof:
            self._fill(n)
        return bytes(self._buf[:n])

    def _read_line(self) -> bytes:
        """Read and consume one CRLF-terminated line (without the CRLF)."""
        while True:
            idx = self._buf.find(b"\r\n")
            if idx != -1:
                line = bytes(self._buf[:idx])
                del self._buf[: idx + 2]
                return line
            if self._eof:
                raise MultipartError("unexpected end of multipart body while reading a header line")
            if len(self._buf) > _MAX_HEADER_LINE:
                raise MultipartError("multipart header line too long")
            self._fill(len(self._buf) + _CHUNK_SIZE)

    def expect_first_boundary(self) -> None:
        line = self._read_line()
        if line != b"--" + self._boundary:
            raise MultipartError("multipart body does not start with the expected boundary")

    def read_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        while True:
            line = self._read_line()
            if line == b"":
                return headers
            text = line.decode("latin-1")
            key, sep, value = text.partition(":")
            if sep:
                headers[key.strip().lower()] = value.strip()

    def consume_body(self, sink: Callable[[bytes], None]) -> None:
        """Stream this part's body to ``sink`` up to (excluding) the delimiter.

        Binary-safe: searches for the exact boundary byte sequence via
        ``bytes.find`` rather than any text decoding, so file content that
        happens to contain boundary-adjacent byte sequences is handled
        correctly as long as it does not contain the literal delimiter.
        """
        delimiter_len = len(self._delimiter)
        while True:
            idx = self._buf.find(self._delimiter)
            if idx != -1:
                sink(bytes(self._buf[:idx]))
                del self._buf[: idx + delimiter_len]
                return
            if self._eof:
                raise MultipartError("unexpected end of multipart body inside a part")
            # Flush everything except a delimiter-sized tail, in case the
            # delimiter is split across this fill boundary.
            safe = max(0, len(self._buf) - (delimiter_len - 1))
            if safe:
                sink(bytes(self._buf[:safe]))
                del self._buf[:safe]
            self._fill(len(self._buf) + _CHUNK_SIZE)

    def is_terminal(self) -> bool:
        """Consume the two bytes following a delimiter; True at the final boundary."""
        prefix = self._peek(2)
        if prefix == b"--":
            del self._buf[:2]
            return True
        if prefix == b"\r\n":
            del self._buf[:2]
            return False
        raise MultipartError("malformed multipart boundary terminator")

    def drain_remaining(self) -> None:
        """Discard any unread bytes still owed to this request's Content-Length."""
        self._buf.clear()
        while self._remaining > 0:
            chunk = self._source.read(min(_CHUNK_SIZE, self._remaining))
            if not chunk:
                return
            self._remaining -= len(chunk)


def parse_multipart(
    rfile: BinaryIO,
    content_length: int,
    content_type: str,
    *,
    on_field: Callable[[str, bytes], None],
    open_file: Callable[[str, str, str | None], BinaryIO],
) -> int:
    """Parse a ``multipart/form-data`` body, streaming file parts to disk.

    ``on_field(name, value)`` is called for each non-file part with the raw
    field bytes. ``open_file(name, filename, content_type)`` is called once
    per file part and must return a writable binary file object; it is
    closed by the parser once that part's bytes are fully read. Returns the
    total number of file bytes written.
    """
    boundary = _extract_boundary(content_type)
    scanner = _Scanner(rfile, content_length, boundary)
    scanner.expect_first_boundary()
    total_bytes = 0
    while True:
        headers = scanner.read_headers()
        params = _parse_params(headers.get("content-disposition", ""))
        name = params.get("name", "")
        filename = params.get("filename")
        part_content_type = headers.get("content-type")

        if filename is not None:
            handle = open_file(name, filename, part_content_type)
            try:
                def _write(chunk: bytes, _handle: BinaryIO = handle) -> None:
                    nonlocal total_bytes
                    if chunk:
                        _handle.write(chunk)
                        total_bytes += len(chunk)

                scanner.consume_body(_write)
            finally:
                handle.close()
        else:
            collected = bytearray()

            def _collect(chunk: bytes, _collected: bytearray = collected) -> None:
                _collected.extend(chunk)

            scanner.consume_body(_collect)
            on_field(name, bytes(collected))

        if scanner.is_terminal():
            break
    scanner.drain_remaining()
    return total_bytes


def save_upload(
    rfile: BinaryIO,
    content_length: int,
    content_type: str,
    *,
    upload_root: str | Path,
    upload_id: str | None = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> dict[str, Any]:
    """Parse an uploaded ``multipart/form-data`` request and stream its files to disk.

    Files land at ``<upload_root>/<upload_id>/<relative-path>``, preserving
    the structure a browser sends via
    ``FormData.append("files", file, file.webkitRelativePath)``. Non-file
    fields (``domain``, ``batch_name_hint``, ...) are collected and returned
    as UTF-8 text. Rejects path traversal, absolute paths, and an empty
    relative path per file part; enforces ``max_bytes`` against
    ``Content-Length`` before any writing begins.
    """
    if content_length > max_bytes:
        raise UploadTooLarge(
            f"upload of {content_length} bytes exceeds the {max_bytes}-byte limit"
        )
    if content_length <= 0:
        raise MultipartError("upload request has an empty or missing body")

    resolved_upload_id = upload_id or str(uuid.uuid4())
    target_root = (Path(upload_root) / resolved_upload_id).resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    fields: dict[str, str] = {}
    file_count = 0

    def on_field(name: str, value: bytes) -> None:
        fields[name] = value.decode("utf-8", errors="replace")

    def open_file(_name: str, filename: str, _content_type: str | None) -> BinaryIO:
        nonlocal file_count
        relative = _safe_relative_path(filename)
        destination = (target_root / relative).resolve()
        if destination != target_root and target_root not in destination.parents:
            raise MultipartError(f"upload path escapes the upload directory: {filename!r}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        file_count += 1
        return destination.open("wb")

    total_bytes = parse_multipart(
        rfile, content_length, content_type, on_field=on_field, open_file=open_file
    )

    return {
        "upload_id": resolved_upload_id,
        "dir": str(target_root),
        "domain": fields.get("domain", ""),
        "batch_name_hint": fields.get("batch_name_hint") or None,
        "file_count": file_count,
        "total_bytes": total_bytes,
    }
