import {test,expect} from "@playwright/test";

test("RU mobile calendar creates all-day family event and requires export consent",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=calendar&lang=ru");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Новое событие",exact:true}).click();
  await card.getByLabel("Название",{exact:true}).fill("Семейный пикник");
  await card.getByLabel("Весь день",{exact:true}).check();
  await card.locator('[name="start_date"]').fill("2026-10-10");
  await card.locator('[name="end_date"]').fill("2026-10-11");
  await card.locator('[name="preparation"]').fill("Взять воду\nСобрать рюкзак");
  await card.locator('[name="reminders"]').fill("60, 15");
  await card.getByRole("button",{name:"Сохранить",exact:true}).click();
  await expect(card.locator('[data-calendar-events]')).toContainText("Семейный пикник");
  const saved=await page.evaluate(()=>window.calls[0]);
  expect(saved.action).toBe("calendar.save");expect(saved.payload.start).toBe("2026-10-10");
  expect(saved.payload.reminder_minutes).toEqual([60,15]);expect(saved.payload.all_day).toBe(true);
  await card.getByRole("button",{name:"Изменить",exact:true}).first().click();
  await card.getByRole("button",{name:"Сохранить",exact:true}).click();
  expect(await page.evaluate(()=>window.calls.length)).toBe(1);
  await card.locator('[name="confirm_public_visibility"]').check();
  await card.getByRole("button",{name:"Сохранить",exact:true}).click();
  await expect(card.locator('[name="confirm_public_visibility"]')).toHaveCount(0);
  expect(await page.evaluate(()=>window.calendarFixture.calendar.config.publish_to_ha)).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/calendar-mobile-ru.png",fullPage:true});
});

test("UK child can edit own proposal without losing the exact folded timestamp",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=calendar&lang=uk&role=child");
  const card=page.locator("family-assistant-card");
  await expect(card.getByRole("button",{name:"Схвалити",exact:true})).toHaveCount(0);
  await card.locator('[data-calendar-event="E000001"]').getByRole("button",{name:"Редагувати",exact:true}).click();
  await card.getByLabel("Назва",{exact:true}).fill("Поїздка до музею");
  await card.getByRole("button",{name:"Зберегти",exact:true}).click();
  await expect(card.locator('[data-calendar-events]')).toContainText("Поїздка до музею");
  const call=await page.evaluate(()=>window.calls[0]);
  expect(call.payload.start).toBe("2026-10-25T03:30:15+02:00");
  expect(call.payload.end).toBe("2026-10-25T04:30:45+02:00");
  expect(call.payload.revision).toBe(1);
  expect(await page.evaluate(()=>window.calendarFixture.calendar.events[0].status)).toBe("tentative");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/calendar-child-uk.png",fullPage:true});
});

test("Parent approves then cancels calendar event with durable visible reasons",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=calendar&lang=en");
  const card=page.locator("family-assistant-card"),event=card.locator('[data-calendar-event="E000001"]');
  await event.getByRole("button",{name:"Approve",exact:true}).click();
  await card.getByLabel("Reason",{exact:true}).fill("Synthetic trip approved");
  await card.getByRole("button",{name:"Save",exact:true}).click();
  await expect(event).toContainText("Confirmed");
  await event.getByRole("button",{name:"Cancel event",exact:true}).click();
  await card.getByLabel("Reason",{exact:true}).fill("Synthetic change of plans");
  await card.getByRole("button",{name:"Save",exact:true}).click();
  await expect(card.locator('[data-calendar-agenda]')).not.toContainText("School outing");
  await event.getByText("History",{exact:true}).click();
  await expect(event).toContainText("Synthetic trip approved");
  await expect(event).toContainText("Synthetic change of plans");
  const calls=await page.evaluate(()=>window.calls);
  expect(calls.map(c=>c.payload.revision)).toEqual([1,2]);
});
