import {test,expect} from "@playwright/test";

async function addMemberWorkspaceFixture(page){
  await page.evaluate(async()=>{
    const data=window.fixture.data,view=data.view;
    data.members.push({id:"M4",name:"Alex Example",role:"child",active:true,language:"en",revision:4,aliases:[]});view.members=structuredClone(data.members);
    view.settings.modules.push("alarms","digests","routines");
    view.school={timetables:[],upcoming:[],homework:[],preparations:[],preparation_reminders:{policy:{enabled:true,days_before:1,time:"19:00",timezone:"UTC"},self_targets:data.members.filter(item=>item.role==="child").map(member=>({member:member.id,member_revision:member.revision,recipient_revision:1,subscription_revision:null,enabled:false}))}};
    view.alarms=[{id:"A1",member:"M4",name:"Alex wake-up",revision:1,time:"07:00",timezone:"UTC",days:[0,1,2,3,4],enabled:true,exceptions:[],profile:"gentle",second_min:12,second_max:18,recheck_grace:60,penalty:0}];
    data.member_readiness=[{id:"M3",alarms:{total:1,enabled:0,strict:0,output_configured:false,issues:["alarm_schedules_disabled"]},school:{timetables:0,issues:["school_no_timetable"]}}];
    await window.panel.loadData();
  });
}

