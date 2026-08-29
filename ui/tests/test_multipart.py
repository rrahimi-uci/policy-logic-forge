from __future__ import annotations

import io
import random
from pathlib import Path

import pytest

from ui.backend.multipart import MultipartError, UploadTooLarge, save_upload

BOUNDARY = b"----WebKitFormBoundaryTestXYZ123"
CONTENT_TYPE = f"multipart/form-data; boundary={BOUNDARY.decode()}"


def _part(
    name: str,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    body: bytes = b"",
) -> bytes:
    """Build one raw multipart part (headers + body), independently of the
    parser under test, so the test actually catches encode/decode mismatches."""
    disposition = f'form-data; name="{name}"'
    if filename is not None:
        disposition += f'; filename="{filename}"'
    header = f"Content-Disposition: {disposition}\r\n"
    if content_type is not None:
        header += f"Content-Type: {content_type}\r\n"
    header += "\r\n"
    return header.encode("latin-1") + body


def _build_body(parts: list[bytes]) -> bytes:
    out = bytearray()
    for part in parts:
        out += b"--" + BOUNDARY + b"\r\n" + part + b"\r\n"
    out += b"--" + BOUNDARY + b"--\r\n"
    return bytes(out)


def test_multiple_files_nested_paths_and_text_fields(tmp_path: Path) -> None:
    file_a = b"alpha file content\nline two\n"
    file_b = b"beta content, different bytes: \x00\x01\xff"
    body = _build_body(
        [
            _part("domain", body=b"nda_confidentiality"),
            _part("batch_name_hint", body=b"my-run"),
            _part("files", filename="top/nested/a.txt", content_type="text/plain", body=file_a),
            _part("files", filename="top/b.txt", content_type="application/octet-stream", body=file_b),
        ]
    )
    result = save_upload(io.BytesIO(body), len(body), CONTENT_TYPE, upload_root=tmp_path)
    assert result["domain"] == "nda_confidentiality"
    assert result["batch_name_hint"] == "my-run"
    assert result["file_count"] == 2
    assert result["total_bytes"] == len(file_a) + len(file_b)
    upload_dir = Path(result["dir"])
    assert upload_dir.parent == tmp_path
    assert (upload_dir / "top" / "nested" / "a.txt").read_bytes() == file_a
    assert (upload_dir / "top" / "b.txt").read_bytes() == file_b


def test_fields_only_no_files(tmp_path: Path) -> None:
    body = _build_body([_part("domain", body=b"privacy_policy")])
    result = save_upload(io.BytesIO(body), len(body), CONTENT_TYPE, upload_root=tmp_path)
    assert result["domain"] == "privacy_policy"
    assert result["file_count"] == 0
    assert result["total_bytes"] == 0
    assert result["batch_name_hint"] is None


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    body = _build_body([_part("files", filename="../escape.txt", body=b"x")])
    with pytest.raises(MultipartError):
        save_upload(io.BytesIO(body), len(body), CONTENT_TYPE, upload_root=tmp_path)


def test_nested_path_traversal_is_rejected(tmp_path: Path) -> None:
    body = _build_body([_part("files", filename="ok/../../escape.txt", body=b"x")])
    with pytest.raises(MultipartError):
        save_upload(io.BytesIO(body), len(body), CONTENT_TYPE, upload_root=tmp_path)


def test_absolute_path_is_rejected(tmp_path: Path) -> None:
    body = _build_body([_part("files", filename="/etc/passwd", body=b"x")])
    with pytest.raises(MultipartError):
        save_upload(io.BytesIO(body), len(body), CONTENT_TYPE, upload_root=tmp_path)


def test_empty_filename_is_rejected(tmp_path: Path) -> None:
    body = _build_body([_part("files", filename="", body=b"x")])
    with pytest.raises(MultipartError):
        save_upload(io.BytesIO(body), len(body), CONTENT_TYPE, upload_root=tmp_path)


def test_content_length_over_limit_raises_before_writing(tmp_path: Path) -> None:
    body = _build_body([_part("files", filename="a.txt", body=b"x" * 10)])
    with pytest.raises(UploadTooLarge):
        save_upload(io.BytesIO(body), len(body), CONTENT_TYPE, upload_root=tmp_path, max_bytes=5)
    assert list(tmp_path.iterdir()) == []


def test_wrong_content_type_is_rejected(tmp_path: Path) -> None:
    body = b"not-a-multipart-body"
    with pytest.raises(MultipartError):
        save_upload(io.BytesIO(body), len(body), "application/json", upload_root=tmp_path)


def test_binary_file_content_with_boundary_adjacent_sequences_round_trips(tmp_path: Path) -> None:
    """The test that actually validates the parser is binary-safe.

    Sprinkles byte sequences through a large binary payload that look like
    (but are not) the real multipart delimiter -- including one straddling
    the parser's internal 64KiB read-chunk boundary -- and asserts the file
    is written back byte-for-byte identical.
    """
    rng = random.Random(1234)
    payload = bytearray(rng.randbytes(200_000))

    # A decoy that starts the real delimiter pattern ("\r\n--" + a boundary
    # prefix) but never completes it -- must not be mistaken for the
    # terminator, and must survive a fill-boundary split intact.
    decoy = b"\r\n--" + BOUNDARY[:12]
    for offset in (0, 1_000, 65_536 - 3, 150_000):
        payload[offset : offset + len(decoy)] = decoy

    # A run of literal "--" and non-UTF8 bytes, for good measure.
    payload[50_000:50_010] = b"-" * 10
    payload[70_000:70_005] = b"\x00\xff\x00\xff\x00"
    payload = bytes(payload)

    body = _build_body(
        [_part("files", filename="binary.bin", content_type="application/octet-stream", body=payload)]
    )
    result = save_upload(io.BytesIO(body), len(body), CONTENT_TYPE, upload_root=tmp_path)
    assert result["file_count"] == 1
    assert result["total_bytes"] == len(payload)
    written = (Path(result["dir"]) / "binary.bin").read_bytes()
    assert written == payload
