import {test,expect} from "./control-audit.js";

test("RU mobile owner saves a configured threshold without changing the report schedule",async({page},testInfo)=>{
  const errors=[];page.on("pageerror",error=>errors.push(error.message));
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=court&lang=ru&courtedit=1");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Настроить отчёты",exact:true}).click();
  await card.getByRole("button",{name:"Добавить порог",exact:true}).click();
  await card.getByLabel("Название правила",{exact:true}).fill("Пример семейного правила");
  await card.getByLabel("Условие",{exact:true}).selectOption("at_least");
  await card.getByLabel("Порог в баллах (от -10000 до 10000)",{exact:true}).fill("8");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(await card.locator("form").first().evaluate(form=>[...form.elements].filter(element=>element.willValidate&&!element.validity.valid).map(element=>({name:element.name,message:element.validationMessage})))).toEqual([]);
  await card.getByRole("button",{name:"Сохранить",exact:true}).click();
  expect(errors).toEqual([]);
  await expect.poll(()=>page.evaluate(()=>window.calls.length)).toBe(1);
  const calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].action).toBe("court.configure");
  expect(calls[0].payload.thresholds).toEqual([{id:"rule-1",label:"Пример семейного правила",direction:"at_least",points:8,members:[]}]);
  await card.getByRole("button",{name:"Настроить отчёты",exact:true}).click();
  await page.screenshot({path:testInfo.outputPath("court-threshold-mobile-ru.png"),fullPage:true});
});
