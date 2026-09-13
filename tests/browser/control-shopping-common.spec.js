import {test,expect} from "./control-audit.js";
import {SHOPPING_ITEM_COPY as ITEMS} from "../../custom_components/family_assistant/frontend/shopping-items.js";

test("completed shopping purchase keeps its uncertain-result retry visible in history",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:ITEMS.en.action_partial_purchase,exact:true}).click();
  await card.locator('form [name="quantity"]').fill("2");
  await page.evaluate(()=>window.commitThenLose=true);
  await card.getByRole("button",{name:ITEMS.en.action_submit,exact:true}).click();
  await expect(card.getByRole("alert").filter({visible:true})).toBeVisible();
  expect(await page.evaluate(()=>window.fixture.shopping[0].status)).toBe("purchased");
  const archive=card.locator(".shopping-archive");
  await expect(archive.getByRole("button",{name:ITEMS.en.action_retry,exact:true})).toBeVisible();
  await archive.getByRole("button",{name:ITEMS.en.action_retry,exact:true}).click();
  await expect(archive.locator("form")).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(2);expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].action).toBe("shopping.purchase");
  expect(calls[0].payload).toMatchObject({id:"S000001",revision:1,quantity:2});
  expect(await page.evaluate(()=>window.fixture.shopping[0])).toMatchObject({purchased:3,revision:2,status:"purchased"});
});

test("remaining shopping editor buttons preserve Back draft and discard without commands",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card"),editor=card.locator(".shopping-editor");
  await card.getByRole("button",{name:"Add shopping item",exact:true}).click();
  await editor.getByLabel("Name",{exact:true}).fill("Synthetic draft only");
  await editor.locator("form").evaluate(form=>form.requestSubmit());
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await expect(editor.locator("form")).toBeVisible();
  await editor.getByRole("button",{name:"Review",exact:true}).click();
  await editor.getByRole("button",{name:"Back",exact:true}).click();
  await expect(editor.getByLabel("Name",{exact:true})).toHaveValue("Synthetic draft only");
  await editor.getByRole("button",{name:"Review",exact:true}).click();
  await editor.getByRole("button",{name:"Cancel",exact:true}).click();
  await expect(editor).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await card.getByRole("button",{name:"Add shopping item",exact:true}).click();
  await expect(editor.getByLabel("Name",{exact:true})).toHaveValue("");
  await editor.getByRole("button",{name:"Cancel",exact:true}).click();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
});

test("shopping explicit new edit after failed save is not a retry or hidden mutation",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card"),editor=card.locator(".shopping-editor");
  const before=await page.evaluate(()=>structuredClone(window.fixture.shopping));
  await card.getByRole("button",{name:"Add shopping item",exact:true}).click();
  await editor.getByLabel("Name",{exact:true}).fill("Synthetic failed draft");
  await editor.getByRole("button",{name:"Review",exact:true}).click();
  await page.evaluate(()=>window.failCommand=true);
  await editor.getByRole("button",{name:"Add to shopping list",exact:true}).click();
  await expect(card.getByRole("alert")).toBeVisible();
  await editor.getByRole("button",{name:"Start a new edit",exact:true}).click();
  await expect(editor.getByLabel("Name",{exact:true})).toBeEnabled();
  await expect(editor.getByLabel("Name",{exact:true})).toHaveValue("");
  expect(await page.evaluate(()=>window.calls)).toHaveLength(1);
  expect(await page.evaluate(()=>window.fixture.shopping)).toEqual(before);
  await editor.getByRole("button",{name:"Cancel",exact:true}).click();
  expect(await page.evaluate(()=>window.calls)).toHaveLength(1);
});

test("shopping recurrence Cancel clears only its unsaved form",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Add recurring item",exact:true}).click();
  const form=card.locator("form");
  await form.locator('[name="name"]').fill("Synthetic unsaved recurrence");
  await form.getByRole("button",{name:"Cancel",exact:true}).click();
  await expect(form).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await card.getByRole("button",{name:"Add recurring item",exact:true}).click();
  await expect(form.locator('[name="name"]')).toHaveValue("");
});

