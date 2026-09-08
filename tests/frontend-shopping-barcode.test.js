import assert from "node:assert/strict";
import {test, afterEach} from "node:test";
import {JSDOM} from "jsdom";
import {normalizeGtin, detectedGtin} from "../custom_components/family_assistant/frontend/gtin.js";
import {BARCODE_COPY, renderBarcodeCamera, stopBarcodeCamera} from "../custom_components/family_assistant/frontend/shopping-barcode.js";

const dom = new JSDOM("<!doctype html><body></body>", {url:"https://localhost",pretendToBeVisual:true});
globalThis.window = dom.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, "navigator", {value:dom.window.navigator,configurable:true});
globalThis.isSecureContext = true;
dom.window.HTMLVideoElement.prototype.play = async () => {};
Object.defineProperty(dom.window.HTMLVideoElement.prototype, "readyState", {get:()=>4});
const settle = async () => { for (let n=0;n<8;n++) await Promise.resolve(); };
const pending = () => { let resolve, reject; const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject}; };
let active;
afterEach(() => { if(active) stopBarcodeCamera(active);active=null;document.body.replaceChildren();globalThis.isSecureContext=true; });

test("GTIN shapes, canonical equivalence, check digit and exact detector format", () => {
  for (const [raw,canonical] of [["96385074","00000096385074"],["036000291452","00036000291452"],["0036000291452","00036000291452"],["4006381333931","04006381333931"],["10012345000017","10012345000017"],["",""]]) {
    assert.equal(normalizeGtin(raw),canonical);
    assert.equal(normalizeGtin(` ${raw} `),canonical);
    if (raw) assert.throws(()=>normalizeGtin(raw.slice(0,-1)+(Number(raw.at(-1))+1)%10));
  }
  for (const raw of [null,undefined,0,false,[],{},"00000000","00000000000000","٩٦٣٨٥٠٧٤","9638-5074","9638 5074","9638507x","123456789"]) assert.throws(()=>normalizeGtin(raw));
  for (const result of [{format:"ean_8",rawValue:"96385074"},{format:"upc_a",rawValue:"036000291452"},{format:"ean_13",rawValue:"4006381333931"},{format:"itf",rawValue:"10012345000017"}]) assert.equal(detectedGtin(result),normalizeGtin(result.rawValue));
  for (const result of [null,{format:"upc_e",rawValue:"96385074"},{format:"qr_code",rawValue:"96385074"},{format:"ean_13",rawValue:"96385074"},{format:"itf",rawValue:"036000291452"},{format:"toString",rawValue:"96385074"}]) assert.throws(()=>detectedGtin(result));
});

test("barcode copy parity and no empty translations", () => {
  for (const lang of ["ru","uk"]) assert.deepEqual(Object.keys(BARCODE_COPY[lang]).sort(),Object.keys(BARCODE_COPY.en).sort());
  for (const copy of Object.values(BARCODE_COPY)) for (const text of Object.values(copy)) assert.ok(text.trim());
});

function fixture({formats=["ean_13","qr_code"],acquire,detect,play}={}) {
  const tracks={stops:0,stop(){this.stops++;}};
  const stream={getTracks:()=>[tracks]};
  const reads=[];let asks=0, detections=0, allowed=true;
  Object.defineProperty(navigator,"mediaDevices",{configurable:true,value:{getUserMedia:async options=>{
    asks++;assert.equal(options.audio,false);return acquire ? acquire() : stream;
  }}});
  globalThis.BarcodeDetector=class {
    static async getSupportedFormats(){return formats;}
    constructor({formats:selected}){assert.equal(selected.includes("qr_code"),false);}
    async detect(){detections++;return detect ? detect() : [{format:"ean_13",rawValue:"4006381333931"}];}
  };
  dom.window.HTMLVideoElement.prototype.play=play || (async()=>{});
  const card={_writing:false,button(text,fn){const b=document.createElement("button");b.type="button";b.textContent=text;b.addEventListener("click",fn);return b;}};
  active=card;
  const host=document.createElement("div");document.body.append(host);
  const options={isCurrent:()=>allowed,onRead:code=>reads.push(code)};
  renderBarcodeCamera(card,host,options);
  return {card,host,stream,tracks,reads,options,start:()=>host.querySelector("button").click(),revoke:()=>{allowed=false;},get asks(){return asks;},get detections(){return detections;}};
}

