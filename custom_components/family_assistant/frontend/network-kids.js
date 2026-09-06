/* All content is textContent. This panel submits typed plans, never RouterOS code. */
import {ERRORS} from "./errors.js";

export const KID_COPY = {
  en: {title:"Children's internet",adopt:"Adopt an existing profile",profile:"RouterOS profile",member:"Child",verify:"I verified that every listed device belongs to this child and is safe to control.",adoptSave:"Confirm profile ownership",local:"This records ownership locally; no router settings change yet.",devices:"Devices",preview:"Review plan",apply:"Apply reviewed control",cancel:"Cancel",pause:"Pause all profile devices",resume:"Return to normal schedule",grant:"Allow temporarily",timed_pause:"Pause temporarily",schedule:"Change allowed hours",rate:"Set rate limit",minutes:"Minutes",days:"Days",weekdays:"Weekdays",weekends:"Weekends",all:"Every day",window:"Allowed window, e.g. 08:00-22:00",speed:"Rate, e.g. 5M (blank removes limit)",stale:"No verified profile. Refresh or review ownership.",normal:"Normal schedule",paused:"Paused",disabled:"Restrictions disabled",timer:"Temporary mode needs verified router expiry/startup guards. Reboot ends the exception early. Previous mode will be restored.",warning:"Router configuration is not proof of end-to-end filtering. Check IPv6, FastTrack and downstream NAT.",until:"Until",empty:"No adopted profiles yet.",writeOff:"Kid Control writes are disabled in connection settings.",observed:"Last observation",delegation:"Allow this adult to manage Kid Control",delegationSave:"Save permission",expired:"Temporary exception ended; previous mode verified",restored:"Previous profile restored"},
  ru: {title:"Интернет детей",adopt:"Передать существующий профиль",profile:"Профиль RouterOS",member:"Ребёнок",verify:"Я проверил: все перечисленные устройства принадлежат этому ребёнку, ими безопасно управлять.",adoptSave:"Подтвердить принадлежность профиля",local:"Принадлежность сохраняется локально; настройки роутера пока не меняются.",devices:"Устройства",preview:"Проверить план",apply:"Применить проверенное управление",cancel:"Отмена",pause:"Пауза всех устройств профиля",resume:"Вернуть обычное расписание",grant:"Разрешить временно",timed_pause:"Приостановить временно",schedule:"Изменить часы доступа",rate:"Ограничить скорость",minutes:"Минуты",days:"Дни",weekdays:"Будни",weekends:"Выходные",all:"Каждый день",window:"Интервал доступа, например 08:00-22:00",speed:"Скорость, например 5M (пусто — без лимита)",stale:"Нет проверенного профиля. Обновите данные или проверьте принадлежность.",normal:"Обычное расписание",paused:"Пауза",disabled:"Ограничения выключены",timer:"Временный режим требует проверенных таймеров окончания и запуска на роутере. Ребут завершит исключение досрочно. Затем вернётся прежний режим.",warning:"Настройки роутера не доказывают сквозную блокировку. Проверьте IPv6, FastTrack и устройства за другим NAT.",until:"До",empty:"Пока нет переданных профилей.",writeOff:"Запись Kid Control выключена в параметрах подключения.",observed:"Последнее наблюдение",delegation:"Разрешить этому взрослому управлять Kid Control",delegationSave:"Сохранить право",expired:"Исключение завершено; прежний режим проверен",restored:"Прежний профиль восстановлен"},
  uk: {title:"Інтернет дітей",adopt:"Передати наявний профіль",profile:"Профіль RouterOS",member:"Дитина",verify:"Я перевірив: усі перелічені пристрої належать цій дитині, ними безпечно керувати.",adoptSave:"Підтвердити належність профілю",local:"Належність зберігається локально; налаштування роутера поки не змінюються.",devices:"Пристрої",preview:"Перевірити план",apply:"Застосувати перевірене керування",cancel:"Скасувати",pause:"Пауза всіх пристроїв профілю",resume:"Повернути звичайний розклад",grant:"Дозволити тимчасово",timed_pause:"Призупинити тимчасово",schedule:"Змінити години доступу",rate:"Обмежити швидкість",minutes:"Хвилини",days:"Дні",weekdays:"Будні",weekends:"Вихідні",all:"Щодня",window:"Інтервал доступу, наприклад 08:00-22:00",speed:"Швидкість, наприклад 5M (порожньо — без ліміту)",stale:"Немає перевіреного профілю. Оновіть дані або перевірте належність.",normal:"Звичайний розклад",paused:"Пауза",disabled:"Обмеження вимкнено",timer:"Тимчасовий режим потребує перевірених таймерів завершення та запуску на роутері. Перезавантаження завершить виняток достроково. Потім повернеться попередній режим.",warning:"Налаштування роутера не доводять наскрізне блокування. Перевірте IPv6, FastTrack і пристрої за іншим NAT.",until:"До",empty:"Поки немає переданих профілів.",writeOff:"Запис Kid Control вимкнено в параметрах підключення.",observed:"Останнє спостереження",delegation:"Дозволити цьому дорослому керувати Kid Control",delegationSave:"Зберегти право",expired:"Виняток завершено; попередній режим перевірено",restored:"Попередній профіль відновлено"}
};

