"""Entry-private generated image files, using the existing isolated decoder."""

from pathlib import Path

from ..domain.validation import DomainError
from ..media_storage import (
    _cleanup,
    _io,
    _publish,
    _read,
    _sync_close,
    _temporary,
    _unlink_blob,
    decode_file,
)
from .image_providers import MAX_BYTES, MIMES


class ImageFiles:
    def __init__(self, root, *, decoder=decode_file):
        self.root, self.decoder = Path(root), decoder

    async def put(self, key, data, mime, *, guard):
        guard()
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES or mime not in MIMES:
            raise DomainError("image_invalid")
        stream = temporary = None
        try:
            stream, temporary = await _io(_temporary, self.root, on_cancel=_cleanup)
            await _io(stream.write, data)
            await _io(_sync_close, stream)
            guard()
            result = await self.decoder(temporary)
            guard()
            if (
                result.get("mime_type") != mime
                or not 1 <= result.get("width", 0) <= 1024
                or not 1 <= result.get("height", 0) <= 1024
                or result.get("size_bytes") != len(data)
            ):
                raise DomainError("image_invalid")
            await _io(_publish, self.root, temporary, key, result)
            guard()
            return result
        finally:
            if stream is not None or temporary is not None:
                await _io(_cleanup, stream, temporary)

    async def get(self, key):
        return await _io(_read, self.root, key)

    async def remove(self, key):
        await _io(_unlink_blob, self.root, key)
