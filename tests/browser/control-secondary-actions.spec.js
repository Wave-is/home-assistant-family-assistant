import {test,expect} from "./control-audit.js";
import {TASK_BATCH_COPY} from "../../custom_components/family_assistant/frontend/task-batch-copy.js";
import {TASK_FORM_COPY} from "../../custom_components/family_assistant/frontend/task-form.js";

test("secondary controls: recurring task disable and enable require named consent and exact committed retry",async({page})=>{
  await page.goto("/tests/fixtures/task-series.html?lang=en&actor=parent");const card=page.locator("family-tasks-card"),row=card.locator('[data-task-series-id="D000001"]');
  await row.getByRole("button",{name:"Disable",exact:true}).click();
  let review=card.locator(".task-series-review");await expect(review).toContainText("Take recycling out");
  await review.getByRole("button",{name:"Confirm disable",exact:true}).click();expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await review.getByRole("button",{name:"Cancel",exact:true}).click();await expect(review).toHaveCount(0);
  expect(await page.evaluate(()=>window.seriesFixture.task_series[0].enabled)).toBe(true);
  await row.getByRole("button",{name:"Disable",exact:true}).click();await review.locator('[name="confirm"]').check();
  await page.evaluate(()=>window.loseResponse=true);await review.getByRole("button",{name:"Confirm disable",exact:true}).click();
  await expect(review).toContainText("exact reviewed request is pending");await review.getByRole("button",{name:"Retry exact request",exact:true}).click();await expect(review).toHaveCount(0);
  await row.getByRole("button",{name:"Enable",exact:true}).click();await review.locator('[name="confirm"]').check();await review.getByRole("button",{name:"Confirm enable",exact:true}).click();
  await expect(review).toHaveCount(0);const calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(3);expect(calls[1]).toEqual(calls[0]);
  expect(calls[0]).toMatchObject({action:"tasks.series_enable",payload:{id:"D000001",revision:4,actor_revision:3,enabled:false}});
  expect(calls[2]).toMatchObject({action:"tasks.series_enable",payload:{id:"D000001",revision:5,actor_revision:3,enabled:true}});
  expect(await page.evaluate(()=>window.seriesFixture.task_series[0])).toMatchObject({enabled:true,revision:6,title:"Take recycling out",assignees:["child"]});
});

test("secondary controls: recurring editor and reviewed draft Cancel discard only unsent changes",async({page})=>{
  await page.clock.install({time:new Date("2026-09-07T12:00:00Z")});
  await page.goto("/tests/fixtures/task-series.html?lang=en&actor=parent");const card=page.locator("family-tasks-card");
  const initial=await page.evaluate(()=>structuredClone(window.seriesFixture.task_series));
  await card.getByRole("button",{name:"Review and edit",exact:true}).click();await card.locator('[name="title"]').fill("Discard this synthetic edit");
  await card.locator(".task-series-form").getByRole("button",{name:"Cancel",exact:true}).click();await expect(card.locator(".task-series-form")).toHaveCount(0);
  await card.getByRole("button",{name:"Review and edit",exact:true}).click();await expect(card.locator('[name="title"]')).toHaveValue("Take recycling out");
  await card.locator('[name="title"]').fill("Discard this reviewed edit");await card.locator('button[type="submit"]').click();
  await expect(card.locator(".task-series-review")).toContainText("Discard this reviewed edit");await card.locator(".task-series-review").getByRole("button",{name:"Cancel",exact:true}).click();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.seriesFixture.task_series)).toEqual(initial);
});

test("secondary controls: changed recurring series invalidates a focused toggle without writing",async({page})=>{
  await page.goto("/tests/fixtures/task-series.html?lang=en&actor=parent");const card=page.locator("family-tasks-card");
  await card.getByRole("button",{name:"Disable",exact:true}).click();await card.locator('[name="confirm"]').check();
  await page.evaluate(async()=>{window.seriesFixture.task_series[0].revision++;await window.card.refresh();});
  await expect(card.locator(".task-series-review")).toHaveCount(0);expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await page.goto("/tests/fixtures/task-series.html?lang=en&actor=child");await expect(card.getByRole("button",{name:"Disable",exact:true})).toHaveCount(0);
});

