import {test,expect} from "./control-audit.js";

const copy={
  en:{tab:"Connections",title:"Image generation (optional)",disabled:"Disabled",incomplete:"Configuration is incomplete",initialized:"Initialized — reachability not verified",configure:"Configure image providers"},
  ru:{tab:"Подключения",title:"Создание изображений (необязательно)",disabled:"Выключено",incomplete:"Настройка не завершена",initialized:"Инициализирован — доступность не проверена",configure:"Настроить провайдеров изображений"},
  uk:{tab:"Підключення",title:"Створення зображень (необов’язково)",disabled:"Вимкнено",incomplete:"Налаштування не завершено",initialized:"Ініціалізовано — доступність не перевірено",configure:"Налаштувати провайдерів зображень"},
};

for(const [lang,text]of Object.entries(copy))test(`optional image provider status and native settings link: ${lang}`,async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.goto(`/tests/fixtures/panel.html?lang=${lang}&theme=dark`);
  const panel=page.locator("family-assistant-panel");await expect(panel.locator("#panel-search")).toBeVisible();
  const before=await page.evaluate(()=>structuredClone(window.fixture.data.capabilities));
  await page.evaluate(async()=>{window.fixture.data.connections.image_generation={optional:true,enabled:false,configured:true,available:false,health:null};await window.panel.loadData();});
  await panel.locator(".mobile-bottom-nav").getByRole("button",{name:text.tab,exact:true}).click();
  const section=panel.locator('[data-connection="image_generation"]');await expect(section).toContainText(text.title);await expect(section).toContainText(text.disabled);
  await page.evaluate(async()=>{Object.assign(window.fixture.data.connections.image_generation,{enabled:true,configured:false});await window.panel.loadData();});
  await expect(section).toContainText(text.incomplete);
  await page.evaluate(async()=>{Object.assign(window.fixture.data.connections.image_generation,{configured:true,available:true});await window.panel.loadData();});
  await expect(section).toContainText(text.initialized);
  await page.evaluate(async()=>{Object.assign(window.fixture.data.connections.image_generation,{available:false,health:"provider_unreachable"});await window.panel.loadData();});
  const expectedError=await page.evaluate(()=>window.panel.errorText({code:"provider_unreachable"}));await expect(section).toContainText(expectedError);
  await expect(section.locator('[role="alert"]')).toHaveCount(0);await expect(section.getByRole("button")).toHaveCount(0);
  expect(await page.evaluate(()=>window.fixture.data.capabilities)).toEqual(before);
  expect(await page.evaluate(()=>window.fixture.calls.filter(call=>call.type==="family_assistant/execute"||call.type.includes("image")))).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.route("**/config/integrations/integration/family_assistant",route=>route.fulfill({status:200,contentType:"text/html",body:"<h1>Synthetic native integration settings destination</h1>"}));
  await section.getByRole("link",{name:text.configure,exact:true}).click();await expect(page).toHaveURL(/\/config\/integrations\/integration\/family_assistant$/);
  await expect(page.getByRole("heading",{name:"Synthetic native integration settings destination"})).toBeVisible();
});

test("missing privileged image projection reveals no provider controls",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en&role=child");const panel=page.locator("family-assistant-panel");await expect(panel.locator("#panel-search")).toBeVisible();
  await panel.locator(".nav-tabs-bar").getByRole("button",{name:/Connections/}).click();await expect(panel.locator('[data-connection="image_generation"]')).toHaveCount(0);
  expect(await page.evaluate(()=>window.fixture.calls.filter(call=>call.type==="family_assistant/execute"||call.type.includes("image")))).toEqual([]);
});
