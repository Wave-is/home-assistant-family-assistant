/* Local search over public labels; no family identities or runtime data. */
import {PANEL_COPY, PANEL_MODULES, moduleCopy} from "./panel-copy.js";
const synonyms = {
  court:["штраф", "минус", "баллы", "суд", "поощрение", "штрафи", "бали", "penalty", "points", "reward"],
  school:["уроки", "расписание", "рюкзак", "розклад", "нагадування", "school", "homework", "reminder"],
  shopping:["покупки", "магазин", "shopping", "groceries"], pantry:["еда", "продукты", "сроки", "їжа", "запаси", "expiry", "stock"],
  tasks:["задачи", "дела", "дежурство", "завдання", "tasks", "chores"],
  telegram:["телеграм", "бот", "токен", "чат", "группа", "telegram", "invite", "bot", "token"],
  conversation:["ии", "модель", "агент", "llm", "ollama", "model", "agent", "пошук", "поиск", "search"],
  members:["семья", "участник", "роль", "имя", "родина", "учасник", "family", "member", "name", "role"],
  alarms:["будильник", "сирена", "подъём", "підйом", "siren", "wake"],
  presence:["дома", "присутствие", "геолокация", "вдома", "presence", "tracker"],
};
export function settingsCatalog(lang = "en") {
  const t = PANEL_COPY[lang] || PANEL_COPY.en;
  return [...PANEL_MODULES.map(([id]) => ({...moduleCopy(id, lang), section:"modules", moduleId:id, keywords:synonyms[id] || []})),
    {id:"members",title:t.members,description:t.accounts,section:"members",keywords:synonyms.members},
    {id:"telegram",title:t.telegram,description:t.accounts,section:"connections",keywords:synonyms.telegram},
    {id:"family",title:t.familyName,description:t.timezone,section:"advanced",keywords:["язык","мова","language","timezone","часовой"]}];
}
export const SETTINGS_CATALOG = settingsCatalog("en");
export function searchSettings(query, lang = "en") {
  const words = String(query || "").trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  return settingsCatalog(lang).filter(item => {
    const source = [item.title, item.description, ...item.keywords].join(" ").toLocaleLowerCase();
    return words.every(word => source.includes(word));
  });
}