export const KID_FIELDS = {
  en:{restrictions:"Restrictions",forcedPause:"Forced pause",enabled:"Enabled",off:"Disabled",yes:"Yes",no:"No",scheduleTitle:"Allowed hours",noAccess:"No access",unlimited:"Unlimited rate",noLimit:"No limit",setting:"Setting"},
  ru:{restrictions:"Ограничения",forcedPause:"Принудительная пауза",enabled:"Включены",off:"Выключены",yes:"Да",no:"Нет",scheduleTitle:"Расписание доступа",noAccess:"Нет доступа",unlimited:"Без лимита скорости",noLimit:"Без лимита",setting:"Настройка"},
  uk:{restrictions:"Обмеження",forcedPause:"Примусова пауза",enabled:"Увімкнено",off:"Вимкнено",yes:"Так",no:"Ні",scheduleTitle:"Розклад доступу",noAccess:"Немає доступу",unlimited:"Без обмеження швидкості",noLimit:"Без ліміту",setting:"Налаштування"}
};

export function kidDiff(key,change,language,dayNames){
  const t=KID_FIELDS[language] || KID_FIELDS.en,copy=KID_COPY[language] || KID_COPY.en;
  const days=["mon","tue","wed","thu","fri","sat","sun"],day=days.indexOf(key.replace(/^tur-/,""));
  const label=key==="disabled"?t.restrictions:key==="paused"?t.forcedPause:key==="rate-limit"?copy.rate:day>=0?`${dayNames[day]}${key.startsWith("tur-")?" · "+t.unlimited:""}`:t.setting;
  const value=v=>key==="disabled"?(v==="true"?t.off:t.enabled):key==="paused"?(v==="true"?t.yes:t.no):v || (day>=0?t.noAccess:t.noLimit);
  return `${label}: ${value(change.before)} → ${value(change.after)}`;
}

function el(tag,text,cls){const node=document.createElement(tag);if(text!=null)node.textContent=text;if(cls)node.className=cls;return node;}
function select(parent,name,label,options){const wrapper=el("label",label),node=el("select");node.name=name;node.setAttribute("aria-label",label);for(const [value,text] of options){const option=el("option",text);option.value=value;node.append(option);}wrapper.append(node);parent.append(wrapper);return node;}
function submit(form,label){const button=el("button",label,"primary");button.type="submit";form.append(button);return button;}
function consent(form,label,checked=false){const wrapper=el("label",null,"check"),box=el("input");box.type="checkbox";box.name="confirmed";box.checked=checked;wrapper.append(box,el("span",label));form.append(wrapper);return box;}

