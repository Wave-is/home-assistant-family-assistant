/* Private, explicit reasons for rejecting a model proposal; never auto-learn or execute. */
export const FEEDBACK_COPY = {
  en: {open:"Reject and describe the problem",hint:"This rejects the pending proposal and saves a private note for your account. The expected command is not executed or learned. Notes are not anonymous and never enter technical exports.",
    category:"What was wrong?",wrong_action:"Wrong action",wrong_target:"Wrong target",wrong_time:"Wrong time",other:"Other",
    expected:"What you meant (not executed)",source:"Original request (optional, exact text required)",
    confirm:"I want to reject this proposal and save this private note",save:"Reject and save note",
    title:"Your private correction notes",journalHint:"These notes are visible only to your current family identity. They do not execute or teach commands and are excluded from technical exports.",empty:"No private notes yet.",missing:"Original request was not supplied.",
    purge:"Delete this note",purgeConfirm:"Delete only this note; keep the original proposal and its history",
    unavailable:"Correction storage needs review. Existing notes were not changed."},
  ru: {open:"Отклонить и описать ошибку",hint:"Предложение будет отклонено, заметка сохранится только для вашего аккаунта. Ожидаемая команда не выполнится и не станет правилом. Заметки не анонимны и не попадают в технические выгрузки.",
    category:"Что не так?",wrong_action:"Не то действие",wrong_target:"Не тот объект",wrong_time:"Не то время",other:"Другое",
    expected:"Что вы имели в виду (без выполнения)",source:"Исходный запрос (необязательно, нужен точный текст)",
    confirm:"Отклонить это предложение и сохранить личную заметку",save:"Отклонить и сохранить заметку",
    title:"Ваши личные заметки об ошибках",journalHint:"Эти заметки видны только вашему текущему аккаунту семьи. Они не выполняют и не обучают команды, не попадают в технические выгрузки.",empty:"Личных заметок пока нет.",missing:"Исходный запрос не указан.",
    purge:"Удалить эту заметку",purgeConfirm:"Удалить только заметку, сохранив исходное предложение и его историю",
    unavailable:"Хранилище замечаний требует проверки. Прежние заметки не изменены."},
  uk: {open:"Відхилити й описати помилку",hint:"Пропозицію буде відхилено, нотатка збережеться лише для вашого акаунта. Очікувана команда не виконається й не стане правилом. Нотатки не анонімні та не потрапляють у технічні експорти.",
    category:"Що не так?",wrong_action:"Не та дія",wrong_target:"Не той об'єкт",wrong_time:"Не той час",other:"Інше",
    expected:"Що ви мали на увазі (без виконання)",source:"Початковий запит (необов'язково, потрібен точний текст)",
    confirm:"Відхилити цю пропозицію та зберегти особисту нотатку",save:"Відхилити й зберегти нотатку",
    title:"Ваші особисті нотатки про помилки",journalHint:"Ці нотатки доступні лише вашому поточному акаунту сім’ї. Вони не виконують і не навчають команди, не потрапляють у технічні експорти.",empty:"Особистих нотаток поки немає.",missing:"Початковий запит не вказано.",
    purge:"Видалити цю нотатку",purgeConfirm:"Видалити лише нотатку, зберігши початкову пропозицію та її історію",
    unavailable:"Сховище зауважень потребує перевірки. Попередні нотатки не змінено."},
};
const CATEGORIES = ["wrong_action","wrong_target","wrong_time","other"];
const drafts = new WeakMap();
export const disposeSemanticFeedback = card => drafts.delete(card);
const node = (tag,text,css) => {const e=document.createElement(tag); if(text!=null)e.textContent=text;if(css)e.className=css;return e;};
const copy = card => FEEDBACK_COPY[(card._config?.language||card._hass?.language||"en").split("-")[0]]||FEEDBACK_COPY.en;
const scope = card => {
  const d=card._data,m=d?.members?.find(row=>row.id===d.actor);
  if(!card.isConnected||!card._entry||!card._hass?.user?.id||!d?.settings?.modules?.includes("conversation")||
     m?.active!==true||!Number.isSafeInteger(m.revision)||m.revision<1||m.role!==d.role||!["owner","parent","adult","child"].includes(d.role))return null;
  return JSON.stringify([card._entry,card._generation,card._hass.user.id,d.actor,m.revision,d.role]);
};
const label = (form,text,name,maximum,required=true) => {
  const wrap=node("label",text),input=node("textarea");input.name=name;input.maxLength=maximum;
  input.required=required;input.rows=2;wrap.append(input);form.append(wrap);return input;
};
const consent = (form,text) => {const wrap=node("label"),check=node("input");check.type="checkbox";check.required=true;wrap.append(check,document.createTextNode(text));form.append(wrap);return check;};
const style = () => node("style",`.semantic-feedback form{display:grid;gap:12px;margin-top:12px}.semantic-feedback label{display:grid;gap:6px}.semantic-feedback textarea{box-sizing:border-box;width:100%;max-width:100%;resize:vertical}.semantic-feedback label:has(input[type=checkbox]){display:flex;align-items:center;gap:10px}.semantic-feedback p{white-space:pre-wrap;overflow-wrap:anywhere}.semantic-feedback select{max-width:100%;min-width:0}`);

