/* Family Assistant cards. User data is inserted only through textContent. */
import {ERRORS} from "./errors.js";
const COPY = {
  en: {
    health:"System health",parentsOnly:"Only parents can review system delivery.",noDeliveryIssues:"No unresolved delivery problems.",uncertain:"Delivery uncertain",failed:"Delivery failed",awaiting_channel:"Waiting for a linked chat",connected:"Connected",retryDelivery:"Review and resend",resolveDelivery:"Resolve without resending",retryWarning:"Telegram may already have accepted the message. Resending can create a duplicate.",resolveWarning:"This closes the warning without resending or claiming delivery.",retryConsent:"I accept the possible duplicate",channelHint:"Link the recipient's private chat in the Telegram options.",
    today: "Family today", shopping: "Shopping", tasks: "Tasks", court: "Rules & rewards",
    alarms:"Wake-up alarms",alarmTime:"Wake-up time",timezone:"Time zone",days:"Days",weekdays:"Weekdays",weekends:"Weekends",everyday:"Every day",profile:"Wake-up style",gentle:"Messages only",strict:"Messages and dedicated siren",alarmPenalty:"Missed wake-up points (0 disables)",alarmDeviceHint:"Assign and test a dedicated siren in integration settings. Automatic penalties require separate opt-in.",moduleOff:"This module is disabled.",first:"First wake-up check",waiting_second:"Waiting for a second check",second:"Second wake-up check",testAlarm:"Test without penalties",soundRequested:"Sound requested — check the device status",soundPaused:"Sound paused",stopAlarm:"Stop this wake-up check",enabled:"Enabled",disabled:"Disabled",enable:"Enable",disable:"Disable",testAlarmWarning:"This test starts the selected siren in strict mode. No penalty will be issued.",startTest:"Start test",alarm_missed:"Wake-up was not confirmed in time",dayNames:["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
    empty: "All clear. Add something when you need it.", add: "Add", name: "Name",
    title: "What needs doing?", amount: "Amount", unit: "Unit", assignee: "Who?",
    due: "Due date", reason: "Reason", points: "Points", buy: "Bought", approve: "Approve",
    report: "Send report", complete: "Confirm done", reverse: "Reverse", pending: "Pending",
    loading: "Loading your family…", retry: "Try again", choose: "Choose a household",
    noHousehold: "No linked household. Add Family Assistant and link your HA account.",
    selectMember: "Choose a person", back: "Back", save: "Save", role: "Role",
    updated: "Saved", failure: "Could not complete this action.", open: "Open tasks",
    awaiting: "Awaiting approval", balance: "Balance", record: "Record", units: "units",
    refresh: "Refresh", entry: "Household", view: "View", reportLabel: "What did you do?",
    approved: "Ready to buy", purchased: "Bought", assigned: "Assigned", submitted: "In review",
    completed: "Completed", active: "Active", reversed: "Reversed", in_progress: "In progress",
    accepted: "Accepted", needs_changes: "Needs changes", rejected: "Rejected", archived: "Archived",
    cancelled: "Cancelled", unitPlaceholder: "kg, l, pcs", revision: "Revision",
  },
  ru: {
    health:"Состояние системы",parentsOnly:"Доставку уведомлений проверяют родители.",noDeliveryIssues:"Нет нерешённых проблем доставки.",uncertain:"Результат отправки неизвестен",failed:"Ошибка отправки",awaiting_channel:"Ожидается привязка чата",connected:"Подключён",retryDelivery:"Проверить и повторить",resolveDelivery:"Закрыть без повтора",retryWarning:"Telegram уже мог принять сообщение. Повторная отправка может создать дубликат.",resolveWarning:"Предупреждение будет закрыто без повтора и без утверждения о доставке.",retryConsent:"Понимаю, что возможен дубликат",channelHint:"Привяжите личный чат получателя в настройках Telegram.",
    today: "Семья сегодня", shopping: "Покупки", tasks: "Задачи", court: "Правила и поощрения",
    alarms:"Будильники",alarmTime:"Время подъёма",timezone:"Часовой пояс",days:"Дни",weekdays:"Будни",weekends:"Выходные",everyday:"Каждый день",profile:"Режим пробуждения",gentle:"Только сообщения",strict:"Сообщения и отдельная сирена",alarmPenalty:"Баллы за пропуск (0 — без штрафа)",alarmDeviceHint:"Назначьте и проверьте отдельную сирену в настройках интеграции. Автоштрафы включаются отдельно.",moduleOff:"Модуль выключен.",first:"Первая проверка подъёма",waiting_second:"Ожидается повторная проверка",second:"Повторная проверка подъёма",testAlarm:"Тест без штрафов",soundRequested:"Запрошен звук — проверьте состояние устройства",soundPaused:"Звук приостановлен",stopAlarm:"Остановить проверку подъёма",enabled:"Включён",disabled:"Выключен",enable:"Включить",disable:"Выключить",testAlarmWarning:"В строгом режиме тест включит назначенную сирену. Штрафов не будет.",startTest:"Начать тест",alarm_missed:"Подъём не подтверждён вовремя",dayNames:["Пн","Вт","Ср","Чт","Пт","Сб","Вс"],
    empty: "Всё спокойно. Добавьте запись, когда понадобится.", add: "Добавить", name: "Название",
    title: "Что нужно сделать?", amount: "Количество", unit: "Единица", assignee: "Кому?",
    due: "Срок", reason: "Причина", points: "Баллы", buy: "Куплено", approve: "Одобрить",
    report: "Сдать отчёт", complete: "Подтвердить", reverse: "Отменить балл", pending: "Ожидает",
    loading: "Загружаю семью…", retry: "Повторить", choose: "Выберите семью",
    noHousehold: "Нет привязанной семьи. Добавьте Family Assistant и свяжите пользователя HA.",
    selectMember: "Выберите участника", back: "Назад", save: "Сохранить", role: "Роль",
    updated: "Сохранено", failure: "Не удалось выполнить действие.", open: "Открытые задачи",
    awaiting: "Ждут решения", balance: "Баланс", record: "Записать", units: "позиций",
    refresh: "Обновить", entry: "Семья", view: "Раздел", reportLabel: "Что сделано?",
    approved: "Можно покупать", purchased: "Куплено", assigned: "Назначена", submitted: "На проверке",
    completed: "Выполнена", active: "Действует", reversed: "Отменён", in_progress: "В работе",
    accepted: "Принята", needs_changes: "На доработке", rejected: "Отклонено", archived: "В архиве",
    cancelled: "Отменена", unitPlaceholder: "кг, л, шт", revision: "Версия",
  },
  uk: {
    health:"Стан системи",parentsOnly:"Доставку сповіщень перевіряють батьки.",noDeliveryIssues:"Немає невирішених проблем доставки.",uncertain:"Результат надсилання невідомий",failed:"Помилка надсилання",awaiting_channel:"Очікується прив’язка чату",connected:"Підключено",retryDelivery:"Перевірити та повторити",resolveDelivery:"Закрити без повтору",retryWarning:"Telegram уже міг прийняти повідомлення. Повторне надсилання може створити дублікат.",resolveWarning:"Попередження буде закрито без повтору й без твердження про доставку.",retryConsent:"Розумію, що можливий дублікат",channelHint:"Прив’яжіть особистий чат отримувача в налаштуваннях Telegram.",
    today: "Родина сьогодні", shopping: "Покупки", tasks: "Завдання", court: "Правила та заохочення",
    alarms:"Будильники",alarmTime:"Час підйому",timezone:"Часовий пояс",days:"Дні",weekdays:"Будні",weekends:"Вихідні",everyday:"Щодня",profile:"Режим пробудження",gentle:"Лише повідомлення",strict:"Повідомлення та окрема сирена",alarmPenalty:"Бали за пропуск (0 — без штрафу)",alarmDeviceHint:"Призначте й перевірте окрему сирену в налаштуваннях інтеграції. Автоштрафи вмикаються окремо.",moduleOff:"Модуль вимкнено.",first:"Перша перевірка підйому",waiting_second:"Очікується повторна перевірка",second:"Повторна перевірка підйому",testAlarm:"Тест без штрафів",soundRequested:"Запитано звук — перевірте стан пристрою",soundPaused:"Звук призупинено",stopAlarm:"Зупинити перевірку підйому",enabled:"Увімкнено",disabled:"Вимкнено",enable:"Увімкнути",disable:"Вимкнути",testAlarmWarning:"У суворому режимі тест увімкне призначену сирену. Штрафів не буде.",startTest:"Почати тест",alarm_missed:"Підйом не підтверджено вчасно",dayNames:["Пн","Вт","Ср","Чт","Пт","Сб","Нд"],
    empty: "Усе спокійно. Додайте запис, коли знадобиться.", add: "Додати", name: "Назва",
    title: "Що потрібно зробити?", amount: "Кількість", unit: "Одиниця", assignee: "Кому?",
    due: "Термін", reason: "Причина", points: "Бали", buy: "Куплено", approve: "Схвалити",
    report: "Здати звіт", complete: "Підтвердити", reverse: "Скасувати бал", pending: "Очікує",
    loading: "Завантажую родину…", retry: "Повторити", choose: "Виберіть родину",
    noHousehold: "Немає прив’язаної родини. Додайте Family Assistant і зв’яжіть користувача HA.",
    selectMember: "Виберіть учасника", back: "Назад", save: "Зберегти", role: "Роль",
    updated: "Збережено", failure: "Не вдалося виконати дію.", open: "Відкриті завдання",
    awaiting: "Чекають рішення", balance: "Баланс", record: "Записати", units: "позицій",
    refresh: "Оновити", entry: "Родина", view: "Розділ", reportLabel: "Що зроблено?",
    approved: "Можна купувати", purchased: "Куплено", assigned: "Призначено", submitted: "На перевірці",
    completed: "Виконано", active: "Діє", reversed: "Скасовано", in_progress: "У роботі",
    accepted: "Прийнято", needs_changes: "На доопрацюванні", rejected: "Відхилено", archived: "В архіві",
    cancelled: "Скасовано", unitPlaceholder: "кг, л, шт", revision: "Версія",
  },
};
const STYLES = `
  :host {display:block;color:var(--primary-text-color,#182c32);font-family:var(--paper-font-body1_-_font-family,system-ui)}
  *{box-sizing:border-box} ha-card{display:block;overflow:hidden;border-radius:22px;background:var(--ha-card-background,var(--card-background-color,#fff));border:1px solid var(--divider-color,#dfe9e7)}
  header{padding:24px 24px 18px;background:linear-gradient(135deg,rgba(19,146,127,.13),rgba(76,167,222,.04))}
  .eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--secondary-text-color,#657d80)}
  h2{font-size:24px;line-height:1.2;margin:8px 0 0;font-weight:650;letter-spacing:-.03em}
  .body{padding:18px 24px 24px}.row{display:flex;align-items:center;gap:10px}.grow{flex:1;min-width:0}.sub{font-size:12px;color:var(--secondary-text-color,#657d80);margin-top:6px}
  .list{display:grid;gap:10px;margin:0;padding:0;list-style:none}.item{padding:14px;border:1px solid var(--divider-color,#e3ebe9);border-radius:14px;overflow-wrap:anywhere}
  .item strong{font-size:15px}.badge{display:inline-block;border-radius:8px;background:rgba(19,146,127,.09);padding:3px 6px;margin:5px 4px 0 0;font-size:11px}
  button,input,select{font:inherit} button{border:1px solid var(--divider-color,#dfe9e7);border-radius:10px;padding:9px 12px;cursor:pointer;background:var(--ha-card-background,#fff);color:inherit;min-height:40px}
  button:hover{background:rgba(19,146,127,.1)}button.primary{background:#087f70;color:white;border-color:#087f70}button:disabled{opacity:.5;cursor:wait}
  button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #55bcba;outline-offset:2px}
  .actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.empty{padding:28px 8px;text-align:center;color:var(--secondary-text-color,#657d80)}
  form{display:grid;gap:12px;margin:0 0 18px}label{display:grid;gap:5px;font-size:12px;color:var(--secondary-text-color,#657d80)}
  input,select{width:100%;min-width:0;border:1px solid var(--divider-color,#d3dfdd);border-radius:10px;padding:10px;background:var(--ha-card-background,#fff);color:var(--primary-text-color,#182c32);font-size:14px}
  .fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px}
  .metric{background:rgba(19,146,127,.07);padding:14px 8px;border-radius:14px;text-align:center}.metric b{display:block;font-size:25px}.metric span{font-size:11px}
  .notice{padding:12px;border-radius:12px;margin-bottom:12px;background:rgba(238,150,60,.14);font-size:13px}
  .toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:16px}.editor{padding:16px;display:grid;gap:12px}
  @media(max-width:400px){header{padding:20px 16px 16px}.body{padding:16px}.fields{grid-template-columns:1fr}h2{font-size:21px}}
`;

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

export class FamilyCard extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this._view = "today"; }
  setConfig(config) {
    this._config = {...config};
    this._view = config.view || this.constructor.defaultView || "today";
    if (!["today","shopping","tasks","court","alarms","health"].includes(this._view)) throw new Error("Unknown Family Assistant view");
    this._generation = (this._generation || 0) + 1;
    this._entry = config.entry_id;
    this._data = null;
    this.render();
    if (this._hass) this.refresh();
  }
  set hass(hass) { this._hass = hass; if (!this._data && !this._loading) this.refresh(); }
  get t() { return COPY[this._config?.language || this._hass?.language?.split("-")[0]] || COPY.en; }
  get parent() { return ["owner","parent"].includes(this._data?.role); }
  getCardSize() { return 5; }
  getGridOptions() { return {columns:12, rows:"auto", min_columns:6}; }
  static getConfigElement() { return document.createElement("family-assistant-card-editor"); }
  static getStubConfig() { return {view:this.defaultView || "today"}; }
  connectedCallback() { this._timer = setInterval(()=>this.refresh(),10000); }
  disconnectedCallback() { clearInterval(this._timer); }
  async refresh() {
    if (!this._hass || !this._config || this._loading || this._writing) return;
    this._loading = true;
    const generation = this._generation;
    try {
      if (!this._entry) {
        const entries = await this._hass.callWS({type:"family_assistant/households"});
        if (generation !== this._generation) return;
        this._entries = entries;
        if (entries.length === 1) this._entry = entries[0].entry_id;
        else { this.render(); return; }
      }
      const data = await this._hass.callWS({type:"family_assistant/view",entry_id:this._entry});
      if (generation !== this._generation) return;
      this._data = data; this._error = null;
      // Avoid destroying a form that the user is currently filling out.
      if (!this.shadowRoot.activeElement?.closest("form")) this.render();
    } catch(error) { if (generation === this._generation) { this._error=error.code || this.t.failure; this.render(); } }
    finally { this._loading = false; }
  }
  button(text, action, primary=false) {
    const button=el("button",text,primary?"primary":""); button.type="button";
    button.disabled=!!this._writing;
    button.addEventListener("click",action); return button;
  }
  input(form,name,label,type="text",value="",required=true) {
    const wrap=el("label",label); const input=el("input");
    Object.assign(input,{name,type,value,required});
    wrap.append(input); form.append(wrap); return input;
  }
  memberSelect(form) {
    const wrap=el("label",this.t.assignee); const select=el("select"); select.name="assignee";
    const members=this._data.members.filter(m=>m.active && (this.parent || m.id===this._data.actor));
    for(const member of members) { const option=el("option",member.name);option.value=member.id;select.append(option); }
    wrap.append(select);form.append(wrap);return select;
  }
  async command(action,payload) {
    if (this._writing) return;
    const fingerprint=JSON.stringify([this._entry,action,payload]);
    if(this._pending?.fingerprint!==fingerprint) this._pending={fingerprint,id:crypto.randomUUID()};
    this._writing=true;
    for(const b of this.shadowRoot.querySelectorAll("button")) b.disabled=true;
    try {
      const result=await this._hass.callWS({type:"family_assistant/execute",entry_id:this._entry,
        action,payload,operation_id:this._pending.id});
      this._pending=null;this._actionError=result?.accepted===false?"wrong_answer":null;this._form=null;
    } catch(error) {this._actionError=error.code || this.t.failure;}
    finally {this._writing=false;await this.refresh();this.render();}
  }
  form() {
    const form=el("form");
    if(this._view==="shopping") {
      this.input(form,"name",this.t.name);
      const fields=el("div",null,"fields");form.append(fields);
      const amount=this.input(fields,"quantity",this.t.amount,"number","1");amount.min="0.001";amount.step="any";
      this.input(fields,"unit",this.t.unit,"text","",false).placeholder=this.t.unitPlaceholder;
    } else if(this._view==="tasks") {
      this.input(form,"title",this.t.title);this.memberSelect(form);
      this.input(form,"due_at",this.t.due,"datetime-local","",false);
    } else if(this._view==="alarms") {
      this.memberSelect(form);
      this.input(form,"name",this.t.name,"text","",false);
      this.input(form,"time",this.t.alarmTime,"time","07:30");
      this.input(form,"timezone",this.t.timezone,"text",this._hass?.config?.time_zone || Intl.DateTimeFormat().resolvedOptions().timeZone);
      const wrap=el("label",this.t.days),days=el("select");days.name="days";
      for(const [value,label] of [["weekdays",this.t.weekdays],["weekends",this.t.weekends],["everyday",this.t.everyday]]){const option=el("option",label);option.value=value;days.append(option);}wrap.append(days);form.append(wrap);
      const profiles=el("label",this.t.profile),select=el("select");select.name="profile";
      for(const value of ["gentle","strict"]){const option=el("option",this.t[value]);option.value=value;select.append(option);}profiles.append(select);form.append(profiles);
      const penalty=this.input(form,"penalty",this.t.alarmPenalty,"number","0");penalty.min="-10";penalty.max="0";penalty.step="1";
      form.append(el("div",this.t.alarmDeviceHint,"sub"));
    } else if(this._view==="court") {
      this.memberSelect(form);
      const points=this.input(form,"points",this.t.points,"number","1");points.min="-100";points.max="100";points.step="1";
      this.input(form,"reason",this.t.reason);
    }
    const submit=el("button",this.t.save,"primary");submit.type="submit";form.append(submit);
    form.addEventListener("submit",event=>{
      event.preventDefault();const values=Object.fromEntries(new FormData(form));
      if(this._view==="shopping") this.command("shopping.add",{...values,quantity:Number(values.quantity)});
      if(this._view==="tasks") { if(values.due_at)values.due_at=new Date(values.due_at).toISOString();else delete values.due_at;this.command("tasks.create",values); }
      if(this._view==="court") this.command("court.award",{member:values.assignee,points:Number(values.points),reason:values.reason});
      if(this._view==="alarms") this.command("alarms.save",{member:values.assignee,name:values.name,time:values.time,timezone:values.timezone,days:values.days==="weekdays"?[0,1,2,3,4]:values.days==="weekends"?[5,6]:[0,1,2,3,4,5,6],profile:values.profile,penalty:Number(values.penalty)});
    });return form;
  }
  render() {
    const root=this.shadowRoot;root.replaceChildren(el("style",STYLES));
    const card=el("ha-card");root.append(card);
    const header=el("header");header.append(el("div",this._data?.settings.name || "Family Assistant","eyebrow"),el("h2",this._config?.title || this.t[this._view]));card.append(header);
    const body=el("div",null,"body");card.append(body);
    if(this._actionError || this._error) {const language=this._config?.language || this._hass?.language?.split("-")[0],errors=ERRORS[language] || ERRORS.en;const notice=el("div",errors[this._actionError || this._error] || this.t.failure,"notice");notice.setAttribute("role","alert");body.append(notice);}
    if(!this._data) {
      body.append(el("div",this._entries?.length===0 ? this.t.noHousehold : this._entries?.length>1 ? this.t.choose : this.t.loading,"empty"));
      for(const entry of this._entries || []) body.append(this.button(entry.title,()=>{this._entry=entry.entry_id;this.refresh();}));
      if(this._error)body.append(this.button(this.t.retry,()=>this.refresh()));return;
    }
    if(this._view==="today") {this.renderToday(body);return;}
    if(this._view==="health") {this.renderHealth(body);return;}
    if(!this._data.settings.modules?.includes(this._view)){body.append(el("div",this.t.moduleOff,"empty"));return;}
    if(this._view==="alarms")this.renderAlarmRuns(body);
    const toolbar=el("div",null,"toolbar");toolbar.append(el("span",`${this._data[this._view]?.length || 0} ${this.t.units}`,"sub"));
    if(!["court","alarms"].includes(this._view) || this.parent) toolbar.append(this.button(this._form?this.t.back:this.t.add,()=>{this._form=!this._form;this.render();},true));
    body.append(toolbar);if(this._form)body.append(this.form());
    const items=this._data[this._view] || [];
    const list=el("ul",null,"list");body.append(list);
    for(const item of items.filter(i=>i.status!=="archived").slice().reverse())this.renderItem(list,item);
    if(!list.children.length)body.append(el("div",this.t.empty,"empty"));
  }
  renderToday(body) {
    const data=this._data, metrics=el("div",null,"metrics");body.append(metrics);
    const counts=[
      [this.t.tasks,data.tasks.filter(t=>!["completed","archived","cancelled"].includes(t.status)).length],
      [this.t.shopping,data.shopping.filter(i=>["approved","pending"].includes(i.status)).length],
      [this.t.awaiting,data.tasks.filter(t=>t.status==="submitted").length],
    ];
    for(const [label,value] of counts){const metric=el("div",null,"metric");metric.append(el("b",value),el("span",label));metrics.append(metric);}
    const list=el("ul",null,"list");body.append(list);
    for(const member of data.members.filter(m=>m.active && (this.parent || m.id===data.actor))){
      const item=el("li",null,"item row"),title=el("div",member.name,"grow");
      const balance=data.court.filter(r=>r.member===member.id && r.status==="active").reduce((s,r)=>s+r.points,0);
      item.append(title,el("strong",String(balance)));list.append(item);
    }
    this.renderAlarmRuns(body);
  }
  renderHealth(body) {
    if(!this.parent){body.append(el("div",this.t.parentsOnly,"empty"));return;}
    for(const [module,status] of Object.entries(this._data.health || {})){
      body.append(el("div",`${module} · ${this.t[status] || status}`,"item"));
    }
    const issues=this._data.delivery_issues || [];
    if(!issues.length)body.append(el("div",this.t.noDeliveryIssues,"empty"));
    for(const issue of issues){
      const item=el("div",null,"item"),actions=el("div",null,"actions");
      item.append(el("strong",`${issue.key} · ${this.t[issue.state] || issue.state}`));
      item.append(el("div",new Date(issue.created_at).toLocaleString(this._hass?.language),"sub"));
      item.append(actions);body.append(item);
      const review=(retry)=>{
        const form=el("form");form.append(el("div",retry?this.t.retryWarning:this.t.resolveWarning,"notice"));
        this.input(form,"reason",this.t.reason);
        if(retry){const wrap=el("label",this.t.retryConsent),checkbox=el("input");checkbox.type="checkbox";checkbox.name="confirmed";checkbox.required=true;wrap.append(checkbox);form.append(wrap);}
        const save=el("button",this.t.save,"primary");save.type="submit";form.append(save);
        form.addEventListener("submit",e=>{e.preventDefault();const values=Object.fromEntries(new FormData(form));this.command(retry?"notifications.retry":"notifications.resolve",{id:issue.id,reason:values.reason,...(retry?{confirmed:values.confirmed==="on"}:{})});});
        actions.replaceChildren(form);
      };
      if(["uncertain","failed"].includes(issue.state)){
        actions.append(this.button(this.t.retryDelivery,()=>review(true)),this.button(this.t.resolveDelivery,()=>review(false)));
      }else item.append(el("div",this.t.channelHint,"sub"));
    }
  }
  renderAlarmRuns(body) {
    for(const run of this._data.alarm_runs || []){
      if(!["first","waiting_second","second"].includes(run.stage))continue;
      const item=el("div",null,"item"),member=this._data.members.find(m=>m.id===run.member);
      item.append(el("strong",`${member?.name || ""} · ${this.t[run.stage]}`));
      if(run.test)item.append(el("div",this.t.testAlarm,"badge"));
      item.append(el("div",run.siren_desired?this.t.soundRequested:this.t.soundPaused,"sub"));
      if(run.challenge && run.member===this._data.actor){
        item.append(el("h3",run.challenge.question));
        const choices=el("div",null,"actions");
        for(const answer of run.challenge.choices)choices.append(this.button(String(answer),()=>this.command("alarms.answer",{id:run.id,nonce:run.challenge.nonce,answer}),true));
        item.append(choices);
      }
      if(this.parent)item.append(this.button(this.t.stopAlarm,()=>{
        const form=el("form");this.input(form,"reason",this.t.reason);
        const submit=el("button",this.t.stopAlarm);submit.type="submit";form.append(submit);
        form.addEventListener("submit",e=>{e.preventDefault();this.command("alarms.cancel",{id:run.id,...Object.fromEntries(new FormData(form))});});item.append(form);
      }));
      body.append(item);
    }
  }
  renderItem(list,item) {
    const row=el("li",null,"item");list.append(row);
    row.append(el("strong",item.name || item.title || item.reason || this.t[item.reason_key] || (this._view==="alarms"?item.time:"")));
    const meta=el("div",null,"sub");
    const member=this._data.members.find(m=>m.id===(item.assignee || item.member));
    const detail=this._view==="shopping"?`${item.purchased} / ${item.quantity} ${item.unit}`:
      this._view==="court"?`${member?.name || ""} · ${item.points>0?"+":""}${item.points}`:
      this._view==="alarms"?`${member?.name || ""} · ${item.time} · ${item.timezone}`:member?.name || "";
    meta.append(el("span",detail),el("span",this._view==="alarms"?this.t[item.enabled?"enabled":"disabled"]:this.t[item.status] || item.status,"badge"));
    if(this._view==="alarms")meta.append(el("div",item.days.map(day=>this.t.dayNames[day]).join(", ")));
    if(item.due_at)meta.append(el("div",new Date(item.due_at).toLocaleString(this._hass?.language)));
    row.append(meta);const actions=el("div",null,"actions");row.append(actions);
    const command=(action,extra={})=>this.command(action,{id:item.id,revision:item.revision,...extra});
    if(this._view==="alarms" && this.parent){
      actions.append(this.button(item.enabled?this.t.disable:this.t.enable,()=>command("alarms.enable",{enabled:!item.enabled})));
      actions.append(this.button(this.t.testAlarm,()=>{
        const confirm=el("div",this.t.testAlarmWarning,"notice");
        confirm.append(this.button(this.t.startTest,()=>this.command("alarms.test",{id:item.id}),true));actions.replaceChildren(confirm);
      }));
    }
    if(this._view==="shopping"){
      if(item.status==="approved" && this._data.role!=="guest")actions.append(this.button(this.t.buy,()=>command("shopping.purchase")));
      if(item.status==="pending" && this.parent)actions.append(this.button(this.t.approve,()=>command("shopping.approve")));
    }
    if(this._view==="tasks" && !["completed","cancelled","archived"].includes(item.status)){
      if(this.parent) actions.append(this.button(this.t.complete,()=>command("tasks.complete")));
      else if(item.assignee===this._data.actor && item.status!=="submitted") actions.append(this.button(this.t.report,()=>{
        const form=el("form");this.input(form,"report",this.t.reportLabel);const send=el("button",this.t.save,"primary");send.type="submit";form.append(send);
        form.addEventListener("submit",event=>{event.preventDefault();command("tasks.submit",Object.fromEntries(new FormData(form)));});actions.replaceChildren(form);
      }));
    }
    if(this._view==="court" && this.parent && item.status==="active")actions.append(this.button(this.t.reverse,()=>{
      const form=el("form");this.input(form,"reason",this.t.reason);const submit=el("button",this.t.save,"primary");submit.type="submit";form.append(submit);
      form.addEventListener("submit",event=>{event.preventDefault();command("court.reverse",Object.fromEntries(new FormData(form)));});actions.replaceChildren(form);
    }));
  }
}

