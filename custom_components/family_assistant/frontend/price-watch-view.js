/* Existing URL-watch consent only. Purchase prices remain in the shopping card. */
export const PRICE_WATCH_COPY = {
  en: {title:"Product URL watches",hint:"Separate from purchase history. These saved URLs are fetched externally every 30 minutes while this module is enabled. Public HTTPS on port 443 only; pages over 512 KiB or requiring credentials are not supported.",review_required:"Review required — a parent must check the URL and explicitly allow fetching again. Existing history is retained.",ready:"Fetching allowed",url:"Product URL (public HTTPS)",consent:"I have reviewed this URL and allow periodic external fetching and the saved parent notification rules.",save:"Save URL and allow fetching",retry:"Retry the same approval",invalid:"Enter a public HTTPS URL without credentials, fragments or a custom port.",empty:"No saved product URL watches. Purchase price history is available in Shopping.",parent:"Ask a parent to review this saved watch.",response_too_large:"Page exceeds the 512 KiB limit",invalid_url:"URL is not supported: public HTTPS on port 443 is required",timeout:"The request timed out",unsupported_response:"Unsupported page format or compression",unavailable:"The page is unavailable",invalid_response:"No valid price or availability was found"},
  ru: {title:"Наблюдение за URL товаров",hint:"Отдельно от истории покупок. Пока модуль включён, сохранённые URL запрашиваются во внешней сети каждые 30 минут. Только публичный HTTPS на порту 443; страницы больше 512 КиБ или с авторизацией не поддерживаются.",review_required:"Нужна проверка — родитель должен проверить URL и явно разрешить запросы заново. История сохранена.",ready:"Запросы разрешены",url:"URL товара (публичный HTTPS)",consent:"Я проверил(а) этот URL и разрешаю периодические внешние запросы и сохранённые правила уведомления родителей.",save:"Сохранить URL и разрешить запросы",retry:"Повторить то же разрешение",invalid:"Введите публичный HTTPS URL без пароля, фрагмента и нестандартного порта.",empty:"Сохранённых URL товаров нет. История цен покупок доступна в разделе «Покупки».",parent:"Попросите родителя проверить это наблюдение.",response_too_large:"Страница превышает лимит 512 КиБ",invalid_url:"URL не поддерживается: нужен публичный HTTPS на порту 443",timeout:"Время запроса истекло",unsupported_response:"Формат или сжатие страницы не поддерживается",unavailable:"Страница недоступна",invalid_response:"Корректная цена или наличие не найдены"},
  uk: {title:"Спостереження за URL товарів",hint:"Окремо від історії покупок. Поки модуль увімкнений, збережені URL запитуються в зовнішній мережі кожні 30 хвилин. Лише публічний HTTPS на порту 443; сторінки понад 512 КіБ або з авторизацією не підтримуються.",review_required:"Потрібна перевірка — батьки мають перевірити URL і явно дозволити запити знову. Історію збережено.",ready:"Запити дозволені",url:"URL товару (публічний HTTPS)",consent:"Я перевірив(-ла) цей URL і дозволяю періодичні зовнішні запити та збережені правила сповіщення батьків.",save:"Зберегти URL і дозволити запити",retry:"Повторити той самий дозвіл",invalid:"Введіть публічний HTTPS URL без пароля, фрагмента та нестандартного порту.",empty:"Збережених URL товарів немає. Історія цін покупок доступна в розділі «Покупки».",parent:"Попросіть батьків перевірити це спостереження.",response_too_large:"Сторінка перевищує ліміт 512 КіБ",invalid_url:"URL не підтримується: потрібен публічний HTTPS на порту 443",timeout:"Час запиту вичерпано",unsupported_response:"Формат або стиснення сторінки не підтримується",unavailable:"Сторінка недоступна",invalid_response:"Коректну ціну або наявність не знайдено"},
};
const node=(tag,text)=>{const result=document.createElement(tag);if(text!==undefined)result.textContent=String(text);return result;};
export function renderPriceWatchReview(panel) {
  const copy=PRICE_WATCH_COPY[panel.lang]||PRICE_WATCH_COPY.en,section=panel.section(copy.title);
  section.dataset.priceWatchReview="true";section.append(node("p",copy.hint));
  const view=panel._data?.view,records=view?.price_watches||[];
  const allowed=["owner","parent"].includes(view?.role)&&!view?.read_only&&view?.settings?.modules?.includes("price_watch");
  if(!records.length)section.append(node("p",copy.empty));
  for(const record of records){
    const row=node("section"),status=node("p",copy[record.policy_status]||copy.review_required);
    row.dataset.priceWatch=record.id;row.style.overflowWrap="anywhere";row.append(node("h4",record.name),status);
    if(record.last_error)row.append(node("p",copy[record.last_error]||copy.unavailable));
    if(!allowed){row.append(node("p",copy.parent));section.append(row);continue;}
    const pending=panel._pending?.action==="price_watch.edit"&&panel._pending.payload.id===record.id?panel._pending:null;
    const frozen=!!panel._pending||panel._writing,form=node("form"),label=node("label",copy.url),url=node("input");
    form.className="panel-stack";label.className="form-group";url.className="form-control";
    url.type="url";url.name="price_watch_url";url.required=true;url.maxLength=2000;url.setAttribute("aria-label",copy.url);
    url.value=pending?.payload.url??record.url;url.disabled=frozen;label.append(url);form.append(label);
    const consentLabel=node("label",copy.consent),consent=node("input");consent.type="checkbox";consent.name="price_watch_consent";consent.required=true;consent.checked=!!pending;consent.disabled=frozen;consentLabel.prepend(consent);form.append(consentLabel);
    for(const control of [url,consent])control.addEventListener("input",()=>{if(!control.disabled)panel._dirty=true;});
    const error=node("p");error.setAttribute("role","alert");form.append(error);
    const save=node("button",pending?copy.retry:copy.save);save.type="submit";save.className="btn btn-primary";save.disabled=panel._writing||!!panel._pending&&!pending;form.append(save);
    const generation=panel._generation,entry=panel._entry,actor=view.actor,actorRevision=view.members?.find(member=>member.id===actor)?.revision;
    form.addEventListener("submit",event=>{
      event.preventDefault();
      const current=panel._data?.view,selected=current?.price_watches?.find(item=>item.id===record.id);
      if(!form.isConnected||!panel.isConnected||panel._generation!==generation||panel._entry!==entry||current?.actor!==actor||current.members?.find(member=>member.id===actor)?.revision!==actorRevision||selected?.revision!==record.revision||panel._writing)return;
      const payload=pending?.payload||{id:record.id,revision:record.revision,actor_revision:actorRevision,url:url.value.trim()};
      if(!pending){
        try{const parsed=new URL(payload.url);if(!consent.checked||parsed.protocol!=="https:"||parsed.username||parsed.password||parsed.hash||(parsed.port&&parsed.port!=="443")||payload.url.includes("\\")||payload.url.length>2000)throw Error();}
        catch{error.textContent=copy.invalid;return;}
      }
      void panel.command("price_watch.edit",payload);
    });
    row.append(form);section.append(row);
  }
  return section;
}
