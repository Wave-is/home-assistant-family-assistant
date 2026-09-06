import {chromium} from "@playwright/test";
import {readFile, mkdir, copyFile} from "node:fs/promises";
const browser=await chromium.launch({channel:process.env.CI?undefined:"chrome"});
try{
 const page=await browser.newPage({viewport:{width:256,height:256},deviceScaleFactor:1});
 const svg=await readFile(new URL("../brand/icon.svg",import.meta.url),"utf8");
 await page.setContent(`<style>body{margin:0}svg{width:256px;height:256px}</style>${svg}`);
 await page.locator("svg").screenshot({path:"brand/icon.png",omitBackground:true});
 await mkdir("custom_components/family_assistant/brand",{recursive:true});
 await copyFile("brand/icon.png","custom_components/family_assistant/brand/icon.png");
}finally{await browser.close();}