test("Russian mobile profile editing preserves aliases and optional fields across tabs",async({page},testInfo)=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/panel.html?lang=ru");const panel=page.locator("family-assistant-panel");
  await panel.getByRole("button",{name:"Sam Example",exact:false}).click();
  await panel.locator('[name="name"]').fill("Synthetic Child");await panel.locator('[name="aliasesText"]').fill("Sunny, Sunshine");
  await panel.locator(".panel-subtabs").getByRole("button",{name:"Дополнительно",exact:true}).click();
  await panel.locator('[name="birth_date"]').fill("2012-07-04");await panel.locator('[name="avatar"]').selectOption("robot");
  await page.screenshot({path:testInfo.outputPath("profile-ru-mobile.png"),fullPage:true});
  await panel.locator("#save-member").click();await expect(panel).toContainText("Сохранено и проверено");
  const write=await page.evaluate(()=>window.fixture.calls.find(m=>m.action==="members.save"));
  expect(write.payload).toMatchObject({id:"M3",revision:3,name:"Synthetic Child",aliases:["Sunny","Sunshine"],birth_date:"2012-07-04",avatar:"robot"});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("Ukrainian dark mode settings retain same-day zero and exact retry payload",async({page},testInfo)=>{
  await page.setViewportSize({width:390,height:844});await page.goto("/tests/fixtures/panel.html?lang=uk&theme=dark");
  const panel=page.locator("family-assistant-panel");await panel.locator("#panel-search").fill("школа");
  await panel.locator(".panel-search-result").first().click();await panel.locator('[name="school_preparation_reminders"]').check();
  await panel.locator('[name="school_preparation_days_before"]').selectOption("0");await panel.locator('[name="school_preparation_time"]').fill("17:45");
  await page.evaluate(()=>window.fixture.failNext=true);await panel.locator("#save-settings").click();await expect(panel.locator('[role="alert"]')).toBeVisible();
  await expect(panel.locator('[name="school_preparation_time"]')).toBeDisabled();
  await page.screenshot({path:testInfo.outputPath("school-uk-dark-retry.png"),fullPage:true});
  await panel.locator("#save-settings").click();await expect(panel).toContainText("Збережено й перевірено");
  const writes=await page.evaluate(()=>window.fixture.calls.filter(m=>m.action==="settings.patch"));expect(writes).toHaveLength(2);expect(writes[1]).toEqual(writes[0]);expect(writes[0].payload.changes.school_preparation_days_before).toBe(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("setup resumes at persisted step and never claims unknown Telegram checks passed",async({page},testInfo)=>{
  await page.setViewportSize({width:1280,height:900});await page.goto("/tests/fixtures/panel.html?lang=en");const panel=page.locator("family-assistant-panel");
  await page.screenshot({path:testInfo.outputPath("overview-en-desktop.png"),fullPage:true});
  await panel.locator("#setup-guide").click();await panel.getByRole("button",{name:"Continue",exact:true}).click();
  await expect(panel.locator('[aria-current="step"]')).toContainText("2. Connections");await expect(panel).toContainText("Ordinary text receptionNot checked");
  await page.reload();await panel.locator("#setup-guide").click();await expect(panel.locator('[aria-current="step"]')).toContainText("2. Connections");
  await panel.getByRole("button",{name:"Set up later",exact:true}).click();await expect(panel.locator('[aria-current="step"]')).toContainText("3. Capabilities");
  const data=await page.evaluate(()=>window.fixture.data);expect(data.onboarding.skipped).toContain("telegram");expect(data.view.settings.automatic_penalties).toBe(false);
});

test("existing task workspace loads locally, duplicate resources do not crash",async({page})=>{
  const errors=[];page.on("pageerror",error=>errors.push(error.message));
  await page.goto("/tests/fixtures/panel.html?lang=en");await page.evaluate(()=>window.panel.openModuleView("tasks",true));
  const card=page.locator("family-assistant-card");await expect(card).toBeVisible();await expect(card).toContainText("Tasks");
  await page.evaluate(async()=>{await import("/custom_components/family_assistant/frontend/family-assistant.js?again=1");await import("/custom_components/family_assistant/frontend/family-panel.js?again=1");});expect(errors).toEqual([]);
  expect((await page.evaluate(()=>window.fixture.calls)).some(m=>m.type==="family_assistant/view"&&m.entry_id==="synthetic")).toBe(true);
});

test("read-only child panel has no owner edits or secret connection configuration",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en&role=child");const panel=page.locator("family-assistant-panel");await expect(panel.locator("#add-member")).toHaveCount(0);
  await panel.getByRole("button",{name:"Sam Example",exact:false}).click();await expect(panel.locator("#save-member")).toHaveCount(0);await expect(panel.locator('[name="name"]')).toBeDisabled();
});

test("Telegram member and group enrollment require an owner-reviewed candidate",async({page},testInfo)=>{
  await page.setViewportSize({width:390,height:844});await page.goto("/tests/fixtures/panel.html?lang=ru");const panel=page.locator("family-assistant-panel");
  await page.evaluate(()=>window.panel.setTab("connections"));await panel.locator(".panel-status-row").filter({hasText:"Sam Example"}).getByRole("button",{name:"Создать приглашение",exact:true}).click();
  const dialog=panel.getByRole("dialog");await expect(dialog).toContainText("Ожидаем действие в Telegram");
  await page.evaluate(()=>{window.fixture.enrollment.state="captured";window.fixture.enrollment.candidate={name:"Synthetic Account",username:"example_child",chat_id:123456789,user_id:123456789};});
  await dialog.locator("#refresh-enrollment").click();await expect(dialog).toContainText("Synthetic Account");await expect(dialog.locator("#confirm-enrollment")).toBeDisabled();
  await dialog.locator('[name="confirm_account"]').check();await page.screenshot({path:testInfo.outputPath("telegram-confirm-ru-mobile.png"),fullPage:true});await dialog.locator("#confirm-enrollment").click();await expect(dialog).toContainText("Привязка подтверждена");
  await dialog.getByRole("button",{name:"Закрыть",exact:true}).click();await panel.locator("#invite-group").click();await expect(dialog.locator('input[readonly]')).toHaveValue("/family_setup@example_test_bot SYNTHETIC-CODE");
  const confirms=await page.evaluate(()=>window.fixture.calls.filter(m=>m.type==="family_assistant/telegram_enrollment_confirm"));expect(confirms).toHaveLength(1);expect(confirms[0].candidate).toEqual({chat_id:123456789,user_id:123456789});
});

test("Russian member notifications preserve child subject and signed-in reminder recipient",async({page},testInfo)=>{
  await page.setViewportSize({width:390,height:844});await page.goto("/tests/fixtures/panel.html?lang=ru");await addMemberWorkspaceFixture(page);
  const panel=page.locator("family-assistant-panel");await panel.getByRole("button",{name:"Sam Example",exact:false}).click();
  await expect(panel.locator(".panel-member-readiness")).toContainText("Расписания подъёма выключены");
  await panel.locator(".panel-subtabs").getByRole("button",{name:"Уведомления",exact:true}).click();await panel.getByRole("button",{name:"🎒 Школа",exact:true}).click();
  const card=panel.locator("family-assistant-card");await expect(card.locator(".member-context")).toContainText("Настройки для: Sam Example");
  await expect(card.locator(".school-reminder-recipient")).toContainText("Morgan Example");await expect(card.locator("[data-school-reminder-member]")).toHaveCount(1);
  await expect(card.locator(".school-work,.school-section")).toHaveCount(0);await expect(card).not.toContainText("Alex Example");
  await card.getByRole("button",{name:"Включить для меня",exact:true}).click();await card.locator('input[type="checkbox"]').check();
  await page.screenshot({path:testInfo.outputPath("member-reminder-ru-mobile.png"),fullPage:true});await card.getByRole("button",{name:"Сохранить выбор",exact:true}).click();
  await expect(card.getByRole("button",{name:"Выключить для меня",exact:true})).toBeVisible();
  const write=await page.evaluate(()=>window.fixture.calls.find(item=>item.action==="school.preparation_reminder_access_set"));expect(write.payload).toEqual({member:"M3",member_revision:3,recipient_revision:1,subscription_revision:null,enabled:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("Ukrainian focused alarm creation targets selected child and digest cannot impersonate",async({page},testInfo)=>{
  await page.setViewportSize({width:390,height:844});await page.goto("/tests/fixtures/panel.html?lang=uk&theme=dark");await addMemberWorkspaceFixture(page);
  const panel=page.locator("family-assistant-panel");await panel.getByRole("button",{name:"Sam Example",exact:false}).click();await panel.locator(".panel-member-readiness").getByRole("button",{name:"Налаштувати: Будильники",exact:true}).click();
  const card=panel.locator("family-assistant-card");await expect(card.locator(".member-context")).toContainText("Налаштування для: Sam Example");await expect(card).not.toContainText("Alex wake-up");
  await card.locator(".toolbar button.primary").click();await expect(card.locator('[name="member"] option')).toHaveCount(1);await expect(card.locator('[name="member"]')).toHaveValue("M3");
  await card.locator('[name="name"]').fill("Sam synthetic wake-up");await card.locator(".alarm-editor form button[type=submit]").click();await card.locator('[name="confirmed"]').check();
  await expect(card.locator(".alarm-editor-review button:not(.primary)").first()).toHaveCSS("background-color","rgb(29, 48, 63)");
  await page.screenshot({path:testInfo.outputPath("member-alarm-uk-dark-mobile.png"),fullPage:true});await card.locator(".alarm-editor-review button.primary").click();
  await expect(card.locator(".alarm-editor")).toHaveCount(0);const write=await page.evaluate(()=>window.fixture.calls.find(item=>item.action==="alarms.save"));expect(write.payload.member).toBe("M3");
  await page.evaluate(()=>{window.panel._workspaceDirty=false;});await panel.getByRole("button",{name:"← Sam Example",exact:true}).click();await panel.locator(".panel-subtabs").getByRole("button",{name:"Сповіщення",exact:true}).click();await panel.getByRole("button",{name:"📨 Особисті дайджести",exact:true}).click();
  await expect(card).toContainText("лише їхній одержувач");await expect(card.locator(".digests,form")).toHaveCount(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
