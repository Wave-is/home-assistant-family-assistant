import {test,expect} from "@playwright/test";

test("network evidence is readable on mobile and refresh is read-only",async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto("/tests/fixtures/dashboard.html?view=mikrotik&lang=ru");
 await expect(page.getByText("Example phone",{exact:true})).toBeVisible();
 await page.getByText("Совпадения в Home Assistant",{exact:true}).click();
 await expect(page.getByText(/Точное совпадение MAC/)).toBeVisible();
 await page.getByRole("button",{name:"Перечитать роутер",exact:true}).click();
 expect((await page.evaluate(()=>window.calls))[0].type).toBe("family_assistant/network_refresh");
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:"test-results/network-mobile-ru.png",fullPage:true});
});

test("child does not see private network inventory",async({page})=>{
 await page.goto("/tests/fixtures/dashboard.html?view=mikrotik&role=child");
 await expect(page.getByText("Example phone",{exact:true})).toHaveCount(0);
 await expect(page.getByRole("button",{name:"Read router again",exact:true})).toHaveCount(0);
});

test("model interpretation stays unexecuted until the user's confirmation",async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto("/tests/fixtures/dashboard.html?view=today&lang=ru&proposal=1");
 await expect(page.getByRole("heading",{name:"Проверьте, правильно ли я понял"})).toBeVisible();
 expect(await page.evaluate(()=>window.calls.length)).toBe(0);
 await page.screenshot({path:"test-results/proposal-mobile-ru.png",fullPage:true});
 await page.getByRole("button",{name:"Выполнить план",exact:true}).click();
 expect((await page.evaluate(()=>window.calls))[0].action).toBe("conversation.confirm");
 expect((await page.evaluate(()=>window.calls))[0].payload).toEqual({id:"Psynthetic"});
 await expect(page.getByRole("button",{name:"Выполнить план",exact:true})).toHaveCount(0);
});

test("conversation card sends an authenticated request and teaches an exact phrase",async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto("/tests/fixtures/dashboard.html?view=conversation&lang=ru");
 await page.getByLabel("Сообщение",{exact:true}).fill("/ping");
 await page.getByRole("button",{name:"Отправить",exact:true}).click();
 await expect(page.getByText("Я тут. Списки и задачи работают без модели.")).toBeVisible();
 expect((await page.evaluate(()=>window.calls))[0].type).toBe("family_assistant/chat");
 await page.getByText("Обучить фразе",{exact:true}).click();
 await page.getByLabel("Непонятная фраза",{exact:true}).fill("покажи мой баланс");
 await page.getByLabel("Поддерживаемая повторяемая команда",{exact:true}).fill("/stats");
 await page.getByRole("button",{name:"Сохранить",exact:true}).click();
 expect((await page.evaluate(()=>window.calls))[1].action).toBe("conversation.learn");
 await page.getByText("Обучить фразе",{exact:true}).click();
 await expect(page.getByRole("button",{name:"Отключить фразу",exact:true})).toBeVisible();
 await page.screenshot({path:"test-results/conversation-mobile-ru.png",fullPage:true});
});

