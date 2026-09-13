import { test, expect } from "./control-audit.js";

test("Ukrainian reviewed metadata edit keeps quantities and exact operation after lost response", async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=shopping&lang=uk");
  const card = page.locator("family-assistant-card");
  await card.locator(".body > ul.list > li.item").filter({hasText:"Яблука"}).getByRole("button",{name:"Змінити дані",exact:true}).click();
  const editor = card.locator(".shopping-editor");
  await expect(editor.locator('[name="quantity"]')).toHaveCount(0);
  await editor.getByLabel("Категорія",{exact:true}).fill("Фрукти");
  await editor.getByLabel("Магазин",{exact:true}).fill("Ринок");
  await editor.getByLabel("Примітка",{exact:true}).fill("Для всієї родини");
  await editor.getByLabel("Покупець",{exact:true}).selectOption("owner");
  await editor.getByRole("button",{name:"Перевірити",exact:true}).click();
  await expect(editor).toContainText("Вона не є приватною");
  expect(await page.evaluate(()=>window.calls)).toHaveLength(0);
  await page.screenshot({path:"test-results/shopping-edit-review-uk.png",fullPage:true});
  await page.evaluate(()=>{window.commitThenLose=true;});
  await editor.getByRole("button",{name:"Зберегти перевірені зміни",exact:true}).click();
  await expect(card.getByRole("alert")).toBeVisible();
  const first = await page.evaluate(()=>structuredClone(window.calls[0]));
  expect(first.action).toBe("shopping.edit");
  expect(first.payload).toEqual({id:"S000001",revision:1,name:"Яблука",category:"Фрукти",store:"Ринок",note:"Для всієї родини",buyer:"owner"});
  await page.evaluate(()=>{window.card._pending={id:"unrelated-operation",fingerprint:"unrelated"};});
  await editor.getByRole("button",{name:"Повторити",exact:true}).click();
  await expect(editor).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls[1])).toEqual(first);
  expect(await page.evaluate(()=>window.fixture.shopping[0])).toMatchObject({revision:2,quantity:3,purchased:1,unit:"kg",status:"approved"});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("focused shopping review is revoked on same-ID buyer replacement", async ({page}) => {
  await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Add shopping item",exact:true}).click();
  const editor=card.locator(".shopping-editor");
  await editor.getByLabel("Name",{exact:true}).fill("Synthetic item");
  await editor.getByLabel("Assigned to",{exact:true}).selectOption("child");
  await editor.getByLabel("Name",{exact:true}).focus();
  await page.evaluate(async()=>{window.fixture.members[1].revision++;await window.card.refresh();});
  await expect(editor).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toHaveLength(0);
});

test("child shopping creation stays a parent-reviewed proposal", async ({page}) => {
  await page.goto("/tests/fixtures/dashboard.html?view=shopping&lang=ru&role=child");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Добавить покупку",exact:true}).click();
  const editor=card.locator(".shopping-editor");
  await expect(editor).toContainText("будет ждать подтверждения родителя");
  await editor.getByLabel("Название",{exact:true}).fill("Цветные карандаши");
  await expect(editor.locator('select[name="buyer"] option')).toHaveCount(2);
  await editor.getByRole("button",{name:"Проверить",exact:true}).click();
  await editor.getByRole("button",{name:"Добавить в список покупок",exact:true}).click();
  await expect(editor).toHaveCount(0);
  expect(await page.evaluate(()=>window.fixture.shopping.at(-1))).toMatchObject({creator:"child",status:"pending"});
});
