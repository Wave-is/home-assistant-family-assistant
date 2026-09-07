"""Decoder process ownership with deterministic delayed synthetic processes."""

import asyncio
from pathlib import Path

import pytest

from custom_components.family_assistant import media_storage
from custom_components.family_assistant.domain.validation import DomainError


class Process:
    def __init__(self, chunks=()):
        self.chunks = iter(chunks)
        self.stdout = self
        self.returncode = None
        self.killed = asyncio.Event()
        self.reaped = asyncio.Event()
        self.reading = asyncio.Event()
        self.release_read = asyncio.Event()
        self.release_wait = asyncio.Event()
        self.block_read = False
        self.block_wait = False

    async def read(self, size):
        self.reading.set()
        if self.block_read:
            await self.release_read.wait()
        return next(self.chunks, b"")

    def kill(self):
        self.killed.set()
        self.returncode = -9

    async def wait(self):
        if self.block_wait:
            await self.release_wait.wait()
        self.returncode = self.returncode if self.returncode is not None else 0
        self.reaped.set()
        return self.returncode


def install(monkeypatch, process):
    async def spawn(*args, **kwargs):
        assert "-I" in args
        assert args[-2].endswith("media_validation.py")
        assert kwargs["stderr"] == asyncio.subprocess.DEVNULL
        return process

    monkeypatch.setattr(media_storage.asyncio, "create_subprocess_exec", spawn)


@pytest.mark.asyncio
async def test_decoder_accumulates_partial_stdout_to_eof(monkeypatch):
    process = Process([b'{"ok":', b'true,"result":', b'{"mime_type":"image/png"}}'])
    install(monkeypatch, process)
    assert await media_storage.decode_file(Path("synthetic")) == {"mime_type": "image/png"}
    assert process.reaped.is_set()


@pytest.mark.asyncio
async def test_decoder_oversized_output_is_killed_and_reaped(monkeypatch):
    process = Process([b"x" * 4097])
    install(monkeypatch, process)
    with pytest.raises(DomainError, match="media_invalid"):
        await media_storage.decode_file(Path("synthetic"))
    assert process.killed.is_set() and process.reaped.is_set()


@pytest.mark.asyncio
async def test_decoder_double_cancel_waits_for_reap(monkeypatch):
    process = Process()
    process.block_read = process.block_wait = True
    install(monkeypatch, process)
    task = asyncio.create_task(media_storage.decode_file(Path("synthetic")))
    await process.reading.wait()
    task.cancel()
    await process.killed.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    process.release_wait.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.reaped.is_set()


@pytest.mark.asyncio
async def test_cancel_during_spawn_still_owns_and_reaps_process(monkeypatch):
    process = Process()
    spawning, release = asyncio.Event(), asyncio.Event()

    async def spawn(*_args, **_kwargs):
        spawning.set()
        await release.wait()
        return process

    monkeypatch.setattr(media_storage.asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(media_storage.decode_file(Path("synthetic")))
    await spawning.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed.is_set() and process.reaped.is_set()
