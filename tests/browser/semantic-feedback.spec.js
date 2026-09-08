import {test,expect} from "@playwright/test";

test("mobile private correction remains a reviewed note, with retry and explicit purge",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/conversation.html?lang=ru&role=child&feedback");
  const card=page.locator("family-conversation-card");
  await card.getByText("Отклонить и описать ошибку",{exact:true}).click();
  const form=card.locator("details.semantic-feedback form");
  await form.getByLabel("Что вы имели в виду (без выполнения)",{exact:true}).fill("Нужны яблоки, а не молоко");
  await form.getByLabel("Отклонить это предложение и сохранить личную заметку",{exact:true}).check();
  await page.evaluate(()=>window.failure="note-before");
  await form.getByRole("button",{name:"Отклонить и сохранить заметку",exact:true}).click();
  await expect(card.locator("textarea[name=expected]")).toHaveValue("Нужны яблоки, а не молоко");
  await expect(card.getByRole("button",{name:"Отклонить и сохранить заметку",exact:true})).toBeEnabled();
  await card.getByRole("button",{name:"Отклонить и сохранить заметку",exact:true}).click();
  const journal=card.locator(".semantic-feedback-journal");
  await expect(journal).toContainText("Нужны яблоки, а не молоко");
  await expect(journal).toContainText("Исходный запрос не указан");
  const calls=await page.evaluate(()=>window.executeCalls);
  expect(calls).toHaveLength(2);expect(calls[0]).toEqual(calls[1]);
  expect(await page.evaluate(()=>window.chatCalls)).toHaveLength(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/semantic-feedback-ru.png",fullPage:true});
  await journal.getByRole("button",{name:"Удалить эту заметку",exact:true}).click();
  expect(await page.evaluate(()=>window.executeCalls.length)).toBe(2);
  await journal.getByLabel("Удалить только заметку, сохранив исходное предложение и его историю",{exact:true}).check();
  await journal.getByRole("button",{name:"Удалить эту заметку",exact:true}).click();
  await expect(journal).toContainText("Личных заметок пока нет");
});

for(const [language,label,expected] of [["en","Reject and describe the problem","What you meant (not executed)"],["uk","Відхилити й описати помилку","Що ви мали на увазі (без виконання)"]]){
  test(`private correction form ${language} drops revoked drafts`,async({page})=>{
    await page.goto(`/tests/fixtures/conversation.html?lang=${language}&role=parent&feedback`);
    const card=page.locator("family-conversation-card");await card.getByText(label,{exact:true}).click();
    await card.getByLabel(expected,{exact:true}).fill("PRIVATE_DRAFT_CANARY");
    await page.evaluate(async()=>{window.fixture.members.find(m=>m.id===window.fixture.actor).revision++;await window.card.refresh();});
    await expect(card.locator("textarea[name=expected]")).toHaveValue("");
    expect(await page.evaluate(()=>window.executeCalls.length)).toBe(0);
  });
}
