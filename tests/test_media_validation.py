"""Synthetic tests for the bounded image verifier."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
import zlib
from pathlib import Path

from custom_components.family_assistant import media_validation
from custom_components.family_assistant.media_validation import (
    MAX_DIMENSION,
    MAX_FILE_BYTES,
    MAX_PIXELS,
    MediaValidationError,
    verify,
)

try:
    from PIL import Image, ImageFile

    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return len(payload).to_bytes(4, "big") + body + zlib.crc32(body).to_bytes(4, "big")


class MediaValidationBase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory_context = tempfile.TemporaryDirectory()
        self.directory = Path(self.directory_context.name)

    def tearDown(self) -> None:
        self.directory_context.cleanup()

    def write(self, name: str, content: bytes) -> Path:
        target = self.directory / name
        target.write_bytes(content)
        return target

    def rejected(self, name: str, content: bytes, code: str = "media_invalid") -> None:
        with self.assertRaises(MediaValidationError) as raised:
            verify(self.write(name, content))
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(str(raised.exception), code)
        self.assertNotIn(str(self.directory), repr(raised.exception))


class TestMediaValidationWithoutDecoder(MediaValidationBase):
    def test_error_contains_only_supported_code(self) -> None:
        for supplied, expected in (
            ("media_invalid", "media_invalid"),
            ("media_too_large", "media_too_large"),
            ("decoder detail C:\\private\\image.png", "media_invalid"),
        ):
            with self.subTest(supplied=supplied):
                error = MediaValidationError(supplied)
                self.assertEqual(error.args, (expected,))
                self.assertEqual(error.code, expected)
                self.assertEqual(str(error), expected)
                self.assertNotIn("private", repr(error))

    def test_missing_bad_path_and_empty_are_code_only_invalid(self) -> None:
        values = (self.directory / "missing.jpg", None, self.write("empty.png", b""))
        for value in values:
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(MediaValidationError) as raised:
                    verify(value)  # type: ignore[arg-type]
                self.assertEqual(raised.exception.code, "media_invalid")
                self.assertEqual(raised.exception.__cause__, None)

    def test_oversize_is_rejected_before_decode(self) -> None:
        target = self.directory / "oversize.jpg"
        with target.open("wb") as stream:
            stream.seek(MAX_FILE_BYTES)
            stream.write(b"x")
        with self.assertRaises(MediaValidationError) as raised:
            verify(target)
        self.assertEqual(raised.exception.code, "media_too_large")

    @unittest.skipUnless(os.name == "posix", "production CLI requires POSIX resource limits")
    def test_cli_failure_is_bounded_code_only_json(self) -> None:
        missing = self.directory / "private-missing.jpg"
        completed = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-I",
                str(Path(media_validation.__file__).resolve()),
                str(missing),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
        self.assertEqual(json.loads(completed.stdout), {"ok": False, "code": "media_invalid"})
        self.assertNotIn(str(missing), completed.stdout)
        self.assertEqual(completed.stderr, "")


@unittest.skipUnless(PILLOW_AVAILABLE, "Pillow required for decoder tests")
class TestMediaValidationWithPillow(MediaValidationBase):
    def image(self, image_format: str, size=(32, 24), **save_options) -> bytes:
        output = io.BytesIO()
        Image.new("RGB", size, (31, 127, 223)).save(output, format=image_format, **save_options)
        return output.getvalue()

    def test_supported_formats_return_exact_metadata(self) -> None:
        for image_format, mime in (
            ("JPEG", "image/jpeg"),
            ("PNG", "image/png"),
            ("WEBP", "image/webp"),
        ):
            with self.subTest(image_format=image_format):
                content = self.image(image_format)
                result = verify(self.write(f"image-{image_format.lower()}.bin", content))
                self.assertEqual(
                    result,
                    {
                        "mime_type": mime,
                        "size_bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "width": 32,
                        "height": 24,
                    },
                )

    @unittest.skipUnless(os.name == "posix", "production CLI requires POSIX resource limits")
    def test_cli_returns_compact_verified_metadata(self) -> None:
        content = self.image("PNG")
        target = self.write("cli-private-name.png", content)
        completed = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-I",
                str(Path(media_validation.__file__).resolve()),
                str(target),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "ok": True,
                "result": {
                    "mime_type": "image/png",
                    "size_bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "width": 32,
                    "height": 24,
                },
            },
        )
        self.assertLess(len(completed.stdout), 4096)
        self.assertEqual(completed.stderr, "")

    def test_content_not_filename_controls_format(self) -> None:
        result = verify(self.write("claimed.jpeg", self.image("PNG")))
        self.assertEqual(result["mime_type"], "image/png")

    def test_disallowed_and_mime_spoofed_payloads(self) -> None:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("inside.txt", "synthetic")
        payloads = {
            "svg.jpg": b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            "html.png": b"<!doctype html><html><body>synthetic</body></html>",
            "document.webp": b"%PDF-1.4\n%%EOF",
            "archive.jpeg": archive.getvalue(),
            "gif.png": self.image("GIF"),
            "tiff.jpg": self.image("TIFF"),
        }
        for name, content in payloads.items():
            with self.subTest(name=name):
                self.rejected(name, content)

    def test_truncated_supported_formats_are_rejected(self) -> None:
        for image_format in ("JPEG", "PNG", "WEBP"):
            with self.subTest(image_format=image_format):
                content = self.image(image_format, (128, 96))
                self.rejected(f"truncated-{image_format}.bin", content[: len(content) // 2])

    def test_animated_png_and_webp_are_rejected(self) -> None:
        for image_format in ("PNG", "WEBP"):
            with self.subTest(image_format=image_format):
                output = io.BytesIO()
                first = Image.new("RGB", (16, 16), "red")
                second = Image.new("RGB", (16, 16), "blue")
                first.save(
                    output,
                    format=image_format,
                    save_all=True,
                    append_images=[second],
                    duration=100,
                )
                self.rejected(f"animated-{image_format}.bin", output.getvalue())

    def test_appended_payloads_are_rejected(self) -> None:
        for image_format in ("JPEG", "PNG", "WEBP"):
            with self.subTest(image_format=image_format):
                self.rejected(
                    f"polyglot-{image_format}.bin",
                    self.image(image_format) + b"<html>synthetic</html>",
                )

    def test_exact_file_limit_is_accepted_and_one_more_is_too_large(self) -> None:
        base = self.image("PNG", (1, 1))
        iend = base.rfind(b"\x00\x00\x00\x00IEND")
        self.assertGreater(iend, 0)
        padding_size = MAX_FILE_BYTES - len(base) - 12
        exact = base[:iend] + _png_chunk(b"faKe", b"x" * padding_size) + base[iend:]
        self.assertEqual(len(exact), MAX_FILE_BYTES)
        result = verify(self.write("exact-limit.png", exact))
        self.assertEqual(result["size_bytes"], MAX_FILE_BYTES)
        with self.assertRaises(MediaValidationError) as raised:
            verify(self.write("over-limit.png", exact + b"x"))
        self.assertEqual(raised.exception.code, "media_too_large")

    def test_dimension_limit_and_pixel_limit(self) -> None:
        allowed = verify(self.write("dimension-edge.png", self.image("PNG", (MAX_DIMENSION, 1))))
        self.assertEqual(allowed["width"], MAX_DIMENSION)
        self.rejected(
            "dimension-over.png",
            self.image("PNG", (MAX_DIMENSION + 1, 1)),
            "media_too_large",
        )
        self.assertEqual(MAX_PIXELS, 4000 * 4000)
        allowed_pixels = verify(self.write("pixel-edge.png", self.image("PNG", (4000, 4000))))
        self.assertEqual(allowed_pixels["width"] * allowed_pixels["height"], MAX_PIXELS)
        self.rejected("pixel-bomb.png", self.image("PNG", (4001, 4000)), "media_too_large")

    def test_declared_decompression_bomb_is_quietly_rejected(self) -> None:
        content = bytearray(self.image("PNG", (1, 1)))
        content[16:20] = (20_000).to_bytes(4, "big")
        content[20:24] = (20_000).to_bytes(4, "big")
        content[29:33] = zlib.crc32(content[12:29]).to_bytes(4, "big")
        with warnings.catch_warnings(record=True) as emitted:
            self.rejected("declared-bomb.png", bytes(content), "media_too_large")
        self.assertEqual(emitted, [])

    def test_exif_is_not_transformed_or_removed(self) -> None:
        content = self.image("JPEG", exif=b"Exif\x00\x00synthetic-metadata")
        target = self.write("metadata.jpg", content)
        before = target.read_bytes()
        result = verify(target)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(result["sha256"], hashlib.sha256(before).hexdigest())

    def test_pillow_globals_are_not_mutated(self) -> None:
        max_pixels = Image.MAX_IMAGE_PIXELS
        truncated = ImageFile.LOAD_TRUNCATED_IMAGES
        verify(self.write("globals.png", self.image("PNG")))
        self.assertEqual(Image.MAX_IMAGE_PIXELS, max_pixels)
        self.assertEqual(ImageFile.LOAD_TRUNCATED_IMAGES, truncated)


if __name__ == "__main__":
    unittest.main()