test("secondary controls: reject a proposal after failure without applying it or rejecting its sibling",async({page})=>{
  await page.goto("/tests/fixtures/conversation.html?lang=en&feedback=1");const card=page.locator("family-conversation-card");
  await page.evaluate(async()=>{window.fixture.proposals.push({id:"P456",status:"pending",preview:"Synthetic sibling proposal",expires_at:new Date(Date.now()+300000).toISOString()});await window.card.refresh();window.failure="reject-before";});
  const proposal=card.locator("section > .item").filter({hasText:"Предложено: добавить молоко"});
  await proposal.getByRole("button",{name:"Cancel plan",exact:true}).click();await expect(card.getByRole("alert")).toBeVisible();
  expect(await page.evaluate(()=>window.fixture.proposals.map(item=>item.id))).toEqual(["P123","P456"]);
  await proposal.getByRole("button",{name:"Cancel plan",exact:true}).click();await expect(card).not.toContainText("Предложено: добавить молоко");await expect(card).toContainText("Synthetic sibling proposal");
  const calls=await page.evaluate(()=>window.executeCalls);expect(calls).toHaveLength(2);expect(calls[1]).toEqual(calls[0]);expect(calls[0]).toMatchObject({action:"conversation.reject",payload:{id:"P123"}});
  expect(await page.evaluate(()=>window.chatCalls)).toEqual([]);expect(await page.evaluate(()=>window.fixture.feedback)).toEqual([]);
});

test("secondary controls: removing a court threshold is a draft until exact settings save",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=court&courtedit=1");const card=page.locator("family-assistant-card");
  await page.evaluate(()=>{window.courtFixture.court_config.thresholds=[{id:"rule-1",label:"Remove synthetic rule",direction:"at_most",points:-3,members:[]},{id:"rule-2",label:"Keep synthetic rule",direction:"at_least",points:5,members:["child"]}];window.card._data=structuredClone(window.courtFixture);window.card.render();});
  await card.getByRole("button",{name:"Configure weekly reports",exact:true}).click();await card.locator('[data-court-threshold="rule-1"]').getByRole("button",{name:"Remove threshold",exact:true}).click();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.courtFixture.court_config.thresholds.length)).toBe(2);
  await card.getByRole("button",{name:"Close settings",exact:true}).click();await card.getByRole("button",{name:"Configure weekly reports",exact:true}).click();await expect(card.locator("[data-court-threshold]")).toHaveCount(2);
  await card.locator('[data-court-threshold="rule-1"]').getByRole("button",{name:"Remove threshold",exact:true}).click();await page.evaluate(()=>window.failCommand=true);
  await card.getByRole("button",{name:"Save",exact:true}).click();await expect(card.getByRole("alert")).toBeVisible();await expect(card.getByRole("button",{name:"Add threshold",exact:true})).toBeDisabled();
  await page.evaluate(()=>window.failCommand=false);await card.getByRole("button",{name:"Retry",exact:true}).click();
  const calls=await page.evaluate(()=>window.calls);expect(calls).toHaveLength(2);expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].payload).toEqual({revision:1,weekly_enabled:false,weekday:0,time:"00:00",second_adult_review:false,thresholds:[{id:"rule-2",label:"Keep synthetic rule",direction:"at_least",points:5,members:["child"]}]});
  expect(await page.evaluate(()=>window.courtFixture.court_config.revision)).toBe(2);
});

test("secondary controls: court award, reversal and stale-review Cancel never write",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=court&courtedit=1");const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Award or deduct points",exact:true}).click();await card.locator('[name="reason"]').fill("Unsubmitted synthetic award");await card.getByRole("button",{name:"Cancel",exact:true}).click();
  await card.getByRole("button",{name:"Reverse",exact:true}).click();await card.locator('[name="reason"]').fill("Unsubmitted reversal");await card.getByRole("button",{name:"Cancel",exact:true}).click();
  await card.getByRole("button",{name:"Reverse",exact:true}).click();
  await page.evaluate(()=>{window.courtFixture.court[0].revision++;window.card._data=structuredClone(window.courtFixture);window.card.render();});
  const stale=card.locator("form");await expect(stale).toContainText("changed");await stale.getByRole("button",{name:"Cancel",exact:true}).click();await expect(stale).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.courtFixture.court[0].status)).toBe("active");
});

test("secondary controls: reward catalog, request and decision Cancel abandon only drafts",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=court&rewards=1");const card=page.locator("family-assistant-card"),item=card.locator("li.item").filter({hasText:"R000001 · Cinema trip"});
  await item.getByRole("button",{name:"Edit",exact:true}).click();await card.locator("form.editor").getByLabel("Name",{exact:true}).fill("Discard this reward title");await card.locator("form.editor").getByRole("button",{name:"Cancel",exact:true}).click();
  await item.getByRole("button",{name:"Request",exact:true}).click();await item.locator("form.editor").getByRole("button",{name:"Cancel",exact:true}).click();
  await page.evaluate(()=>{window.rewardFixture.rewards.requests=[{id:"V000001",name:"Synthetic unapproved request",member:"child",cost:10,status:"requested",revision:1,history:[]}];window.card._data=structuredClone(window.rewardFixture);window.card.render();});
  const request=card.locator("li.item").filter({hasText:"Synthetic unapproved request"});await request.getByRole("button",{name:"Reject",exact:true}).click();await request.locator("form.editor").getByLabel(/Mandatory reason/).fill("Unsubmitted decision");await request.locator("form.editor").getByRole("button",{name:"Cancel",exact:true}).click();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.rewardFixture.rewards.catalog[0].name)).toBe("Cinema trip");expect(await page.evaluate(()=>window.rewardFixture.rewards.requests[0].status)).toBe("requested");
});

