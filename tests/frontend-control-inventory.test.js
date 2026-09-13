import assert from "node:assert/strict";
import {readFile, readdir} from "node:fs/promises";
import {test} from "node:test";
import {buildInventory, cards} from "./helpers/frontend-control-inventory.mjs";

test("UI control inventory names all published cards and remains synchronized with source sites", async () => {
  const saved = JSON.parse(await readFile(new URL("./frontend-control-inventory.json", import.meta.url), "utf8"));
  const current = await buildInventory(process.cwd());
  assert.equal(saved.source_sha256, current.source_sha256, "Frontend controls changed: review/update the inventory and rerun the synthetic control audit.");
  assert.deepEqual(saved.sources, current.sources);
  for (const module of [...cards, "panel", "shared"]) assert.ok(saved.modules.some(item => item.id === module));
  assert.equal(saved.evidence_status, "passed");
  assert.ok(saved.cases.length >= 250);
  assert.ok(saved.handlers.length > 0);
  assert.ok(saved.handlers.every(item => Array.isArray(item.invoked)), "Unexercised controls must retain explicit empty invocation evidence.");
  assert.ok(saved.requests.some(item => item.rejected.length > 0));
  for (const row of saved.handlers) for (const reference of [...row.registered, ...row.invoked, ...row.trusted]) assert.ok(saved.cases.some(item => item.id === reference));
  for (const note of saved.control_notes) {
    assert.ok(saved.sources.some(item=>item.file===note.file));
    assert.ok(note.related_cases.length>0);
    for(const id of note.related_cases)assert.ok(saved.cases.some(item=>item.id===id));
  }
  assert.ok(saved.source_frames.length>0,"The source review must retain nested helper caller frames, not just grouped handler identities.");
  for(const frame of saved.source_frames)for(const id of [...frame.registered,...frame.invoked,...frame.trusted])assert.ok(saved.cases.some(item=>item.id===id));
  for(const row of saved.source_control_review){
    const source=saved.sources.find(item=>item.file===row.file);assert.ok(source);
    assert.ok(row.lines.every(line=>source.sites.some(site=>site.line===line)),`${row.file}: reviewed control source moved.`);
    if(row.classification==="conditional_control_scenario")assert.ok(row.related_cases.length>0,`${row.file}: conditional control lacks its named scenario.`);
    for(const id of row.related_cases)assert.ok(saved.cases.some(item=>item.id===id));
  }
});

test("every browser suite participates in the optional synthetic action audit", async () => {
  const saved = JSON.parse(await readFile(new URL("./frontend-control-inventory.json", import.meta.url), "utf8"));
  for (const file of (await readdir(new URL("./browser/", import.meta.url))).filter(file => file.endsWith(".spec.js"))) {
    const source = await readFile(new URL(`./browser/${file}`, import.meta.url), "utf8");
    assert.match(source, /from ["']\.\/control-audit\.js["']/);
    assert.doesNotMatch(source, /from ["']@playwright\/test["']/);
    assert.ok(saved.cases.some(item => item.file === `tests/browser/${file}`), `${file} has no passing browser evidence in the inventory.`);
  }
});
