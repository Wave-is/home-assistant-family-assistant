import {test as base, expect} from "@playwright/test";

// Optional synthetic-only evidence collection. This records handler invocation
// and WS action names, never field values, payloads, replies or credentials.
export function installControlAudit() {
  if (location.hostname !== "127.0.0.1" || !location.pathname.startsWith("/tests/fixtures/")) return;
  const handlers = new Map(), requests = new Map(), wrappers = new WeakMap();
  const documents = crypto.randomUUID();
  let scheduled = false, version = 0;
  const frames = () => [...new Error().stack.matchAll(/\/custom_components\/family_assistant\/frontend\/([^?# ):]+):(\d+):(\d+)/g)]
    .slice(0, 5).map(([, file, line, column]) => ({file, line: Number(line), column: Number(column)}));
  const snapshot = () => ({document: documents, version, fixture: location.pathname,
    handlers: [...handlers.values()], requests: [...requests.values()]});
  const flush = () => {scheduled = false; void window.__receiveControlAudit?.(snapshot()).catch(() => {});};
  const changed = () => {version++; if (!scheduled) {scheduled = true; setTimeout(flush, 100);}};
  Object.defineProperty(window, "__controlAuditSnapshot", {value: snapshot});
  const originalAdd = EventTarget.prototype.addEventListener;
  const originalRemove = EventTarget.prototype.removeEventListener;
  const kind = target => {
    const host = target?.getRootNode?.().host;
    return host?._view || (host?.localName === "family-assistant-panel" ? "panel" : "shared");
  };
  const wrap = (target, event, listener, sites, capture) => {
    if (!listener || !sites.length || !["click", "submit", "change", "input", "keydown"].includes(event)) return listener;
    let callbacks = wrappers.get(target);
    if (!callbacks) {callbacks = new Map(); wrappers.set(target, callbacks);}
    const key = `${event}:${!!capture}`;
    let byListener = callbacks.get(key);
    if (!byListener) {byListener = new WeakMap(); callbacks.set(key, byListener);}
    if ((typeof listener !== "function" && typeof listener !== "object") || listener === null) return listener;
    if (byListener.has(listener)) return byListener.get(listener);
    const id = `${event}:${sites.map(site => `${site.file}:${site.line}:${site.column}`).join("|")}`;
    let record = handlers.get(id);
    if (!record) {record = {id, event, sites, registered: 0, invoked: 0, trusted: 0, views: []}; handlers.set(id, record);}
    record.registered++; changed();
    const wrapped = function (evt) {
      record.invoked++; if (evt.isTrusted) record.trusted++;
      const view = kind(target); if (!record.views.includes(view)) record.views.push(view);
      changed();
      return typeof listener === "function" ? listener.call(this, evt) : listener.handleEvent(evt);
    };
    byListener.set(listener, wrapped); return wrapped;
  };
  EventTarget.prototype.addEventListener = function (event, listener, options) {
    return originalAdd.call(this, event, wrap(this, event, listener, frames(), typeof options === "boolean" ? options : options?.capture), options);
  };
  EventTarget.prototype.removeEventListener = function (event, listener, options) {
    const capture = typeof options === "boolean" ? options : options?.capture;
    const wrapped = wrappers.get(this)?.get(`${event}:${!!capture}`)?.get(listener);
    return originalRemove.call(this, event, wrapped || listener, options);
  };
  for (const event of ["click", "submit", "change", "input", "keydown"]) {
    const property = `on${event}`, descriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, property);
    if (!descriptor?.set) continue;
    const originals = new WeakMap();
    Object.defineProperty(HTMLElement.prototype, property, {...descriptor,
      get() {return originals.has(this) ? originals.get(this) : descriptor.get.call(this);},
      set(listener) {originals.set(this, listener); descriptor.set.call(this, wrap(this, event, listener, frames(), false));},
    });
  }
  const proxies = new WeakMap(), prototypes = new WeakSet();
  const wrapHass = value => {
    if (!value || typeof value !== "object") return value;
    if (proxies.has(value)) return proxies.get(value);
    let observedCall, originalCall;
    const proxy = new Proxy(value, {get(target, property) {
      if (property !== "callWS" || typeof target.callWS !== "function") return Reflect.get(target, property, target);
      if (originalCall === target.callWS) return observedCall;
      const requestFunction = originalCall = target.callWS;
      observedCall = async (...args) => {
        const message = args[0], type = message?.type, action = message?.action;
        if (typeof type !== "string" || !type.startsWith("family_assistant/")) return requestFunction.apply(target, args);
        const id = `${type}${typeof action === "string" ? `:${action}` : ""}`;
        let record = requests.get(id);
        if (!record) {record = {id, type, ...(typeof action === "string" ? {action} : {}), attempted: 0, resolved: 0, rejected: 0}; requests.set(id, record);}
        record.attempted++; changed();
        try {const result = await requestFunction.apply(target, args); record.resolved++; changed(); return result;}
        catch (error) {record.rejected++; changed(); throw error;}
      };
      return observedCall;
    }});
    proxies.set(value, proxy); proxies.set(proxy, proxy); return proxy;
  };
  const originalDefine = CustomElementRegistry.prototype.define;
  CustomElementRegistry.prototype.define = function (name, ctor, options) {
    if (name.startsWith("family-")) for (let proto = ctor.prototype; proto && proto !== HTMLElement.prototype; proto = Object.getPrototypeOf(proto)) {
      if (prototypes.has(proto)) continue;
      const descriptor = Object.getOwnPropertyDescriptor(proto, "hass");
      if (descriptor?.set) {
        prototypes.add(proto);
        Object.defineProperty(proto, "hass", {...descriptor, set(value) {return descriptor.set.call(this, wrapHass(value));}});
      }
    }
    return originalDefine.call(this, name, ctor, options);
  };
  originalAdd.call(window, "pagehide", flush);
}

export const test = base.extend({
  page: async ({page}, use, testInfo) => {
    if (process.env.FA_CONTROL_AUDIT !== "1") {await use(page); return;}
    const documents = new Map();
    const diagnostics = [];
    const localFixture = () => /^http:\/\/127\.0\.0\.1:\d+\/tests\/fixtures\//.test(page.url());
    const scriptError = error => {if(localFixture())diagnostics.push({kind:"pageerror",message:error.message});};
    const failedResource = request => {
      const url=new URL(request.url());
      if(localFixture()&&url.hostname==="127.0.0.1"&&["script","document"].includes(request.resourceType()))diagnostics.push({kind:"requestfailed",path:url.pathname,error:request.failure()?.errorText});
    };
    page.on("pageerror",scriptError);page.on("requestfailed",failedResource);
    const receive = value => {if (value && value.version >= (documents.get(value.document)?.version ?? -1)) documents.set(value.document, value);};
    const capture = async () => {
      if (!page.isClosed()) receive(await page.evaluate(() => window.__controlAuditSnapshot?.()).catch(() => null));
    };
    await page.exposeBinding("__receiveControlAudit", (_, value) => receive(value));
    await page.addInitScript(installControlAudit);
    // pagehide bindings are best effort during document teardown. Await a
    // snapshot before explicit test navigation so its final click/WS result is
    // not misclassified as unvisited when the next page is read-only.
    const navigation = new Map(["goto", "reload", "close"].map(method => [method, page[method]]));
    for (const [method, original] of navigation) page[method] = async (...args) => {await capture(); return original.apply(page, args);};
    try {await use(page);}
    finally {
      await capture();
      page.off("pageerror",scriptError);page.off("requestfailed",failedResource);
      for (const [method, original] of navigation) page[method] = original;
      await testInfo.attach("frontend-control-audit", {body: JSON.stringify([...documents.values()]), contentType: "application/json"});
      if(diagnostics.length)await testInfo.attach("frontend-load-diagnostics",{body:JSON.stringify(diagnostics),contentType:"application/json"});
    }
  },
});
export {expect};