test("render never opens camera; one valid code fills draft and stops every track", async()=>{
  const f=fixture();assert.equal(f.asks,0);f.start();await settle();
  assert.equal(f.asks,1);assert.deepEqual(f.reads,["04006381333931"]);
  assert.equal(f.tracks.stops,1);assert.equal(f.card._barcodeCamera,null);assert.equal(f.host.querySelector("video").srcObject,null);
  assert.match(f.host.textContent,/Check the item details/);
});

for (const reason of ["unsupported","insecure","format"]) test(`manual fallback without camera request: ${reason}`,async()=>{
  const f=fixture({formats:reason==="format"?["qr_code"]:undefined});
  if(reason==="unsupported") delete globalThis.BarcodeDetector;
  if(reason==="insecure") globalThis.isSecureContext=false;
  f.start();await settle();assert.equal(f.asks,0);assert.equal(f.reads.length,0);assert.match(f.host.textContent,/unavailable/);
});

for (const reason of ["cancel","revoke","remove","pagehide","hidden"]) test(`late permission stream is released after ${reason}`,async()=>{
  const permission=pending();const f=fixture({acquire:()=>permission.promise});f.start();await settle();assert.equal(f.asks,1);
  if(reason==="cancel")stopBarcodeCamera(f.card);
  if(reason==="revoke")f.revoke();
  if(reason==="remove")f.host.remove();
  if(reason==="pagehide")window.dispatchEvent(new dom.window.Event("pagehide"));
  if(reason==="hidden"){
    Object.defineProperty(document,"hidden",{value:true,configurable:true});
    document.dispatchEvent(new dom.window.Event("visibilitychange"));
    delete document.hidden;
  }
  permission.resolve(f.stream);await settle();assert.equal(f.tracks.stops,1);assert.deepEqual(f.reads,[]);assert.equal(f.card._barcodeCamera,null);
});

test("late detection after cancellation cannot fill another draft",async()=>{
  const detection=pending();const f=fixture({detect:()=>detection.promise});f.start();await settle();assert.equal(f.detections,1);
  stopBarcodeCamera(f.card);detection.resolve([{format:"ean_13",rawValue:"4006381333931"}]);await settle();
  assert.deepEqual(f.reads,[]);assert.equal(f.tracks.stops,1);
});

test("multiple products never choose an arbitrary code",async()=>{
  const f=fixture({detect:async()=>[{format:"ean_8",rawValue:"96385074"},{format:"ean_13",rawValue:"4006381333931"}]});
  f.start();await settle();assert.deepEqual(f.reads,[]);assert.match(f.host.textContent,/Several codes/);stopBarcodeCamera(f.card);assert.equal(f.tracks.stops,1);
});

for (const reason of ["permission","play","decode"]) test(`safe bounded error: ${reason}`,async()=>{
  const fail=async()=>{throw new Error("PRIVATE provider detail");};
  const f=fixture({acquire:reason==="permission"?fail:undefined,play:reason==="play"?fail:undefined,detect:reason==="decode"?fail:undefined});
  f.start();await settle();assert.deepEqual(f.reads,[]);assert.equal(f.card._barcodeCamera,null);assert.match(f.host.textContent,/Could not read/);assert.doesNotMatch(f.host.textContent,/PRIVATE/);assert.equal(f.tracks.stops,reason==="permission"?0:1);
});

test("polling rerender never restarts a camera without a new click",async()=>{
  const decode=pending();const f=fixture({detect:()=>decode.promise});f.start();await settle();
  f.host.replaceChildren();renderBarcodeCamera(f.card,f.host,f.options);assert.equal(f.asks,1);assert.equal(f.tracks.stops,1);
  decode.resolve([{format:"ean_13",rawValue:"4006381333931"}]);await settle();assert.deepEqual(f.reads,[]);
});

test("one-minute deadline stops a hung decoder and ignores its eventual result",async()=>{
  const real=globalThis.setTimeout;let deadline;const decode=pending();
  globalThis.setTimeout=(fn,ms,...args)=>ms===60000?(deadline=fn,0):real(fn,ms,...args);
  try {
    const f=fixture({detect:()=>decode.promise});f.start();await settle();assert.equal(typeof deadline,"function");
    deadline();assert.equal(f.tracks.stops,1);assert.match(f.host.textContent,/Scanning stopped/);
    decode.resolve([{format:"ean_13",rawValue:"4006381333931"}]);await settle();assert.deepEqual(f.reads,[]);
  } finally {globalThis.setTimeout=real;}
});
