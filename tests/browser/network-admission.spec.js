import {test,expect} from "./control-audit.js";
import {NETWORK_ADMISSION_COPY as COPY} from "../../custom_components/family_assistant/frontend/network-admission-copy.js";
for(const language of ["ru","uk","en"])test(`${language} mobile local device approval`,async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/tests/fixtures/network-admission.html?lang=${language}`);
  const section=page.locator("family-network-card .network-admission");
  await section.getByRole("button",{name:COPY[language].approve_button,exact:true}).click();
  await section.locator('input[type="text"]').fill("Example laptop");
  await section.getByRole("button",{name:COPY[language].preview_button,exact:true}).click();
  const apply=section.getByRole("button",{name:COPY[language].apply_button,exact:true});
  await expect(apply).toBeDisabled();await section.locator('input[type="checkbox"]').check();
  if(language==="ru")await page.screenshot({path:"test-results/network-admission-review-ru.png",fullPage:true});
  await apply.click();await expect(section.getByRole("button",{name:COPY[language].rename_button,exact:true})).toBeVisible();
  expect(await page.evaluate(()=>window.calls.map(item=>item.action))).toEqual(["mikrotik.admission_preview","mikrotik.admission_apply"]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await expect(section.locator("img")).toHaveCount(0);
});
