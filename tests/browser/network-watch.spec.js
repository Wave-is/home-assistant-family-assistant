import {test,expect} from "@playwright/test";
import {NETWORK_WATCH_COPY as COPY} from "../../custom_components/family_assistant/frontend/network-watch-copy.js";
for(const language of ["ru","uk","en"])test(`${language} mobile private discovery subscription`,async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.goto(`/tests/fixtures/network-watch.html?lang=${language}`);
  const section=page.locator("family-network-card .network-watch");
  await section.getByRole("button",{name:COPY[language].enable,exact:true}).click();
  const form=section.locator("form");await form.locator('[name="min_interval_minutes"]').fill("15");
  const submit=form.getByRole("button",{name:COPY[language].save,exact:true});await expect(submit).toBeDisabled();
  await form.locator('[name="confirmed"]').check();
  if(language==="ru")await section.screenshot({path:"test-results/network-watch-review-ru.png"});
  await submit.click();await expect(form).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toHaveLength(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
