import {test,expect} from "@playwright/test";

for(const [language,title,more] of [
  ["en","Previous reports","Show earlier reports"],
  ["ru","Предыдущие отчёты","Показать более ранние отчёты"],
  ["uk","Попередні звіти","Показати давніші звіти"],
])test(`text report history ${language}: parent paging and role revocation`,async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/tests/fixtures/dashboard.html?view=tasks&lang=${language}&taskedit=1`);
  await expect(page.locator(".body > ul.list > li.item").first()).toBeVisible();
  await page.evaluate(()=>{
    const card=document.querySelector("family-assistant-card"),task=card._data.tasks[0];
    task.previous_reports=Array.from({length:22},(_,i)=>({report:`Synthetic report ${i}`,review_note:`Synthetic feedback ${i}`,submitted_at:"2026-09-07T08:00:00Z"}));
    task.report="Current corrected report";task.report_type="text";card.render();
  });
  const history=page.locator("[data-report-history]").first();
  await history.locator("summary").filter({hasText:title}).click();
  await expect(history.locator("li")).toHaveCount(20);
  await history.getByRole("button",{name:more,exact:true}).click();
  await expect(history.locator("li")).toHaveCount(22);
  await page.screenshot({path:`test-results/report-history-${language}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(()=>{const card=document.querySelector("family-assistant-card");card._data.role="child";card._data.actor="child";card.render();});
  await expect(page.locator("[data-report-history] details")).toHaveCount(0);
});

for(const [lang,label,add,save,done,report] of [
  ["en","Personal reminder — only for me","Add","Save","Confirm done","Send report"],
  ["ru","Личное напоминание — только для меня","Добавить","Сохранить","Подтвердить выполнение","Сдать отчёт"],
  ["uk","Особисте нагадування — лише для мене","Додати","Зберегти","Підтвердити виконання","Здати звіт"],
])test(`personal reminder ${lang}: own-only draft, no report, self completion`,async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/tests/fixtures/dashboard.html?view=tasks&lang=${lang}&taskedit=1&role=child`);
  await page.getByRole("button",{name:add,exact:true}).click();
  const form=page.locator("form[data-task-create]");
  await form.locator('input[name="title"]').fill("My private appointment");
  await form.getByLabel(label,{exact:true}).check();
  await expect(form.locator('select[name="assignee"]')).toBeDisabled();
  await expect(form.locator('select[name="report_type"]')).toHaveValue("none");
  await form.locator('input[name="due_at"]').fill("2026-10-20T10:00");
  await page.screenshot({path:`test-results/personal-task-${lang}.png`,fullPage:true});
  await form.getByRole("button",{name:save,exact:true}).click();
  const call=await page.evaluate(()=>window.calls[0]);
  expect(call.payload).toMatchObject({personal:true,assignee:"child",report_type:"none",grace_minutes:0});
  const item=page.locator("li.item").filter({hasText:"My private appointment"});
  await expect(item.getByRole("button",{name:report,exact:true})).toHaveCount(0);
  await item.getByRole("button",{name:done,exact:true}).click();
  expect(await page.evaluate(()=>window.calls.at(-1).action)).toBe("tasks.complete");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("Russian task editor preserves failed payload, clears deadline and retains progress",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=tasks&lang=ru&taskedit=1");
  const item=page.locator(".body > ul.list > li.item").first();
  await item.getByRole("checkbox").check();
  await item.getByRole("button",{name:"Начать",exact:true}).click();
  await expect(item.locator(".badge")).toHaveText("В работе");
  await item.getByRole("button",{name:"Изменить задачу",exact:true}).click();
  const form=item.locator("form");
  await form.getByLabel("Что нужно сделать?",{exact:true}).fill("Полить растения вечером");
  await form.getByLabel("Срок",{exact:true}).fill("");
  await page.evaluate(()=>window.failCommand=true);
  await form.getByRole("button",{name:"Сохранить",exact:true}).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(form.getByLabel("Что нужно сделать?",{exact:true})).toBeDisabled();
  await page.evaluate(()=>window.failCommand=false);
  await form.getByRole("button",{name:"Повторить",exact:true}).click();
  await expect(form).toHaveCount(0);
  await expect(item.locator(".badge")).toHaveText("В работе");
  await expect(item.getByRole("checkbox")).toBeChecked();
  const calls=await page.evaluate(()=>window.calls);
  expect(calls[2]).toEqual(calls[3]);expect(calls[2].payload.due_at).toBeNull();
  expect(calls[2].payload.revision).toBe(3);expect(calls[2].payload).not.toHaveProperty("assignee");
  await page.screenshot({path:"test-results/task-edit-mobile-ru.png",fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("Ukrainian task report goes through review and parent can request changes",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=tasks&lang=uk&taskedit=1&role=child");
  const item=page.locator(".body > ul.list > li.item").first();
  await item.getByRole("button",{name:"Здати звіт",exact:true}).click();
  await item.getByLabel("Звіт",{exact:true}).fill("Полито всі рослини");
  await item.getByRole("button",{name:"Зберегти",exact:true}).click();
  await expect(item.locator(".badge")).toHaveText("На перевірці");
  await expect(item.getByRole("checkbox")).toBeDisabled();
  await expect(item.getByRole("button",{name:"Підтвердити виконання",exact:true})).toHaveCount(0);
  await page.screenshot({path:"test-results/task-report-mobile-uk.png",fullPage:true});
  // A synthetic fresh parent projection; production identity comes from HA auth.
  await page.evaluate(()=>{
    const card=document.querySelector("family-assistant-card");card._data.role="owner";card._data.actor="owner";card.render();
  });
  await item.getByRole("button",{name:"Повернути на доопрацювання",exact:true}).click();
  await item.getByLabel("Зауваження до звіту",{exact:true}).fill("Перевір ще одну рослину");
  await item.getByRole("button",{name:"Зберегти",exact:true}).click();
  const last=await page.evaluate(()=>window.calls.at(-1));
  expect(last.action).toBe("tasks.request_changes");expect(last.payload.note).toBe("Перевір ще одну рослину");
});

test("new deadline uses household zone and ambiguous time is chosen explicitly",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=tasks&lang=ru&taskedit=1");
  await page.getByRole("button",{name:"Добавить",exact:true}).click();
  const form=page.locator("form[data-task-create]");
  await form.getByLabel("Что нужно сделать?",{exact:true}).fill("Собрать портфель");
  await form.getByLabel("Кому?",{exact:true}).selectOption("child");
  await form.locator('input[name="due_at"]').fill("2026-10-25T02:30");
  await form.getByRole("button",{name:"Сохранить",exact:true}).click();
  expect(await page.evaluate(()=>window.calls.length)).toBe(0);
  await form.locator('select[name="due_fold"]').selectOption("1");
  await form.getByLabel("Шаги — по одному в строке (необязательно)",{exact:true}).fill("Учебники\nТетради");
  await page.screenshot({path:"test-results/task-create-fold-ru.png",fullPage:true});
  await form.getByRole("button",{name:"Сохранить",exact:true}).click();
  const call=await page.evaluate(()=>window.calls[0]);
  expect(call.payload.due_at).toBe("2026-10-25T01:30:00.000Z");expect(call.payload.checklist).toEqual(["Учебники","Тетради"]);
});
