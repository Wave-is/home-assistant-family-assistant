import {test,expect} from "./control-audit.js";

test("parent assigns one step while the other inherits, preserving explicit assignee in payload",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/routine-handoffs.html?lang=ru");
  const card=page.locator("family-routines-card");
  await card.getByRole("button",{name:"Изменить",exact:true}).click();
  const selects=card.locator("select[data-step-assignee]");
  await expect(selects).toHaveCount(2);
  await expect(selects.nth(1)).toBeVisible();
  await selects.nth(1).selectOption("owner");
  await page.screenshot({path:"test-results/routine-handoff-edit-ru.png",fullPage:true});
  await card.getByRole("button",{name:"Сохранить",exact:true}).click();
  await expect(card.getByText("Утренний распорядок",{exact:true}).first()).toBeVisible();
  const payload=await page.evaluate(()=>window.calls[0].payload);
  expect(payload.steps[0]).not.toHaveProperty("assignee");
  expect(payload.steps[1].assignee).toBe("owner");
  expect(await page.evaluate(()=>window.fixture.routines.templates[0].steps[1].assignee)).toBe("owner");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("stale inactive step assignee is rejected before any API payload is sent",async({page})=>{
  await page.goto("/tests/fixtures/routine-handoffs.html?lang=en&stale-template");
  const card=page.locator("family-routines-card");
  await card.getByRole("button",{name:"Edit",exact:true}).click();
  const stale=card.locator("select[data-step-assignee='1']");
  await expect(stale).toHaveValue("former");
  await card.getByRole("button",{name:"Save",exact:true}).click();
  await expect(card.getByRole("alert")).toContainText(/assigned|select|member/i);
  expect(await page.evaluate(()=>window.calls.length)).toBe(0);
});

test("child cannot confirm a current step assigned to the parent even when run member is child",async({page})=>{
  await page.goto("/tests/fixtures/routine-handoffs.html?lang=uk&actor=child&run=handoff");
  const card=page.locator("family-routines-card");
  await expect(card.getByRole("button",{name:"Позначити виконання кроку",exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls.length)).toBe(0);
  await expect(card.getByText("Батько 1",{exact:false}).first()).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/routine-handoff-child-uk.png",fullPage:true});
});

test("assigned parent can confirm own active step despite child run member",async({page})=>{
  await page.goto("/tests/fixtures/routine-handoffs.html?actor=owner&run=handoff");
  const card=page.locator("family-routines-card");
  const confirm=card.getByRole("button",{name:"Mark step done",exact:true});
  await expect(confirm).toHaveCount(1);
  await confirm.click();
  await expect(confirm).toHaveCount(0);
  expect((await page.evaluate(()=>window.calls)).map(c=>c.action)).toEqual(["routines.confirm"]);
});

test("role-revoked detached confirm button cannot send a stale action",async({page})=>{
  await page.goto("/tests/fixtures/routine-handoffs.html?actor=owner&run=handoff");
  const card=page.locator("family-routines-card");
  await expect(card.getByRole("button",{name:"Mark step done",exact:true})).toHaveCount(1);
  await page.evaluate(()=>window.staleButton=[...window.card.shadowRoot.querySelectorAll("button")].find(button=>button.textContent.trim()==="Mark step done"));
  await page.evaluate(()=>window.revokeOwner());
  await page.evaluate(()=>window.card.refresh());
  await expect(card.getByRole("button",{name:"Mark step done",exact:true})).toHaveCount(0);
  await page.evaluate(()=>window.staleButton.click());
  expect(await page.evaluate(()=>window.calls.length)).toBe(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
