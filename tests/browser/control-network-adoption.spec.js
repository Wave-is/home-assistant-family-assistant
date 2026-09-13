import {test,expect} from "./control-audit.js";
import {KID_COPY} from "../../custom_components/family_assistant/frontend/network-kids.js";

const copy=KID_COPY.en;
const card=page=>page.locator("family-assistant-card");
const adoption=page=>card(page).locator("details").filter({has:page.getByText(copy.adopt,{exact:true})});
const delegation=page=>card(page).locator("form").filter({has:page.getByText("Adult 1",{exact:true})});
const calls=page=>page.evaluate(()=>window.calls);
const localState=page=>page.evaluate(()=>({bindings:structuredClone(window.kidAdmin.bindings),grants:{...window.kidAdmin.grants},revision:window.fixture.revision,members:structuredClone(window.fixture.members),plans:structuredClone(window.fixture.kid_control.plans)}));
const open=async(page,role="owner")=>page.goto(`/tests/fixtures/dashboard.html?view=mikrotik&kids=1&kidadoption=1&role=${role}`);

test("network ownership: adoption requires fresh consent for every target change and never applies router controls",async({page})=>{
  await open(page);const section=adoption(page),before=await localState(page);
  await section.locator("summary").click();await expect(section).toContainText("Study phone");
  await section.getByRole("button",{name:copy.adoptSave,exact:true}).click();
  expect(await calls(page)).toEqual([]);expect(await localState(page)).toEqual(before);
  await section.getByLabel(copy.verify,{exact:true}).check();
  await section.getByLabel(copy.profile,{exact:true}).selectOption("*3");
  await expect(section.getByLabel(copy.verify,{exact:true})).not.toBeChecked();
  await expect(section).toContainText("Leisure tablet");await expect(section).toContainText("Leisure laptop");
  await expect(section).not.toContainText("Study phone");
  await section.getByLabel(copy.verify,{exact:true}).check();
  await section.getByLabel(copy.member,{exact:true}).selectOption("sibling");
  await expect(section.getByLabel(copy.verify,{exact:true})).not.toBeChecked();
  // This control is a native disclosure, not a fabricated Cancel action.
  await section.locator("summary").click();expect(await calls(page)).toEqual([]);
  await section.locator("summary").click();await expect(section.getByLabel(copy.profile,{exact:true})).toHaveValue("*3");
  await section.getByLabel(copy.verify,{exact:true}).check();
  await section.getByRole("button",{name:copy.adoptSave,exact:true}).click();
  await expect(card(page).locator("strong").filter({hasText:"Child 2 · Leisure profile"})).toBeVisible();
  const sent=await calls(page);expect(sent).toHaveLength(1);
  expect(sent[0]).toEqual({type:"family_assistant/execute",entry_id:"synthetic",action:"mikrotik.kid_adopt",payload:{member:"sibling",profile_id:"*3",devices:["*4","*5"],confirmed:true},operation_id:expect.stringMatching(/^[0-9a-f-]{36}$/)});
  // The actual API accepts no revision fields: ownership is guarded by current source membership.
  const after=await localState(page);expect(after.revision).toBe(before.revision+1);expect(after.members).toEqual(before.members);expect(after.grants).toEqual(before.grants);expect(after.plans).toEqual([]);
  expect(after.bindings).toEqual({sibling:{member:"sibling",profile_id:"*3",name:"Leisure profile",devices:[{id:"*4",name:"Leisure tablet",mac:"02:11:22:33:44:77"},{id:"*5",name:"Leisure laptop",mac:"02:11:22:33:44:88"}]}});
});