test("secondary controls: parent cancellation of a requested reward releases only its reservation",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=court&rewards=1");const card=page.locator("family-assistant-card");
  await page.evaluate(()=>{window.rewardFixture.rewards.requests=[{id:"V000001",name:"Synthetic parent cancellation",member:"child",cost:10,status:"requested",revision:2,history:[]}];Object.assign(window.rewardFixture.rewards.balances[0],{reserved:10,net:5,available:5});window.card._data=structuredClone(window.rewardFixture);window.card.render();});
  const request=card.locator("li.item").filter({hasText:"Synthetic parent cancellation"});await request.getByRole("button",{name:"Cancel",exact:true}).click();const form=request.locator("form.editor");await form.getByLabel(/Mandatory reason/).fill("Synthetic reservation no longer needed");await form.locator('button[type="submit"]').click();
  await expect(form).toHaveCount(0);expect(await page.evaluate(()=>window.calls[0])).toMatchObject({action:"court.reward_transition",payload:{id:"V000001",revision:2,decision:"cancel",reason:"Synthetic reservation no longer needed"}});
  expect(await page.evaluate(()=>window.rewardFixture.rewards.requests[0])).toMatchObject({status:"cancelled",revision:3});expect(await page.evaluate(()=>window.rewardFixture.rewards.balances[0])).toMatchObject({reserved:0,spent:0,available:15});
});

async function batchSelection(page){
  await page.goto("/tests/fixtures/task-batch.html?lang=en");const panel=page.locator(".task-batch"),c=TASK_BATCH_COPY.en;
  await panel.locator("summary").click();await panel.getByRole("button",{name:c.startBatch,exact:true}).click();
  await panel.locator('[name="batch_action"]').selectOption("tasks.complete");await panel.locator('[name="task_select"][value="T000001"]').check();
  return {panel,c};
}

test("secondary controls: batch selection Cancel and review Back/Cancel preserve every task",async({page})=>{
  const {panel,c}=await batchSelection(page),initial=await page.evaluate(()=>structuredClone(window.fixture.tasks));
  await panel.getByRole("button",{name:c.cancel,exact:true}).click();await expect(panel.locator('[name="task_select"]')).toHaveCount(0);
  await panel.locator("summary").click();
  await panel.getByRole("button",{name:c.startBatch,exact:true}).click();await panel.locator('[name="task_select"][value="T000001"]').check();await panel.getByRole("button",{name:c.reviewBatch,exact:true}).click();
  await panel.getByRole("button",{name:c.back,exact:true}).click();await expect(panel.locator('[name="task_select"][value="T000001"]')).toBeChecked();
  await panel.getByRole("button",{name:c.reviewBatch,exact:true}).click();await panel.getByRole("button",{name:c.cancel,exact:true}).click();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.fixture.tasks)).toEqual(initial);await expect(panel.locator(".task-batch-review")).toHaveCount(0);
});

test("secondary controls: closing uncertain batch explicitly keeps committed work without replay or rollback",async({page})=>{
  const {panel,c}=await batchSelection(page);await panel.getByRole("button",{name:c.reviewBatch,exact:true}).click();await panel.getByLabel(c.confirmLabel,{exact:true}).check();
  await page.evaluate(()=>window.loseReplyOnce=true);await panel.getByRole("button",{name:c.applyBatch,exact:true}).click();await expect(panel).toContainText(c.uncertainNotice);
  const committed=await page.evaluate(()=>structuredClone(window.fixture.tasks));await panel.getByRole("button",{name:c.closeWithoutRollback,exact:true}).click();
  await expect(panel.locator(".task-batch-review")).toHaveCount(0);expect(await page.evaluate(()=>window.calls)).toHaveLength(1);expect(await page.evaluate(()=>window.fixture.tasks)).toEqual(committed);
  expect(committed.find(item=>item.id==="T000001")).toMatchObject({status:"completed",revision:2});expect(committed.find(item=>item.id==="T000002")).toMatchObject({status:"submitted",revision:1});
});

async function multiReview(page){
  await page.goto("/tests/fixtures/task-multi.html?lang=en");await page.getByRole("button",{name:"Add",exact:true}).click();const form=page.locator("form[data-task-create]"),c=TASK_FORM_COPY.en;
  await form.locator('[name="title"]').fill("Synthetic independent assignments");await form.locator('[name="multi"]').check();
  await form.locator('[name="assignee_multi"][value="first"]').check();await form.locator('[name="assignee_multi"][value="second"]').check();await form.locator('[name="due_at"]').fill("2026-10-20T17:00");
  await form.locator('button[type="submit"]').click();return {form,c};
}

