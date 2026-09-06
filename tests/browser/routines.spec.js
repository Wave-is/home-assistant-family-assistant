import {test,expect} from "@playwright/test";

test("Russian mobile ordered editor keeps order, retries one payload and closes after real card refresh",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/routines.html?lang=ru");
  const card=page.locator("family-routines-card");
  await card.getByRole("button",{name:"Новый распорядок",exact:true}).click();
  await card.getByLabel("Название",{exact:true}).fill("Сборы на прогулку");
  await card.getByLabel("Родитель 1",{exact:true}).uncheck();
  await card.getByLabel("Ребёнок 1",{exact:true}).check();
  await card.getByLabel("Название шага",{exact:true}).fill("Одеться");
  await card.getByRole("button",{name:"Добавить шаг",exact:true}).click();
  await card.getByLabel("Название шага",{exact:true}).nth(1).fill("Взять воду");
  const offsets=card.getByLabel("Смещение от начала (минут, 0..10080)",{exact:true});
  await offsets.first().fill("10");await offsets.nth(1).fill("5");
  await card.getByRole("button",{name:"Сохранить",exact:true}).click();
  await expect(card.getByRole("alert")).toContainText("Смещение шагов не может уменьшаться");
  expect(await page.evaluate(()=>window.calls.length)).toBe(0);
  expect(await card.getByLabel("Название шага",{exact:true}).first().inputValue()).toBe("Одеться");
  await offsets.first().fill("0");
  await page.evaluate(()=>window.failCommand=true);
  await card.getByRole("button",{name:"Сохранить",exact:true}).click();
  await expect(card.getByRole("button",{name:"Повторить",exact:true})).toBeVisible();
  await page.evaluate(()=>window.failCommand=false);
  await card.getByRole("button",{name:"Повторить",exact:true}).click();
  await expect(card.getByLabel("Название шага",{exact:true})).toHaveCount(0);
  await expect(card.getByText("Сборы на прогулку",{exact:true})).toBeVisible();
  const calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(2);expect(calls[0].operation_id).toBe(calls[1].operation_id);
  expect(calls[0].payload).toEqual(calls[1].payload);
  expect(calls[1].payload.steps.map(s=>s.title)).toEqual(["Одеться","Взять воду"]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/routines-mobile-ru.png",fullPage:true});
});

test("Ukrainian child sees only own step action and uses a fresh nonce for the next step",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/routines.html?lang=uk&child");
  const card=page.locator("family-routines-card");
  await expect(card.getByRole("button",{name:"Рішення батьків",exact:true})).toHaveCount(0);
  const confirm=card.getByRole("button",{name:"Позначити виконання кроку",exact:true});
  await expect(confirm).toHaveCount(1);await confirm.click();
  expect(await page.evaluate(()=>window.calls[0].payload.nonce)).toBe("synthetic-fresh-first");
  await expect(confirm).toHaveCount(1);
  await page.screenshot({path:"test-results/routines-child-uk.png",fullPage:true});
  await confirm.click();await expect(confirm).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls);
  expect(calls.map(c=>c.payload.step)).toEqual([0,1]);
  expect(calls[1].payload.nonce).toBe("synthetic-fresh-second");
  expect(await page.evaluate(()=>window.fixture.routines.runs[0].status)).toBe("completed");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("Owner observation settings validate input and survive the actual card refresh",async({page})=>{
  await page.goto("/tests/fixtures/routines.html?lang=en");
  const card=page.locator("family-routines-card");
  await card.getByText("Entity observation allowlist",{exact:true}).first().click();
  await card.getByRole("button",{name:"Edit allowlist",exact:true}).click();
  const editor=card.getByLabel("Entity observation allowlist",{exact:true});
  await editor.fill("Switch.INVALID");
  await card.getByRole("button",{name:"Save",exact:true}).click();
  await expect(card.getByRole("alert")).toContainText(/lowercase|format|invalid/i);
  expect(await page.evaluate(()=>window.calls.length)).toBe(0);
  await editor.fill("binary_sensor.synthetic_ready\nsensor.synthetic_temperature");
  await card.getByRole("button",{name:"Save",exact:true}).click();
  await expect(editor).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls[0].payload.entity_allowlist)).toHaveLength(2);
  expect(await page.evaluate(()=>window.fixture.routines.config.revision)).toBe(1);
});
