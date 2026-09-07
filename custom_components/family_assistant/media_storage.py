"""Bounded private blob I/O; family authority remains in the domain Engine.

Files live outside static frontend paths. A verified temporary file is published
without overwriting an existing blob, then its metadata is persisted. A Store
failure leaves a recoverable reservation/blob pair for the exact upload retry.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import AsyncIterable, Awaitable, Callable
from datetime import datetime
from pathlib import Path

from .domain import media
from .domain.validation import DomainError
from .domain.validation import revision as strict_revision

MAX_IO = 2
MAX_CHUNK = 256 * 1024
BLOB_KEY = re.compile(r"[0-9a-f]{64}")


def _directory(root: Path) -> None:
    if root.is_symlink() or root.resolve() != root.absolute():
        raise DomainError("media_unavailable")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or root.resolve() != root.absolute() or not root.is_dir():
        raise DomainError("media_unavailable")


def _path(root: Path, key: str) -> Path:
    if not isinstance(key, str) or not BLOB_KEY.fullmatch(key):
        raise DomainError("media_unavailable")
    if root.is_symlink() or root.resolve() != root.absolute():
        raise DomainError("media_unavailable")
    return root / key


def _read(root: Path, key: str) -> bytes:
    path = _path(root, key)
    if path.is_symlink():
        raise DomainError("media_unavailable")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise DomainError("media_unavailable")
        if not 0 < info.st_size <= media.MAX_FILE_BYTES:
            raise DomainError("media_unavailable")
        content = stream.read(media.MAX_FILE_BYTES + 1)
        if len(content) != info.st_size:
            raise DomainError("media_unavailable")
        return content


def _publish(root: Path, temporary: Path, key: str, metadata: dict) -> None:
    destination = _path(root, key)
    try:
        # Hard-link publication is atomic and exclusive on the private filesystem.
        # Never replace another file, even a residue of a failed earlier request.
        os.link(temporary, destination, follow_symlinks=False)
    except FileExistsError:
        content = _read(root, key)
        if (
            len(content) != metadata["size_bytes"]
            or hashlib.sha256(content).hexdigest() != metadata["sha256"]
        ):
            raise DomainError("conflict") from None
    else:
        temporary.unlink()
    _sync_directory(root)


def _sync_directory(root: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _unlink_blob(root: Path, key: str) -> None:
    path = _path(root, key)
    if path.is_symlink():
        raise DomainError("media_unavailable")
    try:
        info = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise DomainError("media_unavailable")
    path.unlink()
    _sync_directory(root)


def _temporary(root: Path):
    _directory(root)
    descriptor, name = tempfile.mkstemp(prefix=".upload-", dir=root)
    return os.fdopen(descriptor, "wb"), Path(name)


def _sync_close(stream) -> None:
    stream.flush()
    os.fsync(stream.fileno())
    stream.close()


def _cleanup(stream, path: Path | None) -> None:
    if stream is not None and not stream.closed:
        stream.close()
    if path is not None:
        path.unlink(missing_ok=True)


async def _io(function, *args, on_cancel=None):
    """Cancellation cannot release ownership while filesystem work still runs."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled() and task.exception() is None and on_cancel:
            try:
                await _io(on_cancel, *task.result())
            except OSError:
                pass
        raise


async def _guard(callback):
    try:
        await callback()
    except OSError:
        raise DomainError("media_unavailable") from None


