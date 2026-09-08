import assert from "node:assert/strict";
import { test } from "node:test";

import {
  downloadMedia,
  uploadMedia,
  uploadDocument,
  downloadDocument,
} from "../custom_components/family_assistant/frontend/media-client.js";

const MAX_BYTES = 10 * 1024 * 1024;

test("document helpers accept PDF without broadening image consumers",async()=>{
  const file=new Blob(["synthetic pdf"],{type:"application/pdf"});
  const upload=client(jsonResponse({id:"M_RANDOM-987",revision:6,status:"available"}));
  await rejectsCode(uploadMedia(upload.hass,options({file,allowPdf:true})),"media_invalid");
  assert.equal(upload.calls.length,0);
  assert.equal((await uploadDocument(upload.hass,options({file}))).status,"available");
  const downloaded=client(imageResponse("synthetic pdf","application/pdf"));
  assert.equal((await downloadDocument(downloaded.hass,options())).type,"application/pdf");
  const image=client(imageResponse("synthetic pdf","application/pdf"));
  await rejectsCode(downloadMedia(image.hass,options({allowPdf:true})),"media_invalid");
});

function jsonResponse(value, init = {}) {
  return new Response(JSON.stringify(value), {
    status: init.status || 200,
    headers: { "content-type": "application/json", ...(init.headers || {}) },
  });
}

function imageResponse(bytes, type = "image/png", init = {}) {
  return new Response(bytes, {
    status: init.status || 200,
    headers: { "content-type": type, ...(init.headers || {}) },
  });
}

function client(response) {
  const calls = [];
  return {
    calls,
    hass: {
      async fetchWithAuth(path, init) {
        calls.push({ path, init });
        return typeof response === "function" ? response(path, init) : response;
      },
    },
  };
}

function options(changes = {}) {
  return {
    entryId: "entry_ABC-123",
    id: "M_RANDOM-987",
    revision: 5,
    isCurrent: () => true,
    ...changes,
  };
}

async function rejectsCode(promise, code) {
  await assert.rejects(promise, (error) => {
    assert.equal(error?.code, code);
    assert.equal(error?.message, code);
    assert.equal(error?.name, "MediaClientError");
    return true;
  });
}

test("upload uses only the authenticated HA helper and accepts the exact opaque +1 receipt", async () => {
  const receipt = { id: "M_RANDOM-987", revision: 6, status: "available" };
  const { hass, calls } = client(jsonResponse(receipt));
  const signal = new AbortController().signal;
  const file = new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], {
    type: "image/png",
  });

  assert.deepEqual(
    await uploadMedia(hass, options({ file, signal })),
    receipt,
  );
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].path,
    "/api/family_assistant/media/entry_ABC-123/M_RANDOM-987",
  );
  assert.equal(calls[0].init.method, "PUT");
  assert.equal(calls[0].init.body, file);
  assert.equal(calls[0].init.signal, signal);
  assert.equal(calls[0].init.cache, "no-store");
  assert.equal(calls[0].init.redirect, "error");
  assert.deepEqual(calls[0].init.headers, {
    "Content-Type": "image/png",
    "X-Family-Media-Revision": "5",
  });
  assert.equal(Object.hasOwn(calls[0].init, "credentials"), false);
  assert.equal(
    Object.keys(calls[0].init.headers).some(
      (name) => name.toLowerCase() === "authorization",
    ),
    false,
  );
});

test("download sends the exact revision through the authenticated helper", async () => {
  for (const type of ["image/jpeg", "image/png", "image/webp"]) {
    const bytes = new Uint8Array([1, 2, 3, 4]);
    const { hass, calls } = client(
      imageResponse(bytes, type, { headers: { "content-length": "4" } }),
    );
    const blob = await downloadMedia(hass, options());
    assert.equal(blob.type, type);
    assert.equal(blob.size, 4);
    assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes);
    assert.deepEqual(calls[0], {
      path: "/api/family_assistant/media/entry_ABC-123/M_RANDOM-987",
      init: {
        method: "GET",
        headers: { "X-Family-Media-Revision": "5" },
        signal: undefined,
        cache: "no-store",
        redirect: "error",
      },
    });
    assert.equal(
      Object.keys(calls[0].init.headers).some(
        (name) => name.toLowerCase() === "authorization",
      ),
      false,
    );
  }
});