export function appendProposalFeedback(card,item,plan) {
  const expectedScope=scope(card);if(!expectedScope)return;
  const expires=Date.parse(plan?.expires_at);
  if(plan.status!=="pending"||!Number.isFinite(expires)||expires<=Date.now())return;
  const user=card._hass.user;
  let state=drafts.get(card);
  if(!state||state.scope!==expectedScope||state.user!==user){state={scope:expectedScope,user,notes:new Map()};drafts.set(card,state);}
  const valid=new Set((card._data.proposals||[]).filter(p=>p.status==="pending"&&Date.parse(p.expires_at)>Date.now()).map(p=>p.id));
  for(const id of state.notes.keys())if(!valid.has(id))state.notes.delete(id);
  const pinned=JSON.stringify(plan);
  let draft=state.notes.get(plan.id);
  if(!draft||draft.plan!==pinned){draft={plan:pinned,category:CATEGORIES[0],expected:"",source:"",confirmed:false,open:false};state.notes.set(plan.id,draft);}
  const c=copy(card),details=node("details",null,"semantic-feedback");
  details.open=draft.open;
  details.append(style(),node("summary",c.open),node("p",c.hint,"sub"));
  const form=node("form"),categoryLabel=node("label",c.category),select=node("select");select.name="category";
  for(const key of CATEGORIES){const o=node("option",c[key]);o.value=key;select.append(o);}
  categoryLabel.append(select);form.append(categoryLabel);
  const expected=label(form,c.expected,"expected",400),source=label(form,c.source,"source",4096,false);
  const check=consent(form,c.confirm),button=node("button",c.save);button.type="submit";form.append(button);
  select.value=draft.category;expected.value=draft.expected;source.value=draft.source;check.checked=draft.confirmed;
  const currentAccess=()=>form.isConnected&&scope(card)===expectedScope&&card._hass.user===user&&drafts.get(card)===state;
  form.addEventListener("input",()=>{if(currentAccess())Object.assign(draft,{category:select.value,expected:expected.value,source:source.value,confirmed:check.checked});});
  details.addEventListener("toggle",()=>{if(currentAccess())draft.open=details.open;});
  form.addEventListener("submit",event=>{
    event.preventDefault();
    const current=card._data?.proposals?.find(row=>row.id===plan.id);
    if(card._writing||!currentAccess()||!form.checkValidity()||
       JSON.stringify(current)!==pinned||Date.parse(plan.expires_at)<=Date.now()||
       !check.checked||!expected.value.trim()||!CATEGORIES.includes(select.value))return;
    const feedback={category:select.value,expected:expected.value};
    if(source.value)feedback.source=source.value;
    card.command("conversation.reject",{id:plan.id,feedback});
  });
  details.append(form);item.append(details);
}

export function renderFeedbackJournal(card,body) {
  const expectedScope=scope(card),projection=card._data?.semantic_feedback;
  if(!expectedScope||!projection){disposeSemanticFeedback(card);return;}
  const user=card._hass.user,member=card._data.members.find(row=>row.id===card._data.actor);
  const c=copy(card),section=node("section",null,"semantic-feedback semantic-feedback-journal");
  section.append(style(),node("h3",c.title),node("p",c.journalHint,"sub"));body.append(section);
  if(projection.available!==true||!Array.isArray(projection.records)){section.append(node("p",c.unavailable));return;}
  if(!projection.records.length)section.append(node("p",c.empty,"empty"));
  for(const row of projection.records.slice(0,64)){
    if(!row||row.actor!==card._data.actor||row.role!==card._data.role||row.actor_revision!==member.revision||
       !CATEGORIES.includes(row.category)||typeof row.expected!=="string"||typeof row.preview!=="string"||typeof row.source!=="string")continue;
    const article=node("article",null,"item"),form=node("form");
    article.append(node("strong",c[row.category]),node("p",row.preview),node("p",row.expected));
    article.append(node("p",row.source_available===true?row.source:c.missing,"sub"));
    const check=consent(form,c.purgeConfirm),button=node("button",c.purge);button.type="submit";form.append(button);
    const pinned=JSON.stringify(row);
    form.addEventListener("submit",event=>{
      event.preventDefault();
      const current=card._data?.semantic_feedback?.records?.find(r=>r.id===row.id);
      if(card._writing||!form.isConnected||scope(card)!==expectedScope||card._hass.user!==user||!check.checked||projection.available!==true||JSON.stringify(current)!==pinned)return;
      card.command("conversation.feedback_purge",{id:row.id,confirmed:true});
    });
    article.append(form);section.append(article);
  }
}
