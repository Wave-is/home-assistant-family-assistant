import {test,expect} from "@playwright/test";

test("RU mobile owner weekly configuration saves parameters and stays responsive",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=court&lang=ru&courtedit=1");

  const card=page.locator("family-assistant-card");
  await expect(card).toBeVisible();

  // Initially config form is closed; click "Настроить отчёты"
  await card.getByRole("button",{name:"Настроить отчёты",exact:true}).click();

  // Form should now be open with config inputs
  const configForm=card.locator("form").first();
  await expect(configForm.getByRole("heading",{name:"Настройка еженедельных отчётов",exact:true})).toBeVisible();

  // Toggle weekly enabled
  await configForm.getByLabel("Включить еженедельные отчёты (по выбору; балансы не сбрасываются)",{exact:true}).check();

  // Select weekday (e.g. Wednesday = 2)
  await configForm.getByLabel("День недели отчёта",{exact:true}).selectOption("2");

  // Fill time
  await configForm.getByLabel("Время формирования",{exact:true}).fill("18:30");

  // Toggle second adult review
  await configForm.getByLabel("Требовать проверку независимым вторым родителем",{exact:true}).check();

  // Submit form
  await configForm.getByRole("button",{name:"Сохранить",exact:true}).click();

  // Form closes on success and button reverts to "Настроить отчёты"
  await expect(card.getByRole("button",{name:"Настроить отчёты",exact:true})).toBeVisible();

  // Verify ws call payload
  const calls=await page.evaluate(()=>window.calls);
  expect(calls.length).toBe(1);
  expect(calls[0].action).toBe("court.configure");
  expect(calls[0].payload).toEqual({
    revision:1,
    weekly_enabled:true,
    weekday:2,
    time:"18:30",
    second_adult_review:true
  });

  // Responsive check on 390px mobile viewport
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/court-config-mobile-ru.png",fullPage:true});
});

test("UK child submits appeal and ledger preserves original score reason alongside appeal",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=court&lang=uk&role=child&courtedit=1");

  const card=page.locator("family-assistant-card");
  await expect(card).toBeVisible();

  // Child should not see configure weekly reports button
  const summaryHeading=card.getByText("Підсумки тижня",{exact:true});
  await expect(summaryHeading).toBeVisible();
  expect((await summaryHeading.boundingBox()).height).toBeLessThan(45);
  expect((await summaryHeading.boundingBox()).width).toBeGreaterThan(100);
  await expect(card.getByRole("button",{name:"Налаштувати звіти"})).toHaveCount(0);
  // Child should not see award points button
  await expect(card.getByRole("button",{name:"Нарахувати або списати бали"})).toHaveCount(0);

  // Active ledger item C000001
  const item=card.locator("[data-court-ledger] ul.list > li.item").first();
  await expect(item.getByText("C000001: Дитина 1 · +2 · Допоміг з вечерею")).toBeVisible();

  // Click appeal button "Оскаржити"
  await item.getByRole("button",{name:"Оскаржити",exact:true}).click();

  const appealForm=item.locator("form");
  await expect(appealForm.getByText("Оскаржити нарахування")).toBeVisible();

  // Fill appeal reason
  await appealForm.getByLabel("Причина оскарження",{exact:true}).fill("Це була інша дитина");
  await appealForm.getByRole("button",{name:"Зберегти",exact:true}).click();

  // Verify websocket call
  const calls=await page.evaluate(()=>window.calls);
  expect(calls.length).toBe(1);
  expect(calls[0].action).toBe("court.appeal");
  expect(calls[0].payload).toEqual({
    id:"C000001",
    revision:1,
    reason:"Це була інша дитина"
  });

  // Original score reason is preserved intact in ledger, and pending appeal badge appears
  await expect(item.getByText("C000001: Дитина 1 · +2 · Допоміг з вечерею")).toBeVisible();
  await expect(item.getByText(/На розгляді: Дитина 1 · .* · "Це була інша дитина"/)).toBeVisible();

  // Child cannot resolve or reverse the pending appeal
  await expect(item.getByRole("button",{name:"Розглянути апеляцію"})).toHaveCount(0);
  await expect(item.getByRole("button",{name:"Скасувати"})).toHaveCount(0);

  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/court-child-appeal-uk.png",fullPage:true});
});