test("strict local segments, revisions, guard, signal, and blob shape fail before network", async () => {
  const { hass, calls } = client(jsonResponse({}));
  const invalidCases = [
    options({ entryId: "" }),
    options({ entryId: "../entry" }),
    options({ entryId: "entry%2Fother" }),
    options({ entryId: "é" }),
    options({ entryId: "x".repeat(129) }),
    options({ id: "/absolute" }),
    options({ id: "a\\b" }),
    options({ id: 7 }),
    options({ revision: 0 }),
    options({ revision: true }),
    options({ revision: 1.5 }),
    options({ revision: Number.MAX_SAFE_INTEGER + 1 }),
    options({ isCurrent: null }),
    options({ signal: {} }),
  ];
  for (const invalid of invalidCases)
    await rejectsCode(downloadMedia(hass, invalid), "media_invalid");
  await rejectsCode(
    uploadMedia(hass, options({ file: new Blob([], { type: "image/png" }) })),
    "media_invalid",
  );
  await rejectsCode(
    uploadMedia(
      hass,
      options({ file: new Blob([new Uint8Array(MAX_BYTES + 1)], { type: "image/png" }) }),
    ),
    "media_too_large",
  );
  for (const type of ["", "image/svg+xml", "text/html", "application/pdf"])
    await rejectsCode(
      uploadMedia(hass, options({ file: new Blob([1], { type }) })),
      "media_invalid",
    );
  assert.equal(calls.length, 0);
});

test("exactly 10 MiB is accepted for upload while the MIME remains only a request hint", async () => {
  const { hass, calls } = client(
    jsonResponse({ id: "M_RANDOM-987", revision: 6, status: "available" }),
  );
  const file = new Blob([new Uint8Array(MAX_BYTES)], { type: "image/webp" });
  const receipt = await uploadMedia(hass, options({ file }));
  assert.equal(receipt.status, "available");
  assert.equal(calls[0].init.headers["Content-Type"], "image/webp");
  assert.equal(calls[0].init.body.size, MAX_BYTES);
});

test("upload receipt must be exact, bounded, same-ID, available, and revision +1", async () => {
  const file = new Blob([1], { type: "image/jpeg" });
  const invalid = [
    { id: "M_RANDOM-987", revision: 5, status: "available" },
    { id: "OTHER", revision: 6, status: "available" },
    { id: "M_RANDOM-987", revision: 6, status: "reserved" },
    { id: "M_RANDOM-987", revision: 6, status: "available", extra: true },
    { id: "M_RANDOM-987", revision: "6", status: "available" },
    { id: { private: "value" }, revision: 6, status: "available" },
    ["M_RANDOM-987", 6, "available"],
    null,
  ];
  for (const receipt of invalid) {
    const { hass } = client(jsonResponse(receipt));
    await rejectsCode(uploadMedia(hass, options({ file })), "media_invalid");
  }
  const malformed = client(new Response("SERVER-PRIVATE-TRACE"));
  await rejectsCode(
    uploadMedia(malformed.hass, options({ file })),
    "media_invalid",
  );
  const oversized = client(new Response(`"${"x".repeat(64 * 1024)}"`));
  await rejectsCode(
    uploadMedia(oversized.hass, options({ file })),
    "media_too_large",
  );
});

test("download rejects disallowed, empty, lying, and oversized bodies without returning bytes", async () => {
  for (const type of [
    "",
    "text/html",
    "image/svg+xml",
    "application/pdf",
    "image/png; charset=utf-8",
    "IMAGE/PNG",
  ]) {
    const { hass } = client(imageResponse(new Uint8Array([1]), type));
    await rejectsCode(downloadMedia(hass, options()), "media_invalid");
  }
  await rejectsCode(
    downloadMedia(client(imageResponse(new Uint8Array(), "image/png")).hass, options()),
    "media_invalid",
  );
  await rejectsCode(
    downloadMedia(
      client(
        imageResponse(new Uint8Array([1, 2]), "image/png", {
          headers: { "content-length": "3" },
        }),
      ).hass,
      options(),
    ),
    "media_invalid",
  );
  await rejectsCode(
    downloadMedia(
      client(
        imageResponse(new Uint8Array([1, 2]), "image/png", {
          headers: { "content-length": "1" },
        }),
      ).hass,
      options(),
    ),
    "media_invalid",
  );
  await rejectsCode(
    downloadMedia(
      client(
        imageResponse(new Uint8Array([1]), "image/png", {
          headers: { "content-length": String(MAX_BYTES + 1) },
        }),
      ).hass,
      options(),
    ),
    "media_too_large",
  );
  const streamedOversize = new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array(MAX_BYTES));
      controller.enqueue(new Uint8Array([1]));
      controller.close();
    },
  });
  await rejectsCode(
    downloadMedia(
      client(new Response(streamedOversize, { headers: { "content-type": "image/webp" } })).hass,
      options(),
    ),
    "media_too_large",
  );
});