test("network ownership: changed profile membership rejects cached consent until the new device set is reviewed",async({page})=>{
  await open(page);const section=adoption(page),before=await localState(page);await section.locator("summary").click();
  await section.getByLabel(copy.verify,{exact:true}).check();
  await page.evaluate(()=>window.kidAdmin.profiles[0].devices.push({id:"*6",name:"New study tablet",mac:"02:11:22:33:44:99"}));
  await section.getByRole("button",{name:copy.adoptSave,exact:true}).click();
  await expect(card(page).getByRole("alert")).toContainText("entire profile membership");expect(await localState(page)).toEqual(before);
  await section.locator("summary").click();await expect(section).toContainText("New study tablet");
  await expect(section.getByLabel(copy.verify,{exact:true})).not.toBeChecked();
  await section.getByRole("button",{name:copy.adoptSave,exact:true}).click();expect(await calls(page)).toHaveLength(1);
  await section.getByLabel(copy.verify,{exact:true}).check();await section.getByRole("button",{name:copy.adoptSave,exact:true}).click();
  await expect(card(page).locator("strong").filter({hasText:"Child 1 · Study profile"})).toBeVisible();
  const sent=await calls(page);expect(sent).toHaveLength(2);expect(sent.map(item=>item.action)).toEqual(["mikrotik.kid_adopt","mikrotik.kid_adopt"]);
  expect(sent[0].payload.devices).toEqual(["*2"]);expect(sent[1].payload.devices).toEqual(["*2","*6"]);expect(sent[1].operation_id).not.toBe(sent[0].operation_id);
  expect((await localState(page)).revision).toBe(before.revision+1);
});

for(const role of ["parent","adult","child"])test(`network ownership: ${role} cannot see owner-only adoption or delegation forms`,async({page})=>{
  await open(page,role);await expect(card(page).getByRole("heading",{name:copy.title,exact:true})).toBeVisible();
  await expect(card(page).getByRole("button",{name:copy.adoptSave,exact:true})).toHaveCount(0);await expect(card(page).getByRole("button",{name:copy.delegationSave,exact:true})).toHaveCount(0);
  expect(await calls(page)).toEqual([]);expect(await page.evaluate(()=>({candidates:window.card._data.kid_control.candidates,delegations:window.card._data.kid_control.delegations}))).toEqual({candidates:[],delegations:{}});
});

test("network ownership: explicit adult grant and revoke change only Kid Control permission",async({page})=>{
  await open(page);const form=delegation(page),before=await localState(page);await expect(form.getByLabel(copy.delegation,{exact:true})).not.toBeChecked();
  await form.getByLabel(copy.delegation,{exact:true}).check();expect(await calls(page)).toEqual([]);
  await form.getByRole("button",{name:copy.delegationSave,exact:true}).click();await expect(form.getByLabel(copy.delegation,{exact:true})).toBeChecked();
  await form.getByLabel(copy.delegation,{exact:true}).uncheck();await form.getByRole("button",{name:copy.delegationSave,exact:true}).click();await expect(form.getByLabel(copy.delegation,{exact:true})).not.toBeChecked();
  const sent=await calls(page);expect(sent).toHaveLength(2);
  for(const [index,enabled] of [true,false].entries())expect(sent[index]).toEqual({type:"family_assistant/execute",entry_id:"synthetic",action:"mikrotik.kid_permission",payload:{member:"adult",enabled},operation_id:expect.stringMatching(/^[0-9a-f-]{36}$/)});
  expect(sent[1].operation_id).not.toBe(sent[0].operation_id);const after=await localState(page);expect(after).toEqual({...before,revision:before.revision+2});
});

for(const action of ["adopt","permission"])test(`network ownership: stale owner ${action} form is denied after role revocation`,async({page})=>{
  await open(page);const before=await localState(page),form=action==="adopt"?adoption(page):delegation(page);
  if(action==="adopt")await form.locator("summary").click();await form.getByLabel(action==="adopt"?copy.verify:copy.delegation,{exact:true}).check();
  // Backend role changes before the stale displayed control is submitted.
  await page.evaluate(()=>{window.fixture.role="parent";window.fixture.members.find(member=>member.id==="owner").role="parent";});
  await form.getByRole("button",{name:action==="adopt"?copy.adoptSave:copy.delegationSave,exact:true}).click();
  await expect(card(page).getByRole("alert")).toContainText("permission");
  const sent=await calls(page);expect(sent).toHaveLength(1);expect(sent[0].action).toBe(`mikrotik.kid_${action}`);
  const after=await localState(page);expect(after.bindings).toEqual(before.bindings);expect(after.grants).toEqual(before.grants);expect(after.plans).toEqual([]);expect(after.revision).toBe(before.revision);
  await expect(card(page).getByRole("button",{name:copy.adoptSave,exact:true})).toHaveCount(0);await expect(card(page).getByRole("button",{name:copy.delegationSave,exact:true})).toHaveCount(0);
});
