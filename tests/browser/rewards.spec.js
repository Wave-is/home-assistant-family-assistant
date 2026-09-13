import {test,expect} from "./control-audit.js";

test("RU mobile parent creates catalog then edits name/cost on frozen retry after window.failCommand before effect",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=court&lang=ru&rewards=1");
  const card=page.locator("family-assistant-card");
  await expect(card).toBeVisible();

  await card.getByRole("button",{name:"Новая награда",exact:true}).click();
  const createForm=card.locator("form.editor");
  await createForm.getByLabel("Название",{exact:true}).fill("Настольная игра");
  await createForm.getByLabel("Стоимость (баллы 1–10000)",{exact:true}).fill("8");
  await createForm.locator('button[type="submit"]').click();

  const item=card.locator("section.item:has-text('Каталог') ul.list > li.item").filter({hasText:"Настольная игра"});
  await expect(item).toBeVisible();
  await expect(item.getByText("Стоимость: 8 баллов")).toBeVisible();
  await expect(card.getByRole("alert")).toHaveCount(0);

  await item.getByRole("button",{name:"Изменить",exact:true}).click();
  const editForm=card.locator("form.editor");
  const nameInput=editForm.getByLabel("Название",{exact:true});
  const costInput=editForm.getByLabel("Стоимость (баллы 1–10000)",{exact:true});
  await nameInput.fill("Книга сказок");
  await costInput.fill("12");

  await page.evaluate(()=>window.failCommand=true);
  await editForm.locator('button[type="submit"]').click();
  await expect(card.getByRole("alert")).toBeVisible();
  await expect(nameInput).toBeDisabled();
  await expect(costInput).toBeDisabled();
  const retryBtn=editForm.locator('button[type="submit"]');
  await expect(retryBtn).toHaveText("Повторить");

  await page.evaluate(()=>window.failCommand=false);
  await retryBtn.click();

  const calls=await page.evaluate(()=>window.calls.filter(c=>c.action==="court.reward_save"));
  expect(calls.length).toBe(3);
  expect(calls[1].payload).toEqual(calls[2].payload);
  expect(calls[1].operation_id).toBe(calls[2].operation_id);
  expect(calls[2].payload).toEqual({
    id:"R000002",revision:1,name:"Книга сказок",cost:12,description:"",enabled:true,eligible:[],request_ttl_hours:72
  });

  await expect(card.locator("form.editor")).toHaveCount(0);
  await expect(card.getByRole("alert")).toHaveCount(0);
  const updatedItem=card.locator("section.item:has-text('Каталог') ul.list > li.item").filter({hasText:"Книга сказок"});
  await expect(updatedItem).toBeVisible();
  await expect(updatedItem.getByText("Стоимость: 12 баллов")).toBeVisible();

  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/rewards-catalog-edit-ru.png",fullPage:true});
});

