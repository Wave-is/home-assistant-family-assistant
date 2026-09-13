import {test, expect} from "./control-audit.js";
import {SHOPPING_ITEM_COPY as COPY} from "../../custom_components/family_assistant/frontend/shopping-items.js";

for (const language of ["en", "ru", "uk"]) {
  test(`${language} shared buyer filter, reassignment and unassignment use the same item`, async ({page}) => {
    const copy = COPY[language];
    await page.setViewportSize({width:390,height:844});
    await page.goto(`/tests/fixtures/dashboard.html?view=shopping&lang=${language}`);
    await page.evaluate(async () => {
      window.fixture.shopping[0].buyer = "child";
      window.fixture.shopping[1].buyer = "owner";
      await window.card.refresh();
    });
    const card = page.locator("family-assistant-card");
    const rows = card.locator(".body > ul.list > li.item");
    await expect(rows).toHaveCount(2);
    await expect(card.locator(".shopping-filter")).toContainText(copy.buyer_shared);
    await card.getByLabel(copy.filter_label, {exact:true}).selectOption("mine");
    await expect(rows).toHaveCount(1);
    await card.getByLabel(copy.filter_label, {exact:true}).selectOption("buyer:child");
    await expect(rows).toHaveCount(1);
    await rows.getByRole("button", {name:copy.action_edit, exact:true}).click();
    let editor = card.locator(".shopping-editor");
    await editor.getByLabel(copy.label_buyer, {exact:true}).selectOption("owner");
    await editor.getByRole("button", {name:copy.action_review, exact:true}).click();
    await page.evaluate(() => {window.commitThenLose = true;});
    await editor.getByRole("button", {name:copy.action_confirm_edit, exact:true}).click();
    await expect(card.getByRole("alert")).toBeVisible();
    const first = await page.evaluate(() => structuredClone(window.calls[0]));
    expect(first.action).toBe("shopping.edit");
    expect(first.payload).toMatchObject({id:"S000001", revision:1, buyer:"owner"});
    await editor.getByRole("button", {name:copy.action_retry, exact:true}).click();
    await expect(editor).toHaveCount(0);
    expect(await page.evaluate(() => window.calls[1])).toEqual(first);
    await expect(rows).toHaveCount(0);
    await card.getByLabel(copy.filter_label, {exact:true}).selectOption("all");
    await expect(rows).toHaveCount(2);
    const assigned = rows.filter({hasText:copy.status_approved});
    await assigned.getByRole("button", {name:copy.action_edit, exact:true}).click();
    editor = card.locator(".shopping-editor");
    await editor.getByLabel(copy.label_buyer, {exact:true}).selectOption("");
    await editor.getByRole("button", {name:copy.action_review, exact:true}).click();
    await editor.getByRole("button", {name:copy.action_confirm_edit, exact:true}).click();
    await expect(editor).toHaveCount(0);
    await card.getByLabel(copy.filter_label, {exact:true}).selectOption("unassigned");
    await expect(rows).toHaveCount(1);
    expect(await page.evaluate(() => window.fixture.shopping[0])).toMatchObject({id:"S000001", buyer:null, quantity:3, purchased:1, unit:"kg", revision:3});
    expect(await page.evaluate(() => window.fixture.shopping.length)).toBe(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test("a child can still help buy another member's assigned shopping", async ({page}) => {
  await page.goto("/tests/fixtures/dashboard.html?view=shopping&role=child");
  await page.evaluate(async () => {window.fixture.shopping[0].buyer="owner"; await window.card.refresh();});
  const card=page.locator("family-assistant-card");
  await card.getByLabel(COPY.en.filter_label,{exact:true}).selectOption("mine");
  await expect(card.locator(".body > ul.list > li.item")).toHaveCount(0);
  await card.getByLabel(COPY.en.filter_label,{exact:true}).selectOption("all");
  await card.getByRole("button",{name:COPY.en.action_buy_remaining,exact:true}).click();
  await expect(card.locator(".shopping-archive")).toContainText(COPY.en.status_purchased);
  expect(await page.evaluate(()=>window.calls[0])).toMatchObject({action:"shopping.purchase",payload:{id:"S000001",quantity:2}});
  expect(await page.evaluate(()=>window.fixture.shopping[0])).toMatchObject({buyer:"owner",purchased:3,status:"purchased"});
});

for (const change of ["generation", "member", "actor"]) {
  test(`captured filter is inert after ${change} changes`, async ({page}) => {
    await page.goto("/tests/fixtures/dashboard.html?view=shopping");
    const card=page.locator("family-assistant-card");
    await card.getByLabel(COPY.en.filter_label,{exact:true}).selectOption("mine");
    const filter=await card.getByLabel(COPY.en.filter_label,{exact:true}).elementHandle();
    await page.evaluate(change=>{
      if(change==="generation")window.card._generation++;
      if(change==="member")window.card._data.members[0].revision++;
      if(change==="actor"){window.card._data.actor="child";window.card._data.role="child";}
    },change);
    await filter.selectOption("buyer:child");
    expect(await page.evaluate(()=>window.card._shoppingBuyerFilter.value)).toBe("mine");
    await page.evaluate(()=>window.card.render());
    await expect(card.getByLabel(COPY.en.filter_label,{exact:true})).toHaveValue("all");
    expect(await page.evaluate(()=>window.calls)).toHaveLength(0);
  });
}