class FamilyEditor extends HTMLElement {
  constructor(){super();this.attachShadow({mode:"open"});}
  setConfig(config){this._config={...config};this.render();}
  set hass(hass){
    const identity=hass.connection || hass;
    this._hass=hass;
    if(identity!==this._identity){this._identity=identity;this._entries=null;this.loadHouseholds(identity);}
    if(!this.shadowRoot.activeElement)this.render();
  }
  async loadHouseholds(identity){
    try{
      const entries=await this._hass.callWS({type:"family_assistant/households"});
      if(identity!==this._identity)return;
      this._entries=entries;this._error=false;this.render();
    }catch{
      if(identity!==this._identity)return;
      this._error=true;this.render();
    }
  }
  render(){
    const t=COPY[this._hass?.language?.split("-")[0]] || COPY.en;this.shadowRoot.replaceChildren(el("style",STYLES));
    const form=el("div",null,"editor");this.shadowRoot.append(form);
    if(this._error){const notice=el("div",t.failure,"notice");notice.setAttribute("role","alert");form.append(notice);}
    for(const [name,label] of [["entry_id",t.entry],["title",t.name],["view",t.view]]){
      const wrap=el("label",label),input=el(name!=="title"?"select":"input");input.name=name;
      if(name==="entry_id"){
        const empty=el("option",this._entries?(this._entries.length?t.choose:t.noHousehold):t.loading);empty.value="";input.append(empty);
        for(const entry of this._entries || []){const option=el("option",entry.title);option.value=entry.entry_id;input.append(option);}
        input.disabled=!this._entries?.length;
      }
      if(name==="view")for(const view of ["today","shopping","tasks","court","alarms","health"]){const option=el("option",t[view]);option.value=view;input.append(option);}
      const defaultView={"custom:family-alarms-card":"alarms","custom:family-shopping-card":"shopping","custom:family-tasks-card":"tasks","custom:family-court-card":"court","custom:family-health-card":"health"}[this._config?.type] || "today";
      input.value=this._config?.[name] || (name==="view"?defaultView:"");wrap.append(input);form.append(wrap);
      input.addEventListener("change",()=>{this._config={...this._config,[name]:input.value};this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:this._config},bubbles:true,composed:true}));});
    }
  }
}
customElements.define("family-assistant-card-editor",FamilyEditor);
for(const [type,view] of [["family-assistant-card","today"],["family-shopping-card","shopping"],["family-tasks-card","tasks"],["family-court-card","court"],["family-alarms-card","alarms"],["family-health-card","health"]]){
  class Card extends FamilyCard {static defaultView=view;}
  customElements.define(type,Card);
  window.customCards=window.customCards || [];
  window.customCards.push({type,name:`Family Assistant · ${COPY.en[view]}`,description:COPY.en[view],preview:true});
}
export {COPY};
