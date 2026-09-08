"""Bounded validation for private images and explicit equipment documents.

The storage adapter runs :func:`verify` in an isolated helper process. This
module deliberately returns code-only failures: decoder messages and paths are
not safe channel output.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import sys
import warnings
from os import PathLike
from pathlib import Path

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_DIMENSION = 8192

_MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
_CODES = frozenset({"media_invalid", "media_too_large"})
_CHUNK_BYTES = 64 * 1024
_ADDRESS_SPACE_BYTES = 256 * 1024 * 1024
_CPU_SECONDS = 5
_OPEN_FILES = 32


class MediaValidationError(Exception):
    """A validation failure whose public representation contains only a code."""

    def __init__(self, code: str) -> None:
        self.code = code if code in _CODES else "media_invalid"
        super().__init__(self.code)

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return f"MediaValidationError({self.code!r})"


def _read_bounded(path: str | PathLike[str]) -> bytes:
    try:
        file_path = Path(path)
        if file_path.stat().st_size > MAX_FILE_BYTES:
            raise MediaValidationError("media_too_large")
        content = bytearray()
        with file_path.open("rb") as stream:
            while len(content) <= MAX_FILE_BYTES:
                chunk = stream.read(min(_CHUNK_BYTES, MAX_FILE_BYTES + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
    except MediaValidationError:
        raise
    except (OSError, TypeError, ValueError):
        raise MediaValidationError("media_invalid") from None
    if len(content) > MAX_FILE_BYTES:
        raise MediaValidationError("media_too_large")
    if not content:
        raise MediaValidationError("media_invalid")
    return bytes(content)


def _dimensions(image) -> tuple[int, int]:
    width, height = image.size
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise MediaValidationError("media_invalid")
    if width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
        raise MediaValidationError("media_too_large")
    return width, height


def _single_frame(image) -> None:
    frames = getattr(image, "n_frames", 1)
    if type(frames) is not int or frames != 1 or getattr(image, "is_animated", False):
        raise MediaValidationError("media_invalid")


def _exact_container(content: bytes, image_format: str) -> None:
    """Reject obvious appended payloads without claiming complete polyglot detection."""
    if image_format == "JPEG":
        if not content.startswith(b"\xff\xd8") or not content.endswith(b"\xff\xd9"):
            raise MediaValidationError("media_invalid")
        return
    if image_format == "WEBP":
        if (
            len(content) < 12
            or content[:4] != b"RIFF"
            or content[8:12] != b"WEBP"
            or int.from_bytes(content[4:8], "little") + 8 != len(content)
        ):
            raise MediaValidationError("media_invalid")
        return
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise MediaValidationError("media_invalid")
    offset = 8
    saw_end = False
    while offset < len(content):
        if offset + 12 > len(content):
            raise MediaValidationError("media_invalid")
        length = int.from_bytes(content[offset : offset + 4], "big")
        end = offset + 12 + length
        if end > len(content):
            raise MediaValidationError("media_invalid")
        chunk_type = content[offset + 4 : offset + 8]
        offset = end
        if chunk_type == b"IEND":
            if length != 0 or offset != len(content):
                raise MediaValidationError("media_invalid")
            saw_end = True
            break
    if not saw_end:
        raise MediaValidationError("media_invalid")


def _pdf(content: bytes) -> dict[str, str | int]:
    """Inspect a restricted document, not an antivirus verdict or rendering engine.

    The caller must use the bounded child process for untrusted bytes. Streams
    are not decoded for text or images. Interactive content is not supported.
    """
    if re.match(rb"%PDF-(?:1\.[0-7]|2\.0)(?:\r\n|\r|\n)", content) is None or not content.rstrip(
        b" \t\r\n"
    ).endswith(b"%%EOF"):
        raise MediaValidationError("media_invalid")
    try:
        import pypdf
        from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

        if pypdf.__version__ != "6.17.0":
            raise MediaValidationError("media_invalid")
        # Parser diagnostics can contain document text. Never emit them.
        previous_disabled = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                reader = pypdf.PdfReader(io.BytesIO(content), strict=True)
                if reader.is_encrypted:
                    raise MediaValidationError("media_invalid")
                size = reader.trailer.get("/Size")
                if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 20_000:
                    raise MediaValidationError("media_too_large")
                pages = len(reader.pages)
                if not 1 <= pages <= 100:
                    raise MediaValidationError("media_too_large")
                forbidden_keys = {
                    "/A",
                    "/AA",
                    "/OpenAction",
                    "/JS",
                    "/JavaScript",
                    "/AcroForm",
                    "/XFA",
                    "/EmbeddedFiles",
                    "/EF",
                    "/AF",
                    "/Launch",
                    "/RichMediaContent",
                    "/RichMediaSettings",
                    "/3DD",
                    "/Collection",
                }
                forbidden_names = {
                    "/JavaScript",
                    "/Launch",
                    "/SubmitForm",
                    "/ImportData",
                    "/RichMedia",
                    "/3D",
                    "/Movie",
                    "/Sound",
                    "/FileAttachment",
                    "/GoToR",
                    "/GoToE",
                    "/URI",
                    "/Rendition",
                }
                stack, references, containers = [(reader.trailer, 0)], set(), set()
                visited = 0
                while stack:
                    obj, depth = stack.pop()
                    visited += 1
                    if visited > 20_000 or depth > 64:
                        raise MediaValidationError("media_too_large")
                    if isinstance(obj, IndirectObject):
                        reference = (obj.idnum, obj.generation)
                        if reference in references:
                            continue
                        references.add(reference)
                        stack.append((obj.get_object(), depth + 1))
                    elif isinstance(obj, (DictionaryObject, ArrayObject)):
                        if id(obj) in containers:
                            continue
                        containers.add(id(obj))
                        if len(obj) > 20_000 or len(stack) + len(obj) > 20_000:
                            raise MediaValidationError("media_too_large")
                        if isinstance(obj, DictionaryObject):
                            if forbidden_keys.intersection(obj.keys()):
                                raise MediaValidationError("media_invalid")
                            stack.extend((value, depth + 1) for value in obj.values())
                        else:
                            stack.extend((value, depth + 1) for value in obj)
                    elif isinstance(obj, NameObject) and obj in forbidden_names:
                        raise MediaValidationError("media_invalid")
        finally:
            logging.disable(previous_disabled)
    except MediaValidationError:
        raise
    except Exception:
        raise MediaValidationError("media_invalid") from None
    return {
        "mime_type": "application/pdf",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "pages": pages,
    }


def verify(path: str | PathLike[str], *, allow_pdf=False) -> dict[str, str | int]:
    """Decode one static image, or an explicitly enabled restricted PDF."""
    content = _read_bounded(path)
    if allow_pdf is True and content.startswith(b"%PDF-"):
        return _pdf(content)
    try:
        from PIL import Image
    except ImportError:
        raise MediaValidationError("media_invalid") from None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content), formats=tuple(_MIME_TYPES)) as image:
                image_format = image.format
                if image_format not in _MIME_TYPES:
                    raise MediaValidationError("media_invalid")
                _single_frame(image)
                width, height = _dimensions(image)
                _exact_container(content, image_format)
                image.verify()
            with Image.open(io.BytesIO(content), formats=tuple(_MIME_TYPES)) as image:
                if image.format != image_format or image.size != (width, height):
                    raise MediaValidationError("media_invalid")
                _single_frame(image)
                _dimensions(image)
                image.load()
                _single_frame(image)
    except MediaValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise MediaValidationError("media_too_large") from None
    except Exception:
        raise MediaValidationError("media_invalid") from None

    return {
        "mime_type": _MIME_TYPES[image_format],
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "width": width,
        "height": height,
    }


def _lower_process_limit(resource_module, kind: int, maximum: int) -> None:
    _, hard = resource_module.getrlimit(kind)
    target = maximum if hard == resource_module.RLIM_INFINITY else min(maximum, hard)
    if target <= 0:
        raise MediaValidationError("media_invalid")
    resource_module.setrlimit(kind, (target, target))


def _apply_process_limits() -> None:
    """Constrain the isolated POSIX decoder before Pillow is imported."""
    try:
        import resource

        _lower_process_limit(resource, resource.RLIMIT_AS, _ADDRESS_SPACE_BYTES)
        _lower_process_limit(resource, resource.RLIMIT_CPU, _CPU_SECONDS)
        _lower_process_limit(resource, resource.RLIMIT_NOFILE, _OPEN_FILES)
    except (AttributeError, ImportError, OSError, ValueError):
        raise MediaValidationError("media_invalid") from None


def _main(argv: list[str]) -> int:
    try:
        if len(argv) != 2 and not (len(argv) == 4 and argv[2] == "pdf"):
            raise MediaValidationError("media_invalid")
        _apply_process_limits()
        documents = len(argv) == 4
        if documents:
            # This argument is derived exclusively from the HA-installed package
            # by the trusted parent. It is not an upload/header/path parameter.
            dependency = Path(argv[3])
            if not dependency.is_absolute() or dependency.resolve(strict=True) != dependency:
                raise MediaValidationError("media_invalid")
            if not (dependency / "pypdf" / "__init__.py").is_file():
                raise MediaValidationError("media_invalid")
            sys.path.insert(0, str(dependency))
        response = {"ok": True, "result": verify(argv[1], allow_pdf=documents)}
    except MediaValidationError as error:
        response = {"ok": False, "code": error.code}
    except Exception:
        response = {"ok": False, "code": "media_invalid"}
    sys.stdout.write(json.dumps(response, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