async def _settle(task):
    """Drain an owned task even if shutdown repeats cancellation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    return task.result()


async def _reap(process):
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    task = asyncio.create_task(process.wait())
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await _settle(task)
        raise


async def decode_file(path: Path) -> dict:
    """Run only our fixed local decoder, with a bounded wall time and response."""
    worker = Path(__file__).with_name("media_validation.py")
    spawning = asyncio.create_task(
        asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(worker),
            str(path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    )
    try:
        process = await asyncio.shield(spawning)
    except asyncio.CancelledError:
        try:
            process = await _settle(spawning)
            await _reap(process)
        except OSError:
            pass
        raise
    try:
        async with asyncio.timeout(8):
            output = bytearray()
            while True:
                chunk = await process.stdout.read(4097 - len(output))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > 4096:
                    raise DomainError("media_invalid")
            await process.wait()
        result = json.loads(output)
        if not isinstance(result, dict) or result.get("ok") is not True:
            code = result.get("code") if isinstance(result, dict) else None
            raise DomainError(
                code if code in {"media_invalid", "media_too_large"} else "media_invalid"
            )
        if process.returncode != 0:
            raise DomainError("media_invalid")
        metadata = result.get("result")
        if not isinstance(metadata, dict):
            raise DomainError("media_invalid")
        return metadata
    except (TimeoutError, ValueError, TypeError):
        raise DomainError("media_invalid") from None
    finally:
        if process.returncode is None:
            await _reap(process)


class MediaStorage:
    """One entry-private directory, no network or household-service operations."""

    def __init__(
        self,
        engine,
        root: Path,
        clock: Callable[[], datetime],
        *,
        decoder: Callable[[Path], Awaitable[dict]] = decode_file,
    ):
        self.engine, self.root, self.clock = engine, Path(root), clock
        self.decoder = decoder
        self._busy = set()
        self._active = 0
        self._stopped = False
        self._collecting = False

    def _record(self, user_id, media_id, revision, *, upload=False):
        if self._stopped:
            raise DomainError("media_unavailable")
        revision = strict_revision(revision)
        actor_id = self.engine.actor_for_ha(user_id)
        state = self.engine.snapshot()
        record = media.authorize_blob(state, state["members"][actor_id], media_id, self.clock())
        if upload:
            expected = record["revision"] - (record["status"] == "available")
            if record["status"] not in media.PENDING or expected != revision:
                raise DomainError("conflict")
        elif record["status"] not in {"available", "attached"} or record["revision"] != revision:
            raise DomainError("conflict")
        # Domain authorization already validates the opaque key. Filesystem
        # canonicality checks belong to _read/_publish/_temporary worker threads.
        return actor_id, record

    async def put(
        self,
        user_id: str,
        media_id: str,
        revision: int,
        chunks: AsyncIterable[bytes],
        *,
        guard: Callable[[], Awaitable[None]],
    ) -> dict:
        """Stream, verify, publish and persist one exact authorized upload."""
        await _guard(guard)
        _, original = self._record(user_id, media_id, revision, upload=True)
        if self._active >= MAX_IO or media_id in self._busy:
            raise DomainError("media_unavailable")
        self._active += 1
        self._busy.add(media_id)
        stream = temporary = None
        try:
            stream, temporary = await _io(_temporary, self.root, on_cancel=_cleanup)
            total = 0
            digest = hashlib.sha256()
            async with asyncio.timeout(45):
                async for chunk in chunks:
                    await _guard(guard)
                    self._record(user_id, media_id, revision, upload=True)
                    if not isinstance(chunk, bytes) or len(chunk) > MAX_CHUNK:
                        raise DomainError("media_invalid")
                    total += len(chunk)
                    if total > media.MAX_FILE_BYTES:
                        raise DomainError("media_too_large")
                    digest.update(chunk)
                    await _io(stream.write, chunk)
            if not total:
                raise DomainError("media_invalid")
            await _io(_sync_close, stream)
            verified = await self.decoder(temporary)
            if verified.get("size_bytes") != total or verified.get("sha256") != digest.hexdigest():
                raise DomainError("media_invalid")
            if verified.get("mime_type") not in media.MIME_TYPES:
                raise DomainError("media_invalid")
            await _guard(guard)
            self._record(user_id, media_id, revision, upload=True)
            await _io(_publish, self.root, temporary, original["blob_key"], verified)
            await _guard(guard)

            def finalize(ctx):
                actor = self.engine.actor_for_ha(user_id)
                ctx.now = self.clock()
                return media.finalize(
                    ctx,
                    actor,
                    media_id,
                    revision,
                    verified["mime_type"],
                    total,
                    verified["sha256"],
                )

            receipt = await self.engine.system_update("media_verified", self.clock(), finalize)
            await _guard(guard)
            self._record(user_id, media_id, revision, upload=True)
            return receipt
        except (OSError, TimeoutError):
            raise DomainError("media_unavailable") from None
        finally:
            failed = sys.exc_info()[0] is not None
            try:
                await _io(_cleanup, stream, temporary)
            except OSError:
                if not failed:
                    raise DomainError("media_unavailable") from None
            finally:
                self._busy.discard(media_id)
                self._active -= 1

    async def get(
        self,
        user_id: str,
        media_id: str,
        revision: int,
        *,
        guard: Callable[[], Awaitable[None]],
    ) -> tuple[dict, bytes]:
        """Verify exact bytes before the HTTP adapter commits private headers."""
        await _guard(guard)
        _, original = self._record(user_id, media_id, revision)
        if self._active >= MAX_IO:
            raise DomainError("media_unavailable")
        self._active += 1
        try:
            content = await _io(_read, self.root, original["blob_key"])
            if (
                len(content) != original["size_bytes"]
                or hashlib.sha256(content).hexdigest() != original["sha256"]
            ):
                raise DomainError("media_unavailable")
            await _guard(guard)
            _, current = self._record(user_id, media_id, revision)
            if current != original:
                raise DomainError("conflict")
            public = {key: current[key] for key in media.PUBLIC_FIELDS}
            return public, content
        except OSError:
            raise DomainError("media_unavailable") from None
        finally:
            self._active -= 1

    async def stop(self) -> None:
        self._stopped = True
        while self._active:
            await asyncio.sleep(0.05)

    async def collect(self) -> None:
        """Resume two-phase expiry without touching attached report history."""
        if self._stopped or self._collecting or self._active >= MAX_IO:
            return
        self._collecting = True
        self._active += 1
        try:
            state = self.engine.snapshot()
            count = 0
            for media_id, record in state.get("media", {}).items():
                if self._stopped or count >= 100:
                    break
                if media_id in self._busy or record.get("status") not in {
                    *media.PENDING,
                    "deleting",
                }:
                    continue
                if record["status"] in media.PENDING:
                    from .domain.validation import timestamp

                    if timestamp(record.get("expires_at"), "expires_at") > self.clock():
                        continue
                self._busy.add(media_id)
                try:
                    if record["status"] == "deleting":
                        receipt = record
                    else:

                        def begin(ctx, media_id=media_id, revision=record["revision"]):
                            ctx.now = self.clock()
                            return media.expire_pending(ctx, media_id, revision)

                        receipt = await self.engine.system_update(
                            "media_expired", self.clock(), begin
                        )
                    key = media.deleting_blob(self.engine.snapshot(), media_id, receipt["revision"])
                    await _io(_unlink_blob, self.root, key)

                    def finish(ctx, media_id=media_id, revision=receipt["revision"]):
                        ctx.now = self.clock()
                        return media.finish_delete(ctx, media_id, revision)

                    await self.engine.system_update("media_deleted", self.clock(), finish)
                    count += 1
                finally:
                    self._busy.discard(media_id)
        except OSError:
            raise DomainError("media_unavailable") from None
        finally:
            self._active -= 1
            self._collecting = False