test("secondary controls: multi-task review Back retains input and Cancel creates no records",async({page})=>{
  const {form,c}=await multiReview(page);await form.getByRole("button",{name:c.back,exact:true}).click();
  await expect(form.locator('[name="title"]')).toHaveValue("Synthetic independent assignments");await expect(form.locator('[name="assignee_multi"][value="second"]')).toBeChecked();
  await form.locator('button[type="submit"]').click();await form.getByRole("button",{name:c.cancel,exact:true}).click();await expect(form).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.fixture.tasks)).toEqual([]);
});

test("secondary controls: multi-task close without rollback preserves both committed assignments",async({page})=>{
  const {form,c}=await multiReview(page);await form.locator('[name="confirm_batch"]').check();await page.evaluate(()=>window.loseReplyOnce=true);
  await form.getByRole("button",{name:c.applyBatch,exact:true}).click();await expect(form).toContainText(c.uncertainNotice);
  const committed=await page.evaluate(()=>structuredClone(window.fixture.tasks));expect(committed.map(item=>item.assignee)).toEqual(["first","second"]);
  await form.getByRole("button",{name:c.closeWithoutRollback,exact:true}).click();await expect(form).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toHaveLength(1);expect(await page.evaluate(()=>window.fixture.tasks)).toEqual(committed);
});

test("secondary controls: failed household discovery Retry shows authorized choices and loads only the selected family",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=shopping&lang=en");const card=page.locator("family-assistant-card");await expect(card).toContainText("Apples");
  await page.evaluate(()=>{
    let failed=false;window.pickerCalls=[];
    window.card.hass={language:"en",user:{id:"synthetic-ha-user"},callWS:async message=>{
      window.pickerCalls.push(structuredClone(message));
      if(message.type==="family_assistant/households"){
        if(!failed){failed=true;throw {code:"storage_error"};}
        return [{entry_id:"first-family",title:"First synthetic family"},{entry_id:"second-family",title:"Second synthetic family"}];
      }
      if(message.type==="family_assistant/view"&&message.entry_id==="second-family")return {...structuredClone(window.fixture),settings:{...window.fixture.settings,name:"Second synthetic family"}};
      throw {code:"forbidden"};
    }};
    window.card.setConfig({view:"shopping",language:"en"});
  });
  await expect(card.getByRole("alert")).toBeVisible();await expect(card).not.toContainText("Apples");
  await card.getByRole("button",{name:"Try again",exact:true}).click();await expect(card.getByRole("button",{name:"First synthetic family",exact:true})).toBeVisible();
  await card.getByRole("button",{name:"Second synthetic family",exact:true}).click();await expect(card.locator(".eyebrow")).toHaveText("Second synthetic family");await expect(card).toContainText("Apples");
  expect(await page.evaluate(()=>window.pickerCalls)).toEqual([{type:"family_assistant/households"},{type:"family_assistant/households"},{type:"family_assistant/view",entry_id:"second-family"}]);
});

test("secondary controls: task edit, requested-changes note and stale draft dismiss never write",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=tasks&taskedit=1");const item=page.locator("family-assistant-card .body > ul.list > li.item").first();
  await item.getByRole("button",{name:"Edit task",exact:true}).click();await item.locator('[name="title"]').fill("Discard synthetic task rename");await item.getByRole("button",{name:"Cancel",exact:true}).click();
  expect(await page.evaluate(()=>window.fixture.tasks[0].title)).toBe("Water the plants");
  await item.getByRole("button",{name:"Edit task",exact:true}).click();
  await page.evaluate(()=>{window.fixture.tasks[0].revision++;window.card._data=structuredClone(window.fixture);window.card.render();});
  await expect(item.getByRole("alert")).toBeVisible();await item.getByRole("button",{name:"Cancel",exact:true}).click();await expect(item.getByRole("alert")).toHaveCount(0);
  await page.evaluate(()=>{Object.assign(window.fixture.tasks[0],{status:"submitted",report:"Synthetic submitted report"});window.card._data=structuredClone(window.fixture);window.card.render();});
  await item.getByRole("button",{name:"Request changes",exact:true}).click();await item.locator('[name="note"]').fill("Unsubmitted review note");await item.getByRole("button",{name:"Cancel",exact:true}).click();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.fixture.tasks[0])).toMatchObject({title:"Water the plants",status:"submitted",report:"Synthetic submitted report"});
  expect(await page.evaluate(()=>window.fixture.tasks[0].review_note)).toBeUndefined();
});