export function renderKids(card,body){
  const data=card._data.kid_control;if(!data)return;
  const lang=card._config?.language || card._hass.language?.split("-")[0],t=KID_COPY[lang] || KID_COPY.en,errors=ERRORS[lang] || ERRORS.en;
  const fieldsCopy=KID_FIELDS[lang] || KID_FIELDS.en;
  const root=el("section");root.append(el("h2",t.title));body.append(root);
  root.append(el("p",t.warning,"sub"));
  if(data.observed_at)root.append(el("p",t.observed+": "+new Date(data.observed_at).toLocaleString(lang),"sub"));
  if(data.can_manage && !data.writable)root.append(el("p",t.writeOff,"notice"));
  for(const p of data.plans.slice().reverse()){
    const section=el("section",null,"item"),member=card._data.members.find(m=>m.id===p.member)?.name || "";
    const state=p.status==="expired"?t.expired:p.status==="rolled_back"?t.restored:card.t["networkState_"+p.status] || p.status;
    section.append(el("strong",`${p.id} · ${member} · ${state}`),el("p",t[p.mode]));
    for(const [key,value] of Object.entries(p.diff || {}))section.append(el("p",kidDiff(key,value,lang,card.t.dayNames),"sub"));
    if(p.until)section.append(el("p",`${t.until}: ${new Date(p.until).toLocaleString(lang)}`),el("p",t.timer,"sub"));
    if(p.progress?.failure)section.append(el("p",errors[p.progress.failure] || card.t.failure,"notice"));
    if(p.progress?.error)section.append(el("p",errors[p.progress.error] || card.t.failure,"notice"));
    if(p.status==="preview" && data.can_manage && p.actor===card._data.actor){
      if(Date.parse(p.expires_at)<=Date.now())section.append(el("p",card.t.networkExpired,"notice"));
      else if(data.writable)section.append(card.button(t.apply,()=>card.command("mikrotik.kid_apply",{id:p.id,confirmed:true}),true));
      section.append(card.button(t.cancel,()=>card.command("mikrotik.kid_cancel",{id:p.id})));
    }
    root.append(section);
  }
  for(const p of data.profiles){
    const section=el("section",null,"item"),member=card._data.members.find(m=>m.id===p.member)?.name || "";
    section.append(el("strong",`${member} · ${p.name}`),el("p",t.devices+": "+p.device_names.join(", "),"sub"));
    if(!p.observed){section.append(el("p",t.stale,"notice"));root.append(section);continue;}
    section.append(el("p",p.observed.disabled==="true"?t.disabled:p.observed.paused==="true"?t.paused:t.normal));
    const schedule=el("details");schedule.append(el("summary",fieldsCopy.scheduleTitle));
    ["mon","tue","wed","thu","fri","sat","sun"].forEach((day,index)=>schedule.append(el("p",`${card.t.dayNames[index]}: ${p.observed[day] || "—"}`,"sub")));section.append(schedule);
    if(data.can_manage){
      const form=el("form"),mode=select(form,"mode",t.title,["pause","resume","grant","timed_pause","schedule","rate"].map(k=>[k,t[k]]));
      const dynamic=el("div");form.append(dynamic);
      function fields(){dynamic.replaceChildren();if(["grant","timed_pause"].includes(mode.value)){const minutes=card.input(dynamic,"minutes",t.minutes,"number","30");minutes.min="1";minutes.max="1440";dynamic.append(el("p",t.timer,"sub"));}if(mode.value==="schedule"){select(dynamic,"days",t.days,["weekdays","weekends","all"].map(k=>[k,t[k]]));card.input(dynamic,"window",t.window,"text","08:00-22:00",false);}if(mode.value==="rate")card.input(dynamic,"rate_limit",t.speed,"text","5M",false);}
      fields();mode.addEventListener("change",fields);submit(form,t.preview);
      form.addEventListener("submit",event=>{event.preventDefault();const v=Object.fromEntries(new FormData(form)),payload={member:p.member,mode:v.mode};if(v.minutes)payload.minutes=Number(v.minutes);if(v.mode==="schedule"){const days=["mon","tue","wed","thu","fri","sat","sun"],chosen=v.days==="weekdays"?days.slice(0,5):v.days==="weekends"?days.slice(5):days;payload.schedule=Object.fromEntries(chosen.map(d=>[d,v.window]));}if(v.mode==="rate")payload.rate_limit=v.rate_limit;card.command("mikrotik.kid_plan",payload);});section.append(form);
    }
    root.append(section);
  }
  if(!data.profiles.length)root.append(el("p",t.empty,"empty"));
  if(card._data.role==="owner" && data.candidates?.length){
    const section=el("details");section.append(el("summary",t.adopt));const form=el("form");
    const memberSelect=select(form,"member",t.member,card._data.members.filter(m=>m.active && m.role==="child").map(m=>[m.id,m.name]));
    const profile=select(form,"profile_id",t.profile,data.candidates.map(p=>[p.id,p.name]));
    const info=el("p",null,"sub");form.append(info);const update=()=>{const selected=data.candidates.find(p=>p.id===profile.value);info.textContent=(selected?.devices || []).map(d=>`${d.name} · ${d.mac}`).join("\n");info.style.whiteSpace="pre-line";};update();profile.addEventListener("change",update);
    const verified=consent(form,t.verify);verified.required=true;profile.addEventListener("change",()=>{verified.checked=false;});memberSelect.addEventListener("change",()=>{verified.checked=false;});form.append(el("p",t.local,"sub"));submit(form,t.adoptSave);
    form.addEventListener("submit",event=>{event.preventDefault();const v=Object.fromEntries(new FormData(form)),selected=data.candidates.find(p=>p.id===v.profile_id);card.command("mikrotik.kid_adopt",{member:v.member,profile_id:v.profile_id,devices:selected.devices.map(d=>d.id),confirmed:v.confirmed==="on"});});section.append(form);root.append(section);
  }
  if(card._data.role==="owner")for(const adult of card._data.members.filter(m=>m.active && m.role==="adult")){
    const form=el("form");form.append(el("strong",adult.name));const check=consent(form,t.delegation,!!data.delegations?.[adult.id]);submit(form,t.delegationSave);form.addEventListener("submit",event=>{event.preventDefault();card.command("mikrotik.kid_permission",{member:adult.id,enabled:check.checked});});root.append(form);
  }
}