test("parent adds an item using the Russian mobile card",async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto("/tests/fixtures/dashboard.html?lang=ru&view=shopping");
 await expect(page.getByText("Яблоки",{exact:true})).toBeVisible();
 await page.getByRole("button",{name:"Добавить",exact:true}).click();
 await page.getByLabel("Название",{exact:true}).fill("Молоко");
 await page.getByLabel("Количество",{exact:true}).fill("2");
 await page.getByLabel("Единица",{exact:true}).fill("л");
 await page.getByRole("button",{name:"Сохранить",exact:true}).click();
 await expect(page.getByText("Молоко",{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>window.calls[0].payload)).toEqual({name:"Молоко",quantity:2,unit:"л"});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:"test-results/shopping-mobile-ru.png",fullPage:true});
});
test("a failed action remains visible after a successful refresh",async({page})=>{
 await page.goto("/tests/fixtures/dashboard.html?view=shopping");
 await page.evaluate(()=>window.failCommand=true);
 await page.getByRole("button",{name:"Bought",exact:true}).click();
 await expect(page.getByRole("alert")).toHaveText("Could not save the change. It was not applied.");
});
for(const lang of ["en","ru","uk"]){
 test(`today card in ${lang}, dark mode`,async({page})=>{
   await page.goto(`/tests/fixtures/dashboard.html?view=today&lang=${lang}&dark=1`);
   await expect(page.locator("family-assistant-card h2")).toBeVisible();
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await page.screenshot({path:`test-results/today-${lang}-dark.png`,fullPage:true});
 });
}
test("child can answer only their fresh wake-up check",async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto("/tests/fixtures/dashboard.html?view=alarms&lang=uk&role=child&ringing=1");
 await expect(page.getByRole("heading",{name:"3 + 4"})).toBeVisible();
 await expect(page.getByRole("button",{name:"Додати",exact:true})).toHaveCount(0);
 await expect(page.getByRole("button",{name:"Зупинити перевірку підйому"})).toHaveCount(0);
 await page.getByRole("button",{name:"7",exact:true}).click();
 const commands=await page.evaluate(()=>window.calls);
 expect(commands[0].action).toBe("alarms.answer");
 expect(commands[0].payload).toEqual({id:"W000001",nonce:"synthetic-nonce",answer:7});
 await page.screenshot({path:"test-results/alarm-child-uk.png",fullPage:true});
});

test("physical test has an explicit second step",async({page})=>{
 await page.goto("/tests/fixtures/dashboard.html?view=alarms&lang=en");
 await page.getByRole("button",{name:"Test without penalties",exact:true}).click();
 expect(await page.evaluate(()=>window.calls.length)).toBe(0);
 await expect(page.getByText("This test starts the selected siren in strict mode. No penalty will be issued.")).toBeVisible();
 await page.getByRole("button",{name:"Start test",exact:true}).click();
 expect((await page.evaluate(()=>window.calls))[0].action).toBe("alarms.test");
});
test("notification retry requires consent and a reason",async({page})=>{
 await page.goto("/tests/fixtures/dashboard.html?view=health&lang=en");
 await page.getByRole("button",{name:"Review and resend",exact:true}).click();
 await page.getByLabel("Reason",{exact:true}).fill("Checked the private chat");
 await page.getByRole("button",{name:"Save",exact:true}).click();
 expect(await page.evaluate(()=>window.calls.length)).toBe(0);
 await page.getByRole("checkbox").check();
 await page.getByRole("button",{name:"Save",exact:true}).click();
 const command=(await page.evaluate(()=>window.calls))[0];
 expect(command.action).toBe("notifications.retry");
 expect(command.payload.confirmed).toBe(true);
});

test("parent creates a rotating duty using the Russian mobile form",async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto("/tests/fixtures/dashboard.html?view=tasks&lang=ru");
 await page.getByRole("button",{name:"Добавить регулярную обязанность"}).click();
 await page.getByLabel("Что нужно сделать?",{exact:true}).fill("Проверить растения");
 await page.getByRole("group",{name:"Кому?",exact:true}).getByLabel("Ребёнок 1",{exact:true}).check();
 await page.getByLabel("По очереди",{exact:true}).check();
 await page.getByRole("combobox",{name:"Повторять",exact:true}).selectOption("weekly");
 await page.getByLabel("Дата начала",{exact:true}).fill("2026-09-07");
 await page.screenshot({path:"test-results/recurring-form-mobile-ru.png",fullPage:true});
 await page.getByRole("button",{name:"Сохранить",exact:true}).click();
 const command=(await page.evaluate(()=>window.calls))[0];
 expect(command.action).toBe("tasks.series_save");
 expect(command.payload.assignees).toEqual(["child"]);expect(command.payload.rotation).toBe(true);
 expect(command.payload.rule.weekdays).toEqual([0,1,2,3,4]);expect(command.payload.penalty).toBe(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:"test-results/recurring-mobile-ru.png",fullPage:true});
});

test("child cannot create a recurring family duty",async({page})=>{
 await page.goto("/tests/fixtures/dashboard.html?view=tasks&lang=en&role=child");
 await expect(page.getByRole("button",{name:"Add recurring duty"})).toHaveCount(0);
});