test("second-adult-review guard blocks authoring parent from resolving and allows independent parent",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  // Load court in UK language as owner with courtedit
  await page.goto("/tests/fixtures/dashboard.html?view=court&lang=uk&courtedit=1");

  const card=page.locator("family-assistant-card");
  await expect(card).toBeVisible();

  // Set up pending appeal on C000001 (which was authored by owner) and enable second_adult_review in synthetic state
  await page.evaluate(()=>{
    const cardEl=document.querySelector("family-assistant-card");
    window.courtFixture.court_config.second_adult_review=true;
    const rec=window.courtFixture.court.find(c=>c.id==="C000001");
    rec.actor="owner";
    rec.appeal={
      status:"pending",
      actor:"child",
      reason:"Помилковий запис",
      at:"2026-09-06T09:00:00Z"
    };
    rec.revision=2;
    cardEl._data=structuredClone(window.courtFixture);
    cardEl.render();
  });

  const item=card.locator("[data-court-ledger] ul.list > li.item").first();

  // Because current actor is "owner" (author of C000001) and second_adult_review is true,
  // notice is rendered and resolve button is blocked
  await expect(item.locator(".notice")).toHaveText(
    "Потрібна перевірка іншим дорослим: автор запису та автор апеляції не можуть її розглядати або скасовувати."
  );
  await expect(item.getByRole("button",{name:"Розглянути апеляцію"})).toHaveCount(0);
  await expect(item.getByRole("button",{name:"Скасувати"})).toHaveCount(0);

  // Switch actor to parent2 (an independent active parent in the household)
  await page.evaluate(()=>{
    const cardEl=document.querySelector("family-assistant-card");
    window.courtFixture.actor="parent2";
    window.courtFixture.role="parent";
    cardEl._data=structuredClone(window.courtFixture);
    cardEl.render();
  });

  // Now the independent parent sees the resolve button
  await expect(item.getByRole("button",{name:"Розглянути апеляцію",exact:true})).toBeVisible();
  await item.getByRole("button",{name:"Розглянути апеляцію",exact:true}).click();

  const resolveForm=item.locator("form");
  await expect(resolveForm.getByText("Розглянути апеляцію")).toBeVisible();

  // Verify decision options ("Скасувати бал" / "Залишити в силі")
  await resolveForm.getByLabel("Рішення",{exact:true}).selectOption("reverse");
  await resolveForm.getByLabel("Причина",{exact:true}).fill("Підтверджено незалежно");
  await resolveForm.getByRole("button",{name:"Зберегти",exact:true}).click();

  const lastCall=await page.evaluate(()=>window.calls.at(-1));
  expect(lastCall.action).toBe("court.resolve_appeal");
  expect(lastCall.payload).toEqual({
    id:"C000001",
    revision:2,
    decision:"reverse",
    reason:"Підтверджено незалежно"
  });

  // Record is now reversed, original reason is retained
  await expect(item.getByText("C000001: Дитина 1 · +2 · Допоміг з вечерею")).toBeVisible();
  await expect(item.locator(".badge").first()).toHaveText("Скасовано");

  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/court-second-adult-review-uk.png",fullPage:true});
});

test("stale revision collision shows conflict error and explicit close/reopen recovers fresh form",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=court&lang=ru&courtedit=1");

  const card=page.locator("family-assistant-card");
  await expect(card).toBeVisible();

  // Open config form
  await card.getByRole("button",{name:"Настроить отчёты",exact:true}).click();
  const configForm=card.locator("form").first();
  await expect(configForm.getByRole("heading",{name:"Настройка еженедельных отчётов",exact:true})).toBeVisible();

  // Simulate background config mutation (revision advances from 1 to 2) while form is open
  await page.evaluate(()=>{
    const cardEl=document.querySelector("family-assistant-card");
    window.courtFixture.court_config.revision=2;
    window.courtFixture.court_config.time="12:00";
    cardEl._data=structuredClone(window.courtFixture);
  });

  // Owner tries to submit draft with stale revision (1)
  await configForm.getByRole("button",{name:"Сохранить",exact:true}).click();

  // Conflict error notice role="alert" appears with RU localized conflict message
  const alert=card.getByRole("alert");
  await expect(alert).toBeVisible();
  await expect(alert).toHaveText("Запись уже изменилась. Обновите страницу.");

  // No ws call was dispatched because front-end conflict check prevented overwrite
  expect(await page.evaluate(()=>window.calls.length)).toBe(0);

  // Explicit close recovers cleanly: click "Закрыть настройки"
  await card.getByRole("button",{name:"Закрыть настройки",exact:true}).click();
  await expect(card.locator("form")).toHaveCount(0);

  // Explicit reopen loads fresh revision (2) and fresh values
  await card.getByRole("button",{name:"Настроить отчёты",exact:true}).click();
  const freshForm=card.locator("form").first();
  await expect(freshForm).toBeVisible();
  await expect(freshForm.getByLabel("Время формирования",{exact:true})).toHaveValue("12:00");

  // Submitting now sends revision: 2 successfully
  await freshForm.getByRole("button",{name:"Сохранить",exact:true}).click();

  const calls=await page.evaluate(()=>window.calls);
  expect(calls.length).toBe(1);
  expect(calls[0].action).toBe("court.configure");
  expect(calls[0].payload.revision).toBe(2);
  await expect(card.locator("form")).toHaveCount(0);
  await expect(card.getByRole("alert")).toHaveCount(0);

  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/court-stale-recovery-ru.png",fullPage:true});
});
