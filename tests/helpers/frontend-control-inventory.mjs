import {createHash} from "node:crypto";
import {readFile, readdir} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";

export const frontendRoot = "custom_components/family_assistant/frontend";
export const cards = ["today", "shopping", "tasks", "court", "alarms", "health", "conversation", "mikrotik", "calendar", "routines", "pantry", "meals", "school", "maintenance", "polls", "presence", "digests"];
export const moduleForFile = file => {
  if (file.startsWith("panel-") || file === "family-panel.js") return "panel";
  if (file.startsWith("network-")) return "mikrotik";
  if (file.startsWith("task-") || file === "task-items.js") return "tasks";
  if (file.startsWith("shopping-") || file === "gtin.js") return "shopping";
  if (file.startsWith("alarm-")) return "alarms";
  if (file.startsWith("reward")) return "court";
  if (file.startsWith("dietary") || file.startsWith("recipe") || file.startsWith("meal-")) return "meals";
  if (file.startsWith("fault-photo") || file.startsWith("asset-document")) return "maintenance";
  if (file.startsWith("article") || file.startsWith("semantic-feedback")) return "conversation";
  if (file.startsWith("developer")) return "health";
  return cards.find(module => file.startsWith(`${module}-`)) || "shared";
};
const patterns = {
  listener: /\.addEventListener\s*\(|\.(?:onclick|onsubmit|oninput|onchange|onkeydown)\s*=/,
  button: /(?:\bbutton|\.button)\s*\(/,
  element: /\b(?:el|node|createElement)\s*\(\s*["'](?:button|input|select|textarea|form|a|summary)["']/,
  field: /\b(?:input|select|field|selectField|textField|numberField|textareaField|checkbox|checkField)\s*\(|\.name\s*=/,
  command: /\.command\s*\(/,
  request: /\.callWS\s*\(/,
  link: /\.href\s*=/,
};
export async function sourceInventory(root) {
  const sources = [];
  for (const file of (await readdir(path.join(root, frontendRoot))).filter(file => file.endsWith(".js")).sort()) {
    const text = await readFile(path.join(root, frontendRoot, file), "utf8");
    const sites = [];
    for (const [index, source] of text.split(/\r?\n/).entries()) {
      if (/^\s*(?:\/\/|\*|\/\*)/.test(source)) continue;
      const kinds = Object.entries(patterns).filter(([, pattern]) => pattern.test(source)).map(([kind]) => kind);
      if (kinds.length) sites.push({line: index + 1, kinds, code: source.trim()});
    }
    sources.push({file, module: moduleForFile(file), sha256: createHash("sha256").update(text.replaceAll("\r\n", "\n")).digest("hex"), sites});
  }
  return sources;
}
export async function buildInventory(root, evidence = null) {
  const sources = await sourceInventory(root);
  const cases = [], handlers = new Map(), requests = new Map(), sourceFrames = new Map();
  for (const item of evidence?.cases || []) {
    if (item.status !== "passed") continue;
    const id = cases.length;
    cases.push({id, file: item.file, line: item.line, title: item.title});
    for (const document of item.documents || []) {
      for (const handler of document.handlers || []) {
        // Preserve every collected frame separately from the two-frame handler
        // grouping. Nested button wrappers otherwise hide their real callers.
        for(const site of handler.sites) {
          const key=`${site.file}:${site.line}:${site.column}`;
          let frame=sourceFrames.get(key);
          if(!frame){frame={...site,registered:[],invoked:[],trusted:[]};sourceFrames.set(key,frame);}
          frame.registered.push(id);if(handler.invoked)frame.invoked.push(id);if(handler.trusted)frame.trusted.push(id);
        }
        // The first two frames retain a helper + its calling control location;
        // deeper render stacks are not separate controls.
        const sites = handler.sites.slice(0, 2), key = `${handler.event}:${sites.map(site => `${site.file}:${site.line}:${site.column}`).join("|")}`;
        let row = handlers.get(key);
        if (!row) {row = {id: key, event: handler.event, sites, registered: [], invoked: [], trusted: [], views: []}; handlers.set(key, row);}
        row.registered.push(id);
        if (handler.invoked) row.invoked.push(id);
        if (handler.trusted) row.trusted.push(id);
        row.views.push(...handler.views);
      }
      for (const request of document.requests || []) {
        let row = requests.get(request.id);
        if (!row) {row = {id: request.id, attempted: [], resolved: [], rejected: []}; requests.set(request.id, row);}
        for (const kind of ["attempted", "resolved", "rejected"]) if (request[kind]) row[kind].push(id);
      }
    }
  }
  for (const row of [...handlers.values(), ...requests.values(), ...sourceFrames.values()]) for (const key of Object.keys(row)) {
    if (Array.isArray(row[key]) && key !== "sites") row[key] = [...new Set(row[key])].sort();
  }
  const modules = [...cards, "panel", "shared"].map(id => ({id,
    source_sites: sources.filter(source => source.module === id).reduce((count, source) => count + source.sites.length, 0),
    browser_cases_with_invoked_handler: [...new Set([...handlers.values()].filter(row => row.sites.some(site => moduleForFile(site.file) === id) || row.views.includes(id)).flatMap(row => row.invoked))].sort(),
  }));
  const relatedCases = fragment => cases.filter(item => item.title.includes(fragment)).map(item => item.id);
  const controlNotes = [
    {file:"school-reminders-view.js",lines:[341],classification:"submit_navigation_guard_only",explanation:"The form submit listener only prevents navigation. The named browser scenario explicitly submits the form and asserts no mutation; saving still requires its separate preference action.",related_cases:relatedCases("school reminder form submit cannot bypass")},
    {file:"task-batch-view.js",lines:[396],classification:"submit_navigation_guard_only",explanation:"Explicit form submission keeps selection visible and sends no batch. This tests the no-navigation guard, not a replacement for named review and consent.",related_cases:relatedCases("task batch selection submit is only")},
    {file:"task-media-view.js",lines:[820],classification:"submit_navigation_guard_only",explanation:"Submitting a valid selected-file form sends neither a reservation nor upload and cannot bypass explicit photo review.",related_cases:relatedCases("task photo selection submit cannot bypass")},
    {file:"digests-view.js",lines:[732,793],classification:"alternate_submit_path",explanation:"Submit delegates to the same guarded button/save function. The named scenario explicitly requestSubmits both forms with synthetic failure/retry evidence; this does not claim every Enter/keyboard combination.",related_cases:relatedCases("digest alternate submit retries")},
    {file:"presence-view.js",lines:[503],classification:"alternate_submit_path",explanation:"The named scenario exercises explicit form submission, consent, failure and exact retry through the same guarded save function as its button.",related_cases:relatedCases("presence Cancel refuses consent")},
    {file:"presence-notifications-view.js",lines:[579],classification:"alternate_submit_path",explanation:"Submit uses the same guarded submitAction as the named review button. The named scenario requestSubmits the form and asserts one exact preference mutation.",related_cases:relatedCases("return-home notification Cancel resets")},
    {file:"network-watch-view.js",lines:[323],classification:"alternate_submit_path",explanation:"Explicit form submit is refused without consent, then sends one exact preference through the same guarded submitAction as the review button. Real network observation/delivery is outside this synthetic test.",related_cases:relatedCases("private discovery alternate submit requires")},
    {file:"family-panel.js",lines:[419,479,559],classification:"alternate_submit_path",explanation:"Named scenarios requestSubmit valid member, Advanced/wizard family, school settings and recognition forms; assertions distinguish exact writes, frozen failed member retry and read-only recognition. These are not claims about every setting combination or keyboard sequence.",related_cases:cases.filter(item=>item.file==="tests/browser/control-final-actions.spec.js"&&/member alternate submit|settings alternate submit|recognition alternate submit/.test(item.title)).map(item=>item.id)},
    {file:"court-view.js",lines:[533,536],classification:"native_submit_action",explanation:"The button click callback itself is deliberately empty because the button submits the form. The manual award scenario clicks it with invalid and valid values, then verifies exact failed-save retry, the chosen member and preserved prior ledger.",related_cases:relatedCases("manual points award validates")},
    {file:"family-panel.js",lines:[546],classification:"native_navigation_boundary_only",explanation:"Both connection aliases are clicked and intercepted at a synthetic local native-setup page. This validates their destination, not Home Assistant Options, credentials or provider behavior.",related_cases:relatedCases("opens only intercepted native setup boundary")},
    {file:"recurrence-form.js",classification:"shared_factory_not_all_value_combinations",explanation:"Calendar, task, shopping and other callers clone common recurrence inputs. Named cases validate specific payloads; not every caller/frequency/weekday/time combination was exercised.",related_cases:cases.filter(item=>item.file==="tests/browser/recurrence-browser.spec.js"||item.file==="tests/browser/task-series.spec.js").map(item=>item.id)},
  ];
  const sourceReview = [
    {file:"asset-document-view.js",lines:[92],classification:"conditional_control_scenario",detail:"Removed-document archive beyond the initial 20 rows: local pagination only.",related_cases:relatedCases("removed document pagination")},
    {file:"task-batch-view.js",lines:[492],classification:"conditional_control_scenario",detail:"More than 100 eligible tasks: load the next page without clearing selection or sending a batch.",related_cases:relatedCases("task batch pagination reveals")},
    {file:"task-series-view.js",lines:[567],classification:"conditional_control_scenario",detail:"Inactive assignee in retained series: remove only the unsaved row and cancel without changing the series.",related_cases:relatedCases("unavailable recurring assignee")},
    {file:"family-assistant.js",lines:[675],classification:"conditional_control_scenario",detail:"Lovelace editor household/title/view changes emit exact local config-changed events; they are not integration settings writes.",related_cases:relatedCases("Lovelace editor emits")},
    {file:"family-panel.js",lines:[328],classification:"conditional_control_scenario",detail:"Multiple authorized households: selecting each entry reloads only that entry's panel and sends no mutation.",related_cases:relatedCases("panel household selector replaces")},
    {file:"family-assistant.js",lines:[603,606],classification:"conditional_control_scenario",detail:"Parent Stop for an active alarm run validates reason and retries the same cancellation after a pre-effect failure; no device is present in this fixture.",related_cases:relatedCases("parent alarm Stop validates")},
    {file:"task-form.js",lines:[899],classification:"conditional_control_scenario",detail:"Single create after committed response loss: Close without rollback preserves the committed task and sends no second command.",related_cases:relatedCases("single-task Close without rollback")},
    {file:"task-media-view.js",lines:[865],classification:"conditional_control_scenario",detail:"Image decoder rejects a selected synthetic file: Cancel clears the failed preview without media reservation or upload.",related_cases:relatedCases("failed photo preview Cancel")},
    {file:"pantry-view.js",lines:[771],classification:"conditional_control_scenario",detail:"Archive validates reason, preserves original stock/history during failure and retries the exact id/revision payload.",related_cases:relatedCases("pantry archive reason is validated")},
    {file:"maintenance-view.js",lines:[1055],classification:"conditional_control_scenario",detail:"Manual service log consumable row Remove is distinct from the equipment editor; no saved stock or log is changed before submission.",related_cases:relatedCases("manual maintenance log consumable Remove")},
    {file:"network-kids.js",lines:[108,111],classification:"conditional_control_scenario",detail:"Owner-only adoption and adult delegation use their real local Store API shapes, with consent, target changes and failure cases. This is not router/device acceptance.",related_cases:cases.filter(item=>item.file==="tests/browser/control-network-adoption.spec.js").map(item=>item.id)},
    {file:"routines-view.js",lines:[775,1469,1623,1713],classification:"conditional_control_scenario",detail:"Household modes, member-targeted start, parent step override and run cancellation have dedicated named consent, role and failure scenarios.",related_cases:cases.filter(item=>item.file==="tests/browser/control-routine-actions.spec.js").map(item=>item.id)},
    {file:"availability-shell.js",lines:[91],classification:"not_reachable_through_published_card_router",detail:"FamilyCard.render returns its common Retry at family-assistant.js:419 when _error is set, before every availability-shell call. The helper's error Retry is therefore not another reachable published-card button; module/role shells remain covered.",related_cases:cases.filter(item=>item.file==="tests/browser/availability-shell.spec.js").map(item=>item.id)},
    {file:"family-assistant.js",lines:[396,635,637],classification:"obsolete_generic_routes_not_reachable",detail:"The generic form has no reachable published use: tasks form returns its specialized editor at 383, shopping uses its editor, court/calendar return specialized renderers at 460-461, and alarms use their dedicated editor. Generic court reversal in renderItem is bypassed by renderCourt. Retained source is not removed or counted as clicked.",related_cases:cases.filter(item=>["tests/browser/court-browser.spec.js","tests/browser/alarm-editor.spec.js"].includes(item.file)).map(item=>item.id)},
    ...[["network-admission-view.js",363],["network-watch-view.js",196],["presence-notifications-view.js",382],["shopping-items.js",755],["task-media-view.js",428]].map(([file,line])=>({file,lines:[line],classification:"non_card_helper_fallback",detail:"Fallback listener is used only when a caller supplies no card.button. Every published card inherits FamilyCard.button; browser evidence for the shared-button branch does not claim this alternate helper implementation ran.",related_cases:[]})),
  ];
  return {schema_version: 1,
    scope: "All 17 published cards, shared Lovelace editor, and control panel. Public source and synthetic fixtures only.",
    interpretation: {
      source_sites: "Conservative line inventory of control factories, listeners, form fields, commands and links. Shared factories and dynamic loops are explicit sites, not proof of every possible record/value combination. Full source excerpt retained for review.",
      handlers: "Registered = a fixture rendered/bound that source handler; invoked = listener actually ran; trusted = at least one native browser event. Source frames identify helpers and the caller. Runtime variants/roles not used in listed tests remain untested.",
      requests: "Exact WS type/action observed through real frontend code. Resolved/rejected describe synthetic fixture promises, not validation by Home Assistant or devices.",
      gaps: "Source-only sites, registered handlers with empty invoked, and requests without rejected evidence need additional manual/browser/fault scenarios. Native integration links are not followed to real HA. Camera, external providers, real notifications, devices and live legacy parity are not established.",
    },
    source_sha256: createHash("sha256").update(JSON.stringify(sources)).digest("hex"),
    evidence_status: evidence?.status || "not_run", modules, cases, control_notes:controlNotes,source_control_review:sourceReview,
    sources,
    handlers: [...handlers.values()].sort((a, b) => a.id.localeCompare(b.id)),
    source_frames:[...sourceFrames.values()].sort((a,b)=>a.file.localeCompare(b.file)||a.line-b.line||a.column-b.column),
    requests: [...requests.values()].sort((a, b) => a.id.localeCompare(b.id)),
  };
}
export function summarizeInventory(inventory) {
  const boundSites=new Set((inventory.source_frames || inventory.handlers.flatMap(row=>row.sites)).map(site=>`${site.file}:${site.line}`));
  const uninvoked=inventory.handlers.filter(row=>!row.invoked.length);
  return {
    evidence_status: inventory.evidence_status,
    passing_browser_cases: inventory.cases.length,
    frontend_files: inventory.sources.length,
    source_sites: inventory.sources.reduce((count, source) => count + source.sites.length, 0),
    source_sites_without_registered_handler_frame:inventory.sources.reduce((count,source)=>count+source.sites.filter(site=>!boundSites.has(`${source.file}:${site.line}`)).length,0),
    registered_handler_sites: inventory.handlers.length,
    invoked_handler_sites: inventory.handlers.filter(row => row.invoked.length).length,
    trusted_event_handler_sites: inventory.handlers.filter(row => row.trusted.length).length,
    uninvoked_handler_sites: uninvoked.map(row => row.id),
    uninvoked_by_event:Object.fromEntries(["click","submit","input","change","keydown"].map(event=>[event,uninvoked.filter(row=>row.event===event).length])),
    observed_ws_actions: inventory.requests.length,
    ws_actions_with_resolved_fixture_response: inventory.requests.filter(row => row.resolved.length).length,
    ws_actions_with_rejected_fixture_response: inventory.requests.filter(row => row.rejected.length).length,
    modules: inventory.modules.map(module => ({id: module.id, source_sites: module.source_sites,
      passing_cases_with_invoked_handler: module.browser_cases_with_invoked_handler.length})),
  };
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = process.cwd();
  const input = process.argv.slice(2).find(value => !value.startsWith("--"));
  if (process.argv.includes("--summary")) {
    const inventory = JSON.parse(await readFile(path.resolve(root, input || "tests/frontend-control-inventory.json"), "utf8"));
    process.stdout.write(JSON.stringify(summarizeInventory(inventory), null, 2) + "\n");
  } else {
  const evidence = input ? JSON.parse(await readFile(path.resolve(root, input), "utf8")) : null;
  const inventory = await buildInventory(root, evidence);
  if (process.argv.includes("--patch")) {
    const target = path.join(root, "tests", "frontend-control-inventory.json");
    let previous = null;
    try {previous = await readFile(target,"utf8");} catch {}
    const encoded = JSON.stringify(inventory, null, 2) + "\n";
    const patch = ["*** Begin Patch", ...(previous === null ? [`*** Add File: ${target}`] : [`*** Update File: ${target}`,"@@",...previous.trimEnd().split(/\r?\n/).map(line=>`-${line}`)]),
      ...encoded.trimEnd().split("\n").map(line => `+${line}`), "*** End Patch"].join("\n");
    process.stdout.write(patch);
  } else process.stdout.write(JSON.stringify(inventory, null, 2) + "\n");
  }
}