test("UK child requests privilege with points reserved then owner approves/fulfills",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=court&lang=uk&role=child&rewards=1");
  const card=page.locator("family-assistant-card");
  await expect(card).toBeVisible();

  const catItem=card.locator("section.item:has-text('Каталог') ul.list > li.item").filter({hasText:"Cinema trip"});
  await catItem.getByRole("button",{name:"Запитати",exact:true}).click();
  const reqForm=catItem.locator("form.editor");
  await reqForm.getByLabel("Примітка (необов'язково)",{exact:true}).fill("З друзями");
  await reqForm.locator('button[type="submit"]').click();

  const balancesSec=card.locator("section.item:has-text('Баланси винагород')");
  await expect(balancesSec.getByText("Зарезервовано: 10")).toBeVisible();
  await expect(balancesSec.getByText("Доступно: 5")).toBeVisible();

  const reqItem=card.locator("section.item:has-text('Запити') ul.list > li.item").filter({hasText:"Cinema trip"});
  await expect(reqItem).toBeVisible();
  await expect(reqItem.locator(":scope > .sub").first()).toContainText("Запитано");
  await expect(reqItem.getByRole("button",{name:"Схвалити"})).toHaveCount(0);

  await page.evaluate(()=>{
    const c=document.querySelector("family-assistant-card");
    window.rewardFixture.actor="owner";
    window.rewardFixture.role="owner";
    c._data=structuredClone(window.rewardFixture);
    c.render();
  });

  await expect(reqItem.getByRole("button",{name:"Схвалити",exact:true})).toBeVisible();
  await reqItem.getByRole("button",{name:"Схвалити",exact:true}).click();
  const approveForm=reqItem.locator("form.editor");
  await approveForm.getByLabel(/Обов'язкова причина/).fill("Гарні оцінки");
  await approveForm.locator('button[type="submit"]').click();

  await expect(reqItem.locator(":scope > .sub").first()).toContainText("Схвалено");
  await expect(reqItem.getByRole("button",{name:"Виконати",exact:true})).toBeVisible();
  await reqItem.getByRole("button",{name:"Виконати",exact:true}).click();
  const fulfillForm=reqItem.locator("form.editor");
  await fulfillForm.getByLabel(/Обов'язкова причина/).fill("Квитки придбано");
  await fulfillForm.locator('button[type="submit"]').click();

  await expect(card.getByRole("alert")).toHaveCount(0);
  const termDetails=card.locator("section.item:has-text('Запити') > details");
  await expect(termDetails).toBeVisible();
  await termDetails.locator(":scope > summary").click();
  const fulfilledReq=termDetails.locator("ul.list > li.item").filter({hasText:"Cinema trip"});
  await expect(fulfilledReq).toBeVisible();
  await expect(fulfilledReq.getByText("Cinema trip (10)")).toBeVisible();
  await expect(fulfilledReq.locator(":scope > .sub").first()).toContainText("Виконано");

  const histDetails=fulfilledReq.locator("details");
  await histDetails.locator("summary").click();
  await expect(histDetails.getByText(/Схвалено — Гарні оцінки/)).toBeVisible();
  await expect(histDetails.getByText(/Виконано — Квитки придбано/)).toBeVisible();

  await expect(balancesSec.getByText("Витрачено: 10")).toBeVisible();
  await expect(balancesSec.locator("li.item").filter({hasText:"Дитина 1"}).getByText("Зарезервовано: 0")).toBeVisible();

  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/rewards-child-request-uk.png",fullPage:true});
});

test("stale catalog edit rejects after out-of-band fixture revision update while DOM focused and no command",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=court&lang=ru&rewards=1");
  const card=page.locator("family-assistant-card");
  await expect(card).toBeVisible();

  const item=card.locator("section.item:has-text('Каталог') ul.list > li.item").filter({hasText:"Cinema trip"});
  await item.getByRole("button",{name:"Изменить",exact:true}).click();
  const editForm=card.locator("form.editor");
  const nameInput=editForm.getByLabel("Название",{exact:true});
  await nameInput.focus();
  await nameInput.fill("Вечер кино");

  await page.evaluate(()=>{
    const c=document.querySelector("family-assistant-card");
    const it=window.rewardFixture.rewards.catalog.find(x=>x.id==="R000001");
    it.revision=2;
    it.cost=20;
    c._data=structuredClone(window.rewardFixture);
  });

  const callsBefore=await page.evaluate(()=>window.calls.length);
  await editForm.locator('button[type="submit"]').click();

  const callsAfter=await page.evaluate(()=>window.calls.length);
  expect(callsAfter).toBe(callsBefore);

  const alert=card.getByRole("alert");
  await expect(alert).toBeVisible();
  await expect(alert).toHaveText("Запись уже изменилась. Обновите страницу.");
  await expect(card.locator("form.editor")).toHaveCount(0);

  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/rewards-stale-catalog-ru.png",fullPage:true});
});
