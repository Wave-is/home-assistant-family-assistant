/* Authenticated, bounded client helpers for private Family Assistant images. */

const SEGMENT = /^[A-Za-z0-9_-]{1,128}$/;
const MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_BYTES = 10 * 1024 * 1024;
const MAX_RECEIPT_BYTES = 64 * 1024;
const MAX_REVISION = Number.MAX_SAFE_INTEGER;

class MediaClientError extends Error {
  constructor(code) {
    super(code);
    this.name = "MediaClientError";
    this.code = code;
  }
}

function fail(code) {
  throw new MediaClientError(code);
}

function validateCommon(hass, { entryId, id, revision, signal, isCurrent } = {}) {
  if (
    typeof entryId !== "string" ||
    typeof id !== "string" ||
    !SEGMENT.test(entryId) ||
    !SEGMENT.test(id)
  )
    fail("media_invalid");
  if (!Number.isSafeInteger(revision) || revision < 1 || revision > MAX_REVISION)
    fail("media_invalid");
  if (typeof isCurrent !== "function") fail("media_invalid");
  if (
    signal !== undefined &&
    signal !== null &&
    (typeof signal !== "object" ||
      typeof signal.aborted !== "boolean" ||
      typeof signal.addEventListener !== "function" ||
      typeof signal.removeEventListener !== "function")
  )
    fail("media_invalid");
  if (!hass || typeof hass.fetchWithAuth !== "function") fail("media_unavailable");
  return {
    url: `/api/family_assistant/media/${entryId}/${id}`,
    id,
    revision,
    signal: signal ?? undefined,
    isCurrent,
  };
}

function current(check) {
  try {
    if (check() === true) return;
  } catch {
    // A throwing guard is indistinguishable from revoked access.
  }
  fail("forbidden");
}

function statusError(response) {
  if ([401, 403, 404].includes(response.status)) return "forbidden";
  if (response.status === 409) return "conflict";
  if (response.status === 413) return "media_too_large";
  if ([400, 405, 415, 422].includes(response.status)) return "media_invalid";
  return "media_unavailable";
}

async function request(hass, scope, init) {
  current(scope.isCurrent);
  if (scope.signal?.aborted) fail("media_unavailable");
  let response;
  try {
    response = await hass.fetchWithAuth(scope.url, {
      ...init,
      signal: scope.signal,
      cache: "no-store",
      redirect: "error",
    });
  } catch {
    current(scope.isCurrent);
    fail("media_unavailable");
  }
  current(scope.isCurrent);
  if (!response || typeof response !== "object" || response.redirected === true)
    fail("media_unavailable");
  if (response.ok !== true) fail(statusError(response));
  return response;
}

async function cancel(reader) {
  try {
    await reader.cancel();
  } catch {
    // Cancellation is best effort; callers still receive only a fixed error.
  }
}

async function boundedBody(
  response,
  limit,
  scope,
  overflowCode = "media_too_large",
) {
  let reader;
  try {
    reader = response?.body?.getReader?.();
  } catch {
    fail("media_unavailable");
  }
  if (!reader || typeof reader.read !== "function") fail("media_unavailable");
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      current(scope.isCurrent);
      const part = await reader.read();
      current(scope.isCurrent);
      if (!part || typeof part.done !== "boolean") fail("media_unavailable");
      if (part.done) break;
      if (!ArrayBuffer.isView(part.value)) fail("media_unavailable");
      const bytes = new Uint8Array(
        part.value.buffer,
        part.value.byteOffset,
        part.value.byteLength,
      );
      total += bytes.byteLength;
      if (total > limit) {
        await cancel(reader);
        fail(overflowCode);
      }
      chunks.push(bytes.slice());
    }
  } catch (error) {
    if (error instanceof MediaClientError) {
      await cancel(reader);
      throw error;
    }
    current(scope.isCurrent);
    fail("media_unavailable");
  } finally {
    try {
      reader.releaseLock?.();
    } catch {
      // Never surface stream implementation details.
    }
  }
  current(scope.isCurrent);
  return { chunks, total };
}

function header(response, name) {
  try {
    const value = response.headers?.get?.(name);
    if (value === null || value === undefined) return null;
    if (typeof value !== "string") fail("media_invalid");
    return value;
  } catch (error) {
    if (error instanceof MediaClientError) throw error;
    fail("media_unavailable");
  }
}

function contentLength(response) {
  const value = header(response, "content-length");
  if (value === null || value === undefined || value === "") return null;
  if (!/^\d+$/.test(value)) fail("media_invalid");
  const result = Number(value);
  if (!Number.isSafeInteger(result)) fail("media_too_large");
  if (result > MAX_BYTES) fail("media_too_large");
  if (result === 0) fail("media_invalid");
  return result;
}

export async function uploadMedia(hass, options) {
  const scope = validateCommon(hass, options);
  const file = options?.file;
  if (typeof Blob === "undefined" || !(file instanceof Blob)) fail("media_invalid");
  if (!Number.isSafeInteger(file.size) || file.size === 0) fail("media_invalid");
  if (file.size > MAX_BYTES) fail("media_too_large");
  if (!MIME_TYPES.has(file.type)) fail("media_invalid");

  const response = await request(hass, scope, {
    method: "PUT",
    headers: {
      "Content-Type": file.type,
      "X-Family-Media-Revision": String(scope.revision),
    },
    body: file,
  });
  const body = await boundedBody(response, MAX_RECEIPT_BYTES, scope);
  if (body.total === 0) fail("media_invalid");
  const combined = new Uint8Array(body.total);
  let offset = 0;
  for (const chunk of body.chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  let receipt;
  try {
    receipt = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(combined));
  } catch {
    fail("media_invalid");
  }
  current(scope.isCurrent);
  if (
    !receipt ||
    typeof receipt !== "object" ||
    Array.isArray(receipt) ||
    JSON.stringify(Object.keys(receipt).sort()) !==
      JSON.stringify(["id", "revision", "status"]) ||
    receipt.id !== scope.id ||
    receipt.revision !== scope.revision + 1 ||
    receipt.status !== "available"
  )
    fail("media_invalid");
  return receipt;
}

export async function downloadMedia(hass, options) {
  const scope = validateCommon(hass, options);
  const response = await request(hass, scope, {
    method: "GET",
    headers: {
      "X-Family-Media-Revision": String(scope.revision),
    },
  });
  const mimeType = header(response, "content-type");
  if (!MIME_TYPES.has(mimeType)) fail("media_invalid");
  const expectedLength = contentLength(response);
  const body = await boundedBody(
    response,
    expectedLength ?? MAX_BYTES,
    scope,
    expectedLength === null ? "media_too_large" : "media_invalid",
  );
  if (body.total === 0) fail("media_invalid");
  if (expectedLength !== null && expectedLength !== body.total) fail("media_invalid");
  current(scope.isCurrent);
  return new Blob(body.chunks, { type: mimeType });
}
