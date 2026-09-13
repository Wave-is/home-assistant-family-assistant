import {test,expect} from "./control-audit.js";
import {PRICE_WATCH_COPY} from "../../custom_components/family_assistant/frontend/price-watch-view.js";
import {PANEL_COPY} from "../../custom_components/family_assistant/frontend/panel-copy.js";

async function prepared(page,{language="en",role="owner"}={}){
  await page.goto(`/tests/fixtures/panel.html?lang=${language}&role=${role}`);
  await expect(page.locator("family-assistant-panel")).toBeVisible();
  await page.waitForFunction(()=>window.panel?._data?.view);
  await page.evaluate(async()=>{
    const data=window.fixture.data;data.view.settings.modules.push("price_watch");
    data.view.price_watches=[{id:"PW1",revision:7,name:"<img src=x onerror=alert(1)>",url:"https://merchant.example/item",policy_status:"review_required",history:[{price_text:"5",currency:"USD"}]}];
    const original=window.panel._hass.callWS;
    window.fixture.priceWrites=[];window.fixture.priceFail=false;
    window.panel.hass={...window.panel._hass,callWS:async(message)=>{
      if(message.type==="family_assistant/execute"&&message.action==="price_watch.edit"){
        window.fixture.priceWrites.push(structuredClone(message));
        if(window.fixture.priceFail){window.fixture.priceFail=false;throw {code:"connection_lost"};}
        const watch=data.view.price_watches[0];if(watch.revision!==message.payload.revision||message.payload.actor_revision!==data.view.members[0].revision)throw {code:"conflict"};
        Object.assign(watch,{url:message.payload.url,revision:watch.revision+1,policy_generation:1,policy_status:"ready"});return structuredClone(watch);
      }
      return original(message);
    }};
    await window.panel.loadData();
  });
  // Navigate the real panel controls, not a synthetic standalone review component.
  const panel=page.locator("family-assistant-panel");
  const labels={en:{modules:"Modules",title:"Price history",configure:"Configure"},ru:{modules:"Модули",title:"История цен",configure:"Настроить"},uk:{modules:"Модулі",title:"Історія цін",configure:"Налаштувати"}}[language];
  await panel.getByRole("navigation").getByRole("button",{name:new RegExp(`${PANEL_COPY[language].modules}$`)}).click();
  const card=panel.locator(".panel-module-card").filter({hasText:labels.title});
  await card.getByRole("button",{name:labels.configure,exact:true}).click();
  return panel.locator("[data-price-watch-review]");
}

for(const language of ["en","ru","uk"])test(`mobile ${language}: saved watch needs explicit URL consent; failure retries exact payload`,async({page})=>{
  await page.setViewportSize({width:390,height:844});const box=await prepared(page,{language}),copy=PRICE_WATCH_COPY[language];
  await expect(box).toContainText(copy.review_required);await expect(box).toContainText("512");await expect(box.locator("img,script,a")).toHaveCount(0);
  const consent=box.getByRole("checkbox"),url=box.getByLabel(copy.url,{exact:true});await expect(consent).not.toBeChecked();
  await box.getByRole("button",{name:copy.save,exact:true}).click();expect(await page.evaluate(()=>window.fixture.priceWrites.length)).toBe(0);
  await url.fill("https://merchant.example/reviewed");await consent.check();await page.evaluate(()=>{window.fixture.priceFail=true;});
  await box.getByRole("button",{name:copy.save,exact:true}).click();await expect(box.getByRole("button",{name:copy.retry,exact:true})).toBeVisible();await expect(url).toBeDisabled();await expect(consent).toBeDisabled();
  await box.getByRole("button",{name:copy.retry,exact:true}).click();await expect(box).toContainText(copy.ready);
  const writes=await page.evaluate(()=>window.fixture.priceWrites);expect(writes).toHaveLength(2);expect(writes[0]).toEqual(writes[1]);expect(writes[0].payload).toEqual({id:"PW1",revision:7,actor_revision:1,url:"https://merchant.example/reviewed"});
  expect(await page.evaluate(()=>window.fixture.data.view.price_watches[0].history)).toHaveLength(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test("child has shared status but no reapproval; parent can explicitly reapprove unchanged URL",async({page})=>{
  let box=await prepared(page,{role:"child"});await expect(box.locator("form")).toHaveCount(0);expect(await page.evaluate(()=>window.fixture.priceWrites.length)).toBe(0);
  box=await prepared(page,{role:"parent"});await box.getByRole("checkbox").check();await box.getByRole("button",{name:PRICE_WATCH_COPY.en.save,exact:true}).click();await expect(box).toContainText(PRICE_WATCH_COPY.en.ready);
  expect((await page.evaluate(()=>window.fixture.priceWrites))[0].payload.url).toBe("https://merchant.example/item");
});

test("unsupported credential URL is rejected locally and disabled module has no approval form",async({page})=>{
  const box=await prepared(page),copy=PRICE_WATCH_COPY.en;
  await box.getByLabel(copy.url,{exact:true}).fill("https://user:synthetic@merchant.example/item");await box.getByRole("checkbox").check();await box.getByRole("button",{name:copy.save,exact:true}).click();await expect(box).toContainText(copy.invalid);expect(await page.evaluate(()=>window.fixture.priceWrites.length)).toBe(0);
  await page.evaluate(()=>{window.panel._data.view.settings.modules=[];window.panel.render();});await expect(box.locator("form")).toHaveCount(0);
});
