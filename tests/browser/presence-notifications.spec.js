import {test,expect} from "@playwright/test";
import {PRESENCE_NOTIFICATIONS_COPY as COPY} from "../../custom_components/family_assistant/frontend/presence-notifications-copy.js";
for(const language of ["ru","uk","en"])test(`${language} mobile reviewed return-home reminders`,async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/tests/fixtures/presence-notifications.html?lang=${language}`);
  const section=page.locator("family-presence-card .presence-notifications");
  const child=section.locator('[data-notification-member="child"]');
  await child.getByRole("button",{name:COPY[language].enable,exact:true}).click();
  const form=section.locator("form");await expect(form).toContainText("Example child");
  await form.getByLabel(COPY[language].max_wait_input,{exact:false}).fill("45");
  const submit=form.getByRole("button",{name:COPY[language].save,exact:true});
  await expect(submit).toBeDisabled();
  await form.locator('input[name="confirmed"]').check();
  if(language==="ru")await page.screenshot({path:"test-results/presence-notifications-review-ru.png",fullPage:true});
  await submit.click();await expect(form).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls);expect(calls).toHaveLength(1);
  expect(calls[0].payload).toEqual({member:"child",member_revision:4,binding_revision:7,preference_revision:null,enabled:true,max_wait_minutes:45,actor_member_revision:2});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
