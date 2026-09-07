import {wallTimeCandidates} from "./local-time.js";
import {personalTaskCopy} from "./personal-task-copy.js";

export const TASK_FORM_COPY = {
  en: {checklist:"Steps — one per line (optional)", reportType:"Report required", text:"Text", none:"No report text", zone:"Deadline uses household time zone", fold:"This time occurs twice. Choose an occurrence", choose:"Choose…", first:"First occurrence", second:"Second occurrence", invalid:"This local time does not exist or is invalid. Choose another time.", retry:"Retry the same task", frozen:"The outcome is unconfirmed. Retry sends the same task, without creating a second copy."},
  ru: {checklist:"Шаги — по одному в строке (необязательно)", reportType:"Требуемый отчёт", text:"Текст", none:"Без текста отчёта", zone:"Срок в часовом поясе семьи", fold:"Это время встречается дважды. Выберите вариант", choose:"Выберите…", first:"Первое вхождение", second:"Второе вхождение", invalid:"Такого местного времени нет или оно некорректно. Выберите другое.", retry:"Повторить ту же задачу", frozen:"Результат не подтверждён. Повтор отправит ту же задачу, не создавая вторую копию."},
  uk: {checklist:"Кроки — по одному в рядку (необов’язково)", reportType:"Потрібний звіт", text:"Текст", none:"Без тексту звіту", zone:"Строк у часовому поясі сім’ї", fold:"Цей час трапляється двічі. Виберіть варіант", choose:"Виберіть…", first:"Перше входження", second:"Друге входження", invalid:"Такого місцевого часу немає або він некоректний. Виберіть інший.", retry:"Повторити те саме завдання", frozen:"Результат не підтверджено. Повтор надішле те саме завдання, не створюючи другу копію."},
};
const el=(tag,text)=>{const node=document.createElement(tag);if(text!=null)node.textContent=text;return node;};

