import {test,expect} from "@playwright/test";

const labels={
  en:{add:"Add shopping item",name:"Name",code:"Barcode (optional GTIN)",review:"Review",save:"Add to shopping list"},
  ru:{add:"Добавить покупку",name:"Название",code:"Штрихкод (необязательный GTIN)",review:"Проверить",save:"Добавить в список покупок"},
  uk:{add:"Додати покупку",name:"Назва",code:"Штрихкод (необов’язковий GTIN)",review:"Перевірити",save:"Додати до списку покупок"}
};
for(const lang of ["en","ru","uk"])test(`${lang}: mobile manual barcode is reviewed and exact-retried`,async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/tests/fixtures/dashboard.html?view=shopping&lang=${lang}`);
  const card=page.locator("family-assistant-card"),copy=labels[lang];
  await card.getByRole("button",{name:copy.add,exact:true}).click();
  const editor=card.locator(".shopping-editor");
  await editor.getByLabel(copy.name,{exact:true}).fill("Fictional cereal");
  await editor.getByLabel(copy.code,{exact:true}).fill("4006381333931");
  await editor.getByRole("button",{name:copy.review,exact:true}).click();
  await expect(editor).toContainText("04006381333931");
  expect(await page.evaluate(()=>window.calls)).toHaveLength(0);
  await page.screenshot({path:`test-results/shopping-barcode-${lang}.png`,fullPage:true});
  await page.evaluate(()=>{window.commitThenLose=true;});
  await editor.getByRole("button",{name:copy.save,exact:true}).click();
  await expect(card.getByRole("alert")).toBeVisible();
  const first=await page.evaluate(()=>structuredClone(window.calls[0]));
  expect(first.payload.barcode).toBe("04006381333931");
  await editor.getByRole("button",{name:lang==="en"?"Retry":lang==="ru"?"Повторить":"Повторити",exact:true}).click();
  await expect(editor).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls[1])).toEqual(first);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

async function syntheticCamera(page,{waitPermission=false,waitDetection=false}={}){
  await page.addInitScript(({waitPermission,waitDetection})=>{
    window.cameraRequests=0;window.cameraStops=0;window.cameraDetections=0;
    const canvas=document.createElement("canvas");canvas.width=320;canvas.height=240;
    // A synthetic canvas stream exercises actual video playback without a camera.
    const context=canvas.getContext("2d");context.fillRect(0,0,320,240);
    const stream=canvas.captureStream(5);
    for(const track of stream.getTracks()){
      const stop=track.stop.bind(track);track.stop=()=>{window.cameraStops++;stop();};
    }
    Object.defineProperty(navigator,"mediaDevices",{configurable:true,value:{getUserMedia:()=>{
      window.cameraRequests++;
      return waitPermission?new Promise(resolve=>{window.resolveCamera=()=>resolve(stream);}):Promise.resolve(stream);
    }}});
    window.BarcodeDetector=class {
      static async getSupportedFormats(){return ["ean_13","qr_code"];}
      async detect(video){
        if(!(video instanceof HTMLVideoElement)||video.videoWidth===0)throw Error("missing video");
        window.cameraDetections++;
        const result=[{format:"ean_13",rawValue:"4006381333931"}];
        return waitDetection?new Promise(resolve=>{window.resolveDetection=()=>resolve(result);}):result;
      }
    };
  },{waitPermission,waitDetection});
}

test("synthetic local video scan only fills a reviewed draft and stops its tracks",async({page})=>{
  await syntheticCamera(page);await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Add shopping item",exact:true}).click();
  expect(await page.evaluate(()=>window.cameraRequests)).toBe(0);
  await card.getByRole("button",{name:"Scan barcode",exact:true}).click();
  await expect(card.getByLabel(labels.en.code,{exact:true})).toHaveValue("04006381333931");
  await expect.poll(()=>page.evaluate(()=>window.cameraStops)).toBe(1);
  expect(await page.evaluate(()=>window.calls)).toHaveLength(0);
  await expect(card.getByLabel("Name",{exact:true})).toHaveValue("");
});

for(const revoke of ["cancel","identity","unmount"])test(`late permission cannot outlive ${revoke}`,async({page})=>{
  await syntheticCamera(page,{waitPermission:true});await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Add shopping item",exact:true}).click();
  await card.getByRole("button",{name:"Scan barcode",exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.cameraRequests)).toBe(1);
  if(revoke==="cancel")await card.locator(".shopping-editor").getByRole("button",{name:"Cancel",exact:true}).click();
  if(revoke==="identity")await page.evaluate(()=>{window.card.hass={...window.card._hass,user:{id:"another-user"}};});
  if(revoke==="unmount")await page.evaluate(()=>window.card.remove());
  await page.evaluate(()=>window.resolveCamera());
  await expect.poll(()=>page.evaluate(()=>window.cameraStops)).toBe(1);
  expect(await page.evaluate(()=>window.calls)).toHaveLength(0);
});

test("revoked member cannot consume an outstanding detection",async({page})=>{
  await syntheticCamera(page,{waitDetection:true});await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Add shopping item",exact:true}).click();
  await card.getByRole("button",{name:"Scan barcode",exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.cameraDetections)).toBe(1);
  await page.evaluate(async()=>{window.fixture.members[0].revision++;await window.card.refresh();window.resolveDetection();});
  await expect(card.locator(".shopping-editor")).toHaveCount(0);
  expect(await page.evaluate(()=>window.cameraStops)).toBe(1);
  expect(await page.evaluate(()=>window.calls)).toHaveLength(0);
});

test("manual barcode entry cancels pending scan; scanner Enter never submits a purchase",async({page})=>{
  await syntheticCamera(page,{waitDetection:true});await page.goto("/tests/fixtures/dashboard.html?view=shopping");
  const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Add shopping item",exact:true}).click();
  await card.getByRole("button",{name:"Scan barcode",exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.cameraDetections)).toBe(1);
  const field=card.getByLabel(labels.en.code,{exact:true});
  await field.fill("96385074");await field.press("Enter");
  await page.evaluate(()=>window.resolveDetection());
  await expect(field).toHaveValue("96385074");
  expect(await page.evaluate(()=>window.cameraStops)).toBe(1);
  expect(await page.evaluate(()=>window.calls)).toHaveLength(0);
});