test("identity drift before request, after response, and during a deferred body is generic forbidden", async () => {
  let current = false;
  const before = client(imageResponse(new Uint8Array([1]), "image/png"));
  await rejectsCode(
    downloadMedia(before.hass, options({ isCurrent: () => current })),
    "forbidden",
  );
  assert.equal(before.calls.length, 0);

  let resolveResponse;
  current = true;
  const after = client(
    () =>
      new Promise((resolve) => {
        resolveResponse = resolve;
      }),
  );
  const afterPromise = downloadMedia(
    after.hass,
    options({ isCurrent: () => current }),
  );
  await Promise.resolve();
  current = false;
  resolveResponse(imageResponse(new Uint8Array([9]), "image/png"));
  await rejectsCode(afterPromise, "forbidden");

  let releaseBody;
  current = true;
  const deferred = new ReadableStream({
    start(controller) {
      releaseBody = () => {
        controller.enqueue(new Uint8Array([7, 8, 9]));
        controller.close();
      };
    },
  });
  const duringPromise = downloadMedia(
    client(new Response(deferred, { headers: { "content-type": "image/jpeg" } })).hass,
    options({ isCurrent: () => current }),
  );
  await Promise.resolve();
  current = false;
  releaseBody();
  await rejectsCode(duringPromise, "forbidden");

  let uploadChecks = 0;
  const upload = client(
    jsonResponse({ id: "M_RANDOM-987", revision: 6, status: "available" }),
  );
  await rejectsCode(
    uploadMedia(
      upload.hass,
      options({
        file: new Blob([1], { type: "image/png" }),
        isCurrent: () => {
          uploadChecks += 1;
          return uploadChecks < 8;
        },
      }),
    ),
    "forbidden",
  );

  let downloadChecks = 0;
  await rejectsCode(
    downloadMedia(
      client(imageResponse(new Uint8Array([1]), "image/png")).hass,
      options({
        isCurrent: () => {
          downloadChecks += 1;
          return downloadChecks < 7;
        },
      }),
    ),
    "forbidden",
  );
});

test("HTTP, redirect, network, body, and abort failures expose only fixed client codes", async () => {
  const file = new Blob([1], { type: "image/png" });
  for (const [status, code] of [
    [400, "media_invalid"],
    [401, "forbidden"],
    [403, "forbidden"],
    [404, "forbidden"],
    [409, "conflict"],
    [413, "media_too_large"],
    [500, "media_unavailable"],
    [302, "media_unavailable"],
  ]) {
    const { hass } = client(new Response("DO-NOT-ECHO", { status }));
    await rejectsCode(uploadMedia(hass, options({ file })), code);
  }

  const network = client(() => {
    throw new Error("PRIVATE NETWORK OR SERVER DETAIL");
  });
  await rejectsCode(
    uploadMedia(network.hass, options({ file })),
    "media_unavailable",
  );
  const redirected = client({ ok: true, status: 200, redirected: true });
  await rejectsCode(
    uploadMedia(redirected.hass, options({ file })),
    "media_unavailable",
  );

  const preAborted = new AbortController();
  preAborted.abort("PRIVATE ABORT REASON");
  const aborted = client(jsonResponse({}));
  await rejectsCode(
    downloadMedia(aborted.hass, options({ signal: preAborted.signal })),
    "media_unavailable",
  );
  assert.equal(aborted.calls.length, 0);

  const readFailure = new ReadableStream({
    pull(controller) {
      controller.error(new Error("PRIVATE STREAM DETAIL"));
    },
  });
  await rejectsCode(
    downloadMedia(
      client(new Response(readFailure, { headers: { "content-type": "image/png" } })).hass,
      options(),
    ),
    "media_unavailable",
  );
});
