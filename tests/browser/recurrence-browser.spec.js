import {test,expect} from "@playwright/test";

const field=(card,key)=>card.locator(`[data-recurrence-control="${key}"]`);

test("RU recurring calendar uses event clock, task links, exceptions and one frozen retry",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=calendar&lang=ru");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Новое событие",exact:true}).click();
  await card.getByLabel("Название",{exact:true}).fill("Еженедельная прогулка");
  await card.getByLabel("Весь день",{exact:true}).check();
  await card.locator('[name="start_date"]').fill("2026-10-05");
  await card.locator('[name="end_date"]').fill("2026-10-06");
  await card.locator('[name="participants"][value="child"]').check();
  await card.locator('[name="task_ids"]').first().check();
  await field(card,"enabled").check();
  await field(card,"frequency").selectOption("weekly");
  await field(card,"interval").fill("2");
  await field(card,"exceptions").fill("2026-10-19\n2026-11-02");
  await field(card,"until").fill("2027-01-01");
  await expect(field(card,"catchup_hours")).toBeHidden();
  await expect(field(card,"start_date")).toHaveValue("2026-10-05");
  await expect(field(card,"time")).toHaveValue("00:00");
  await expect(field(card,"timezone")).toBeDisabled();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/recurrence-calendar-ru.png",fullPage:true});
  await page.evaluate(()=>window.failCommand=true);
  await card.getByRole("button",{name:"Сохранить",exact:true}).click();
  await expect(card.getByRole("button",{name:"Повторить",exact:true})).toBeVisible();
  await page.evaluate(()=>window.failCommand=false);
  await card.getByRole("button",{name:"Повторить",exact:true}).click();
  await expect(field(card,"enabled")).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(2);expect(calls[0].operation_id).toBe(calls[1].operation_id);
  expect(calls[0].payload).toEqual(calls[1].payload);
  expect(calls[1].payload.rule).toMatchObject({frequency:"weekly",interval:2,start_date:"2026-10-05",time:"00:00",timezone:"Europe/Kyiv",until:"2027-01-01",exceptions:["2026-10-19","2026-11-02"],catchup_hours:24});
  expect(calls[1].payload.task_ids).toHaveLength(1);
});

test("Calendar rejects a second-fold recurrence but preserves a one-off exact timestamp",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=calendar&lang=en");
  const card=page.locator("family-assistant-card");
  await card.locator('[data-calendar-event="E000001"]').getByRole("button",{name:"Edit",exact:true}).click();
  await field(card,"enabled").check();
  await card.getByRole("button",{name:"Save",exact:true}).click();
  expect(await page.evaluate(()=>window.calls.length)).toBe(0);
  await expect(card.locator("form")).toContainText("first occurrence");
  await field(card,"enabled").uncheck();
  await card.getByRole("button",{name:"Save",exact:true}).click();
  await expect(field(card,"enabled")).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls[0].payload.start)).toBe("2026-10-25T03:30:15+02:00");
});

test("UK routine recurrence remains intact on title edits and can explicitly be disabled",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/routines.html?lang=uk");
  await page.evaluate(()=>{
    window.fixture.routines.templates[0].rule={frequency:"monthly",interval:3,start_date:"2026-09-07",time:"07:35",timezone:"Europe/Kyiv",weekdays:[1,4],month_day:31,until:"2028-01-01",exceptions:["2027-01-31"],catchup_hours:48};
    window.card.refresh();
  });
  const card=page.locator("family-routines-card");
  await card.getByRole("button",{name:"Редагувати",exact:true}).click();
  await expect(field(card,"frequency")).toHaveValue("monthly");
  await expect(field(card,"month_day")).toHaveValue("31");
  await card.getByLabel("Назва",{exact:true}).fill("Ранковий маршрут");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/recurrence-routines-uk.png",fullPage:true});
  await card.getByRole("button",{name:"Зберегти",exact:true}).click();
  await expect(field(card,"enabled")).toHaveCount(0);
  const first=await page.evaluate(()=>window.calls[0]);
  expect(first.payload.rule).toEqual({frequency:"monthly",interval:3,start_date:"2026-09-07",time:"07:35",timezone:"Europe/Kyiv",weekdays:[1,4],month_day:31,until:"2028-01-01",exceptions:["2027-01-31"],catchup_hours:48});
  await card.getByRole("button",{name:"Редагувати",exact:true}).click();
  await field(card,"enabled").uncheck();
  await card.getByRole("button",{name:"Зберегти",exact:true}).click();
  await expect(field(card,"enabled")).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls[1].payload.rule)).toBeNull();
});
