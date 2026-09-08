import {test,expect} from "@playwright/test";
import {PRICE_COPY as PRICE} from "../../custom_components/family_assistant/frontend/shopping-price.js";
import {SHOPPING_ITEM_COPY as ITEMS} from "../../custom_components/family_assistant/frontend/shopping-items.js";

for(const language of ["en","ru","uk"])test(`${language} mobile price total, shared disclosure and exact response-loss retry`,async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/tests/fixtures/dashboard.html?view=shopping&lang=${language}`);
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:ITEMS[language].action_partial_purchase,exact:true}).click();
  const form=card.locator("form").filter({has:page.locator(".shopping-price-fields")});
  await expect(form).toContainText(PRICE[language].shared);
  await expect(form.locator('[name="price_total"]')).toBeDisabled();
  await form.locator('[name="quantity"]').fill("0.5");
  await form.getByRole("checkbox").check();
  await form.locator('[name="price_total"]').fill("12,5000");
  await form.locator('[name="price_currency"]').fill("uah");
  await page.screenshot({path:`test-results/shopping-price-${language}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(()=>{window.commitThenLose=true;});
  await form.getByRole("button",{name:ITEMS[language].action_submit,exact:true}).click();
  await expect(card.getByRole("alert").filter({visible:true})).toBeVisible();
  const first=await page.evaluate(()=>structuredClone(window.calls[0]));
  expect(first.action).toBe("shopping.purchase");
  expect(first.payload.price).toEqual({total:"12.5",currency:"UAH"});
  expect(first.payload.quantity).toBe(0.5);
  await expect(form.locator('[name="price_total"]')).toBeDisabled();
  await page.evaluate(()=>{window.card._pending={id:"unrelated",fingerprint:"unrelated"};});
  await form.getByRole("button",{name:ITEMS[language].action_retry,exact:true}).click();
  await expect(form).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls[1])).toEqual(first);
  expect(await page.evaluate(()=>window.fixture.shopping[0].purchased)).toBe(1.5);
  await expect(card).toContainText("12.5 UAH");
});

test("focused price input does not retain a revoked actor draft",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:ITEMS.en.action_partial_purchase,exact:true}).click();
  const fields=card.locator(".shopping-price-fields");
  await fields.getByRole("checkbox").check();
  await fields.locator('[name="price_total"]').fill("12");
  await fields.locator('[name="price_total"]').focus();
  await page.evaluate(async()=>{window.fixture.members[0].revision++;await window.card.refresh();});
  await expect(fields).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toHaveLength(0);
});
