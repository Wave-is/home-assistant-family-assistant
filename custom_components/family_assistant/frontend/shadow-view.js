/* Owner-only server projection of a frozen migration copy. No command controls. */
import {ERRORS} from "./errors.js";

export const SHADOW_COPY = Object.freeze({
  en: {title:"Migration review", retained:"Full original history stays in the private migration archive.", limit:"First 20 visible records are shown. The total is in the section heading."},
  ru: {title:"Проверка переноса", retained:"Полная исходная история сохранена в приватном архиве переноса.", limit:"Показаны первые 20 доступных записей. Общее число указано в заголовке раздела."},
  uk: {title:"Перевірка перенесення", retained:"Повну початкову історію збережено у приватному архіві перенесення.", limit:"Показано перші 20 доступних записів. Загальну кількість зазначено в заголовку розділу."},
});

function node(tag, text, className) {
  const element=document.createElement(tag);
  if(text!==undefined)element.textContent=String(text);
  if(className)element.className=className;
  return element;
}

export function renderShadow(card,body) {
  const language=card._config?.language || card._hass?.language?.split("-")[0];
  const copy=SHADOW_COPY[language] || SHADOW_COPY.en;
  const section=node("section",undefined,"migration-shadow");
  section.append(node("h3",copy.title));
  const notice=node("p",(ERRORS[language] || ERRORS.en).migration_shadow_read_only,"notice");
  notice.setAttribute("role","status");section.append(notice,node("p",copy.retained));
  for(const key of ["tasks","shopping","court","alarms"]) {
    const rows=Array.isArray(card._data?.[key])?card._data[key]:[];
    const details=node("details");details.append(node("summary",`${card.t[key]} · ${rows.length}`));
    const list=node("ul");
    for(const row of rows.slice(0,20)) {
      const title=row.title || row.name || row.reason || row.time || "";
      list.append(node("li",`${row.id || ""} · ${title}`));
    }
    details.append(list);if(rows.length>20)details.append(node("p",copy.limit));
    section.append(details);
  }
  body.append(section);
}
