import {test,expect} from "./control-audit.js";
import {SHADOW_COPY} from "../../custom_components/family_assistant/frontend/shadow-view.js";

for(const lang of ["en","ru","uk"])test(`owner shadow review is mobile read-only ${lang}`,async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/tests/fixtures/maintenance.html?lang=${lang}`);
  await page.locator("family-maintenance-card").waitFor();
  await page.evaluate(()=>{
    const card=window.card;
    card._data={...card._data,role:"owner",read_only:"migration_shadow_read_only",settings:{...card._data.settings,modules:[]},tasks:[{id:"T000019",title:"<img src=x> Synthetic retained chore"}]};
    card.render();
  });
  const section=page.locator("family-maintenance-card .migration-shadow");
  await expect(section.getByRole("heading",{name:SHADOW_COPY[lang].title})).toBeVisible();
  await expect(section.getByRole("status")).toBeVisible();
  await expect(section.locator("button,input,form,img")).toHaveCount(0);
  await section.locator("summary").first().click();
  await expect(section.locator("li").first()).toContainText("<img src=x>");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`test-results/shadow-${lang}.png`,fullPage:true});
});
