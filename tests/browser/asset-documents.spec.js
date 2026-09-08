import {test,expect} from "@playwright/test";
import {DOCUMENT_COPY} from "../../custom_components/family_assistant/frontend/asset-document-copy.js";

async function setup(page,lang){
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/tests/fixtures/maintenance.html?lang=${lang}`);
  await page.locator("family-maintenance-card .asset-documents").waitFor();
  await page.evaluate(async()=>{
    const card=window.card,state=window.fixture,original=card._hass;
    state.members[0].role="owner";state.role="owner";state.maintenance.documents=[];
    const receipts=new Map();window.documentCalls=[];window.documentHttp=[];
    card.hass={...original,user:{id:"synthetic-owner"},callWS:async m=>{
      if(m.type==="family_assistant/view")return window.project();
      if(!["media.reserve","maintenance.document_attach","maintenance.document_purge"].includes(m.action))return original.callWS(m);
      window.documentCalls.push(structuredClone(m));
      if(receipts.has(m.operation_id))return structuredClone(receipts.get(m.operation_id));
      let result;
      if(m.action==="media.reserve")result={id:"Mdoc",revision:1,status:"reserved"};
      if(m.action==="maintenance.document_attach"){
        const p=m.payload;
        if(p.id!=="MX000001"||p.media.id!=="Mdoc"||p.media.revision!==2)throw {code:"invalid_field"};
        state.maintenance.documents.push({id:"MDdoc",revision:1,asset_id:p.id,title:p.title,kind:p.kind,note:p.note,status:"attached",attachment:{id:"Mdoc",revision:3,status:"attached",purpose:"equipment_document",mime_type:"application/pdf",size_bytes:13}});
        result={id:"MDdoc",revision:1,asset_id:p.id,status:"attached"};
      }
      if(m.action==="maintenance.document_purge"){
        const row=state.maintenance.documents[0];row.revision++;row.status="deleted";delete row.attachment;
        result={id:row.id,revision:row.revision,asset_id:row.asset_id,status:row.status};
      }
      receipts.set(m.operation_id,structuredClone(result));
      if(window.documentLose&&m.action!=="media.reserve"){window.documentLose=false;throw {code:"storage_error"};}
      return result;
    },fetchWithAuth:async(path,options)=>{
      window.documentHttp.push({path,method:options.method});
      return options.method==="PUT"?new Response(JSON.stringify({id:"Mdoc",revision:2,status:"available"}),{headers:{"content-type":"application/json"}}):new Response("synthetic pdf",{headers:{"content-type":"application/pdf","content-length":"13"}});
    }};
    await card.refresh();
  });
  return page.locator("family-maintenance-card .asset-documents");
}
async function upload(section,lang){
  const c=DOCUMENT_COPY[lang];
  await section.getByRole("button",{name:c.add,exact:true}).click();
  await section.locator('[name="document_file"]').setInputFiles({name:"synthetic.pdf",mimeType:"application/pdf",buffer:Buffer.from("synthetic pdf")});
  await section.locator('[name="title"]').fill("Synthetic warranty");
  await section.locator('[name="note"]').fill("<img src=x onerror=alert(1)>");
  await section.getByRole("button",{name:c.upload,exact:true}).click();
  await expect(section.getByRole("button",{name:c.attach,exact:true})).toBeEnabled();
}
for(const lang of ["en","ru","uk"])test(`${lang} mobile equipment document upload, explicit attachment/download and owner removal`,async({page})=>{
  const c=DOCUMENT_COPY[lang],section=await setup(page,lang);
  await upload(section,lang);
  expect(await page.evaluate(()=>window.documentCalls.map(x=>x.action))).toEqual(["media.reserve"]);
  await section.scrollIntoViewIfNeeded();
  await page.screenshot({path:`test-results/documents-${lang}.png`,fullPage:true});
  await section.getByRole("button",{name:c.attach,exact:true}).click();
  await expect(section.locator("[data-document-form]")).toHaveCount(0);
  await expect(section).toContainText("<img src=x onerror=alert(1)>");
  await expect(section.locator("img,iframe,object,embed")).toHaveCount(0);
  expect(await page.evaluate(()=>window.documentHttp.filter(x=>x.method==="GET").length)).toBe(0);
  await section.getByRole("button",{name:c.download,exact:true}).click();
  const link=section.locator("a[download]");await expect(link).toHaveAttribute("download","family-assistant-document.pdf");
  const downloaded=page.waitForEvent("download");await link.click();
  expect((await downloaded).suggestedFilename()).toBe("family-assistant-document.pdf");
  await section.getByRole("button",{name:c.purge,exact:true}).click();
  await expect(section).toContainText(c.purge_warning);
  await section.locator('[name="reason"]').fill("Synthetic removal reviewed");
  await section.getByRole("button",{name:c.confirm_purge,exact:true}).click();
  await expect(section).toContainText(c.deleted);await expect(section.locator("a[download]")).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test("uncertain attachment retries exactly once without duplicate document",async({page})=>{
  const section=await setup(page,"en");await upload(section,"en");
  await page.evaluate(()=>{window.documentLose=true;});
  await section.getByRole("button",{name:DOCUMENT_COPY.en.attach,exact:true}).click();
  const retry=section.getByRole("button",{name:DOCUMENT_COPY.en.retry,exact:true});await expect(retry).toBeEnabled();
  await page.evaluate(()=>{window.card._pending={id:"unrelated"};});await retry.click();
  await expect(section.locator("[data-document-form]")).toHaveCount(0);
  const state=await page.evaluate(()=>({calls:window.documentCalls,rows:window.fixture.maintenance.documents}));
  expect(state.calls[1]).toEqual(state.calls[2]);expect(state.rows).toHaveLength(1);
});
