"""Standalone browser smoke test of the Academy card with a synthetic WS adapter."""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

CARD = (Path(__file__).resolve().parents[1] / "custom_components/family_assistant/frontend"
        / "academy-card.js")

MOCK = """
let mode='parent', enrolled=false, epoch=0, pos=0, paused=false, active=false, forbidden=false;
let calls=[], replyLost=false, receipts={};
const student=()=>({id:'child',name:'Example child',member_revision:1,epoch,enrolled});
const knowledge={fraction_value:{status:'unknown',level:1,correct:0,attempts:0,accuracy:null,due:null}};
const current=()=>active?{session_id:'session',status:paused?'paused':'active',position:pos,total:2,
  mode:pos===0?'practice':'exit',skill:'fraction_value',hints_used:0,
  task:{id:'task'+pos,template:'read_bar',prompt:'What fraction is filled?',parameters:[2,5],hint_count:pos===0?2:0}}:null;
const report={independent_correct:1,independent_total:2,results:[{correct:false,solution:'Try equal parts.'},{correct:true,solution:'2/5'}]};
function hass(){return {user:{id:mode},language:'en',callWS:async msg=>{
  calls.push(msg);if(forbidden)throw {code:'forbidden'};
  if(msg.type==='family_assistant/households')return [{entry_id:'house',title:'Example'}];
  const p=msg.payload||{};
  if(msg.action==='read'){
    if(mode==='parent')return p.member_id?{role:'parent',student:student(),knowledge}:{role:'parent',students:[student()]};
    return {role:'child',student:student(),current:current(),...(!active?{knowledge,...(pos===2?{last_report:report}:{})}:{})};
  }
  if(msg.action==='enroll'){enrolled=p.enabled;epoch++;return student();}
  if(receipts[p.operation_id])return receipts[p.operation_id];
  if(msg.action==='start'){active=true;pos=0;return current();}
  if(msg.action==='hint')return {status:'hint',text:'Count the filled pieces.'};
  if(msg.action==='pause'){paused=true;return current();}
  if(msg.action==='resume'){paused=false;return current();}
  if(msg.action==='answer'){
    let result=pos===0?{status:'recorded',correct:false,solution:'Try equal parts.'}:{status:'completed',report};
    pos++;if(pos===2)active=false;receipts[p.operation_id]=result;
    if(replyLost){replyLost=false;throw Error('lost reply');}return result;
  }
  throw Error('Unexpected call');
}};}
const card=document.createElement('family-assistant-academy-card');document.body.append(card);
card.setConfig({entry_id:'house'});card.hass=hass();
"""


def check(executable):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=executable, args=["--no-sandbox"])
        for width in (390, 1024):
            page = browser.new_page(viewport={"width": width, "height": 850})
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            page.route("http*://**/*", lambda route: route.abort())
            page.set_content("<!doctype html><html><body></body></html>")
            page.add_script_tag(content=CARD.read_text().replace("export class", "class"))
            page.add_script_tag(content=MOCK)
            page.get_by_role("combobox").select_option("child")
            page.get_by_role("button", name="Enable learning").click()
            page.get_by_role("button", name="Pause enrollment").wait_for()
            page.evaluate("mode='child'; card.hass=hass()")
            page.get_by_role("button", name="Start mission").click()
            page.get_by_role("img", name="2 of 5 equal parts filled").wait_for()
            assert page.locator(".filled").count() == 2
            page.get_by_role("button", name="Hint", exact=True).click()
            page.get_by_text("Count the filled pieces.").wait_for()
            page.get_by_role("button", name="Pause", exact=True).click()
            page.get_by_role("button", name="Resume").click()
            page.get_by_role("textbox", name="Your answer").fill("1/2")
            page.evaluate("replyLost=true")
            page.get_by_role("button", name="Submit").click()
            page.get_by_role("button", name="Retry / refresh").wait_for()
            page.wait_for_function("!card.busy")
            page.get_by_role("button", name="Retry / refresh").click()
            page.get_by_text("exit · 2/2", exact=False).wait_for()
            assert page.get_by_role("button", name="Hint", exact=True).count() == 0
            assert page.get_by_role("button", name="Show solution").count() == 0
            page.get_by_role("textbox", name="Your answer").fill("2/5")
            page.get_by_role("button", name="Submit").click()
            page.get_by_text("1/2 independent answers").wait_for()
            assert page.evaluate("calls.filter(c=>c.action==='answer')[0].payload.operation_id===calls.filter(c=>c.action==='answer')[1].payload.operation_id")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.evaluate("forbidden=true; card.refresh()")
            page.get_by_text("Academy is disabled or unavailable.").wait_for()
            assert page.get_by_text("1/2 independent answers").count() == 0
            assert not errors, errors
            page.close()
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    check(parser.parse_args().chromium)
    print("Passed: two synthetic Academy card browser scenarios (390px, 1024px)")