export function renderTaskForm(card) {
  const copy=TASK_FORM_COPY[card._config?.language || card._hass?.language?.split("-")[0]] || TASK_FORM_COPY.en;
  const generation=card._generation,actor=card._data.actor;
  const actorRevision=card._data.members.find(m=>m.id===actor)?.revision;
  const personalCopy=personalTaskCopy(card);
  const zone=card._data.settings.timezone || card._hass?.config?.time_zone || "UTC";
  const draft=card._taskCreateDraft ||= {title:"",assignee:"",due_at:"",fold:"",checklist:"",report_type:"text"};
  const form=el("form");form.dataset.taskCreate="true";
  const title=card.input(form,"title",card.t.title,"text",draft.title);title.maxLength=500;
  const personalWrap=el("label",personalCopy.label),personal=el("input");
  personal.type="checkbox";personal.name="personal";personal.checked=draft.personal===true;
  personalWrap.prepend(personal);form.append(personalWrap);
  const personalHint=el("p",personalCopy.hint);personalHint.className="sub";personalHint.hidden=!personal.checked;form.append(personalHint);
  const assignee=card.memberSelect(form);
  if(draft.assignee && [...assignee.options].some(o=>o.value===draft.assignee)) assignee.value=draft.assignee;
  else if(draft.assignee) {const missing=el("option",card.t.selectMember);missing.value="";assignee.prepend(missing);assignee.value="";}
  assignee.required=true;
  const due=card.input(form,"due_at",card.t.due,"datetime-local",draft.due_at,false);
  due.min="0001-01-01T00:00";due.max="9999-12-31T23:59";
  const hint=el("p",`${copy.zone}: ${zone}`);hint.className="sub";form.append(hint);
  const foldWrap=el("label",copy.fold),fold=el("select");fold.name="due_fold";
  for(const [value,label] of [["",copy.choose],["0",copy.first],["1",copy.second]]) {const option=el("option",label);option.value=value;fold.append(option);}
  fold.value=draft.fold;foldWrap.append(fold);form.append(foldWrap);
  const invalid=el("p",copy.invalid);invalid.className="notice";invalid.setAttribute("role","alert");invalid.hidden=true;form.append(invalid);
  const updateDue=()=>{
    invalid.hidden=true;foldWrap.hidden=true;fold.required=false;
    if(!due.value)return [];
    try {
      const candidates=wallTimeCandidates(due.value,zone);
      invalid.hidden=candidates.length>0;foldWrap.hidden=candidates.length<2;fold.required=candidates.length>1;
      return candidates;
    } catch {invalid.hidden=false;return [];}
  };
  updateDue();
  const checklistWrap=el("label",copy.checklist),checklist=el("textarea");
  checklist.name="checklist";checklist.rows=3;checklist.value=draft.checklist;checklist.maxLength=10049;checklistWrap.append(checklist);form.append(checklistWrap);
  const reportWrap=el("label",copy.reportType),report=el("select");report.name="report_type";
  for(const value of ["text","photo","none"]) {const option=el("option",value==="photo"?({en:"Photo",ru:"Фото",uk:"Фото"}[card._config?.language || card._hass?.language?.split("-")[0]] || "Photo"):copy[value]);option.value=value;report.append(option);}
  report.value=draft.report_type;reportWrap.append(report);form.append(reportWrap);
  const advanced=el("details");advanced.append(el("summary",card.t.advanced));card.deadlinePolicy(advanced);form.append(advanced);
  for(const key of ["reminder_minutes","grace_minutes","penalty"]) {
    const input=form.elements.namedItem(key);if(input && key in draft)input.value=draft[key];
  }
  const canInteract=()=>!card._writing && card._generation===generation && card._data?.actor===actor && card._data.members.find(m=>m.id===actor)?.revision===actorRevision && card._data.role!=="guest" && card._data.settings.modules?.includes("tasks") && zone===(card._data.settings.timezone || card._hass?.config?.time_zone || "UTC");
  const syncPersonal=()=>{
    personalHint.hidden=!personal.checked;
    if(personal.checked){
      assignee.value=actor;report.value="none";
      draft.assignee=actor;draft.report_type="none";
      for(const key of ["grace_minutes","penalty"]){const input=form.elements.namedItem(key);if(input)input.value="0";draft[key]="0";}
    }
    for(const field of [assignee,report,...["grace_minutes","penalty"].map(key=>form.elements.namedItem(key)).filter(Boolean)])field.disabled=!!card._writing || !!draft.payload || personal.checked;
  };
  form.addEventListener("input",event=>{
    if(!canInteract() || draft.payload)return;
    if(event.target===checklist)checklist.setCustomValidity("");
    if(event.target.name)draft[event.target.name==="due_fold"?"fold":event.target.name]=event.target===personal?personal.checked:event.target.value;
    if(event.target===personal)syncPersonal();
    if(event.target===due){draft.fold="";fold.value="";updateDue();}
  });
  form.addEventListener("change",event=>{
    if(!canInteract() || draft.payload)return;
    if(event.target.name)draft[event.target.name==="due_fold"?"fold":event.target.name]=event.target===personal?personal.checked:event.target.value;
    if(event.target===personal)syncPersonal();
  });
  if(draft.payload){const frozen=el("p",copy.frozen);frozen.className="notice";form.append(frozen);}
  const submit=el("button",draft.payload?copy.retry:card.t.save);submit.type="submit";submit.className="primary";form.append(submit);
  for(const field of form.querySelectorAll("input,select,textarea"))field.disabled=!!card._writing || !!draft.payload;
  syncPersonal();
  submit.disabled=!!card._writing;
  form.addEventListener("submit",async event=>{
    event.preventDefault();if(!canInteract())return;
    if(!draft.payload){
      if(!form.checkValidity())return;
      const candidates=updateDue();if(due.value && !candidates.length)return;
      if(candidates.length>1 && !["0","1"].includes(fold.value)){fold.reportValidity();return;}
      const selected=card._data.members.find(m=>m.id===assignee.value && m.active && m.role!=="guest");
      if(!selected || (!card.parent && selected.id!==actor))return;
      const steps=checklist.value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
      if(steps.length>50 || steps.some(s=>s.length>200)){checklist.setCustomValidity(card.t.failure);checklist.reportValidity();return;}
      checklist.setCustomValidity("");
      draft.payload={title:title.value.trim(),assignee:selected.id,report_type:report.value,checklist:steps};
      if(personal.checked){if(selected.id!==actor)return;draft.payload.personal=true;}
      if(due.value)draft.payload.due_at=candidates.length===1?candidates[0]:candidates[Number(fold.value)];
      for(const key of ["reminder_minutes","grace_minutes","penalty"]) {
        const input=form.elements.namedItem(key);if(input)draft.payload[key]=Number(input.value);
      }
    }
    await card.command("tasks.create",draft.payload);
    if(card._generation!==generation)return;
    if(!card._actionError)card._taskCreateDraft=null;
    card.render();
  });
  return form;
}