test("barcode Stop ends synthetic tracks and rejects late detection without saving",async({page})=>{
  await page.addInitScript(()=>{
    window.stopCalls=0;
    const canvas=document.createElement("canvas");canvas.width=canvas.height=16;
    canvas.getContext("2d").fillRect(0,0,16,16);
    const stream=canvas.captureStream(5);
    for(const track of stream.getTracks()){
      const original=track.stop.bind(track);track.stop=()=>{window.stopCalls++;original();};
    }
    Object.defineProperty(navigator,"mediaDevices",{configurable:true,value:{getUserMedia:async()=>stream}});
    window.BarcodeDetector=class {
      static async getSupportedFormats(){return ["ean_13"];}
      async detect(){return new Promise(resolve=>{window.finishDetection=()=>resolve([{format:"ean_13",rawValue:"4006381333931"}]);});}
    };
  });
  await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Add shopping item",exact:true}).click();
  await card.getByRole("button",{name:"Scan barcode",exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>typeof window.finishDetection)).toBe("function");
  await card.getByRole("button",{name:"Stop camera",exact:true}).click();
  await page.evaluate(()=>window.finishDetection());
  await expect(card.getByRole("button",{name:"Stop camera",exact:true})).toBeHidden();
  expect(await page.evaluate(()=>window.stopCalls)).toBe(1);
  await expect(card.getByLabel("Barcode (optional GTIN)",{exact:true})).toHaveValue("");
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
});

test("calendar editor and native-export consent Cancel do not persist drafts",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=calendar");
  const card=page.locator("family-assistant-card");
  const before=await page.evaluate(()=>structuredClone(window.calendarFixture.calendar));
  await card.getByRole("button",{name:"New event",exact:true}).click();
  await card.getByLabel("Title",{exact:true}).fill("Synthetic abandoned event");
  await card.locator("form").getByRole("button",{name:"Cancel",exact:true}).click();
  await expect(card.getByLabel("Title",{exact:true})).toHaveCount(0);
  await card.getByRole("button",{name:"New event",exact:true}).click();
  await card.locator(".toolbar").getByRole("button",{name:"Cancel",exact:true}).click();
  await expect(card.getByLabel("Title",{exact:true})).toHaveCount(0);
  await card.getByRole("button",{name:"Edit",exact:true}).first().click();
  await expect(card.locator('[name="confirm_public_visibility"]')).toBeVisible();
  await card.locator("form").getByRole("button",{name:"Cancel",exact:true}).click();
  await expect(card.locator('[name="confirm_public_visibility"]')).toHaveCount(0);
  expect(await page.evaluate(()=>window.calendarFixture.calendar)).toEqual(before);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
});

test("condition row Remove keeps another condition and never edits template before Save",async({page})=>{
  await page.goto("/tests/fixtures/routines.html?lang=ru");
  const card=page.locator("family-routines-card");
  await card.getByRole("button",{name:"Изменить",exact:true}).click();
  const first=card.locator('[data-routine-step-index="0"]');
  await first.getByText("Расширенное условие пропуска",{exact:true}).click();
  const scope=card.locator('[data-condition-scope="step-0-skip"]');
  await scope.locator('[data-condition-field="kind"][data-condition-path=""]').selectOption("all");
  await scope.getByRole("button",{name:"Добавить условие",exact:true}).click();
  await expect(scope.getByRole("button",{name:"Удалить",exact:true})).toHaveCount(2);
  await scope.getByRole("button",{name:"Удалить",exact:true}).last().click();
  await expect(scope.getByRole("button",{name:"Удалить",exact:true})).toHaveCount(1);
  await expect(scope.getByRole("button",{name:"Удалить",exact:true})).toBeDisabled();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
});

test("developer preview Close discards only displayed report and does not download",async({page})=>{
  await page.goto("/tests/fixtures/health-view.html?lang=en&role=owner&diagnostics");
  await page.evaluate(()=>window.ready);
  const card=page.locator("family-health-card");let downloads=0;page.on("download",()=>downloads++);
  await card.getByRole("button",{name:"Review technical report",exact:true}).click();
  await expect(card.locator(".developer-json")).toBeVisible();
  const before=await page.evaluate(()=>structuredClone(window.calls));
  await card.getByRole("button",{name:"Close preview",exact:true}).click();
  await expect(card.locator(".developer-json")).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toEqual(before);expect(downloads).toBe(0);
});
