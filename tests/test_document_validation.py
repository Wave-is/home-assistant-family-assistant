"""Synthetic restricted PDFs; no household documents or file input providers."""

import hashlib
import io
import logging

import pytest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject

from custom_components.family_assistant.media_validation import MediaValidationError, verify


def document(*, pages=1, mutate=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if mutate:
        mutate(writer)
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def checked(tmp_path, content, *, enabled=True):
    path = tmp_path / "synthetic.bin"
    path.write_bytes(content)
    return verify(path, allow_pdf=enabled)


def test_valid_pdf_exact_metadata_and_image_lane_denial(tmp_path):
    content = document()
    assert checked(tmp_path, content) == {
        "mime_type": "application/pdf",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "pages": 1,
    }
    with pytest.raises(MediaValidationError):
        checked(tmp_path, content, enabled=False)


@pytest.mark.parametrize(
    "change",
    [
        lambda w: w.add_js("app.alert('synthetic')"),
        lambda w: w.add_attachment("synthetic.txt", b"synthetic"),
        lambda w: w.encrypt("synthetic-only"),
        lambda w: w._root_object.update({NameObject("/AcroForm"): DictionaryObject()}),
        lambda w: w.pages[0].update({NameObject("/AA"): DictionaryObject()}),
        lambda w: w._root_object.update(
            {
                NameObject("/OpenAction"): DictionaryObject(
                    {
                        NameObject("/S"): NameObject("/Launch"),
                        NameObject("/F"): TextStringObject("synthetic"),
                    }
                )
            }
        ),
    ],
)
def test_active_or_encrypted_documents_rejected(tmp_path, change):
    with pytest.raises(MediaValidationError) as error:
        checked(tmp_path, document(mutate=change))
    assert str(error.value) == "media_invalid"


@pytest.mark.parametrize(
    "content", [b"%PDF-1.4\n%%EOF", b"<html>synthetic</html>", b"", b"%PDF-1.7\ntruncated"]
)
def test_malformed_documents_rejected(tmp_path, content):
    with pytest.raises(MediaValidationError):
        checked(tmp_path, content)


def test_page_limit_and_appended_payload(tmp_path):
    with pytest.raises(MediaValidationError, match="media_too_large"):
        checked(tmp_path, document(pages=101))
    with pytest.raises(MediaValidationError, match="media_invalid"):
        checked(tmp_path, document() + b"<script>synthetic</script>")


def test_unrelated_text_is_not_treated_as_executable_action(tmp_path):
    content = document(mutate=lambda w: w.add_metadata({"/Title": "JavaScript /Launch manual"}))
    assert checked(tmp_path, content)["pages"] == 1


def test_graph_depth_is_bounded(tmp_path):
    def change(writer):
        value = DictionaryObject()
        for _ in range(70):
            value = DictionaryObject({NameObject("/Synthetic"): value})
        writer._root_object[NameObject("/Synthetic")] = value

    with pytest.raises(MediaValidationError, match="media_too_large"):
        checked(tmp_path, document(mutate=change))


def test_graph_width_is_bounded(tmp_path):
    def change(writer):
        writer._root_object[NameObject("/Synthetic")] = ArrayObject(
            [NumberObject(0) for _ in range(20_001)]
        )

    with pytest.raises(MediaValidationError, match="media_too_large"):
        checked(tmp_path, document(mutate=change))


def test_parser_logging_threshold_restored_after_success_and_rejection(tmp_path):
    previous = logging.root.manager.disable
    try:
        logging.disable(logging.WARNING)
        checked(tmp_path, document())
        assert logging.root.manager.disable == logging.WARNING
        with pytest.raises(MediaValidationError):
            checked(tmp_path, document(mutate=lambda w: w.add_js("synthetic")))
        assert logging.root.manager.disable == logging.WARNING
    finally:
        logging.disable(previous)
