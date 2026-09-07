/* Read-only textual history. Server projection is authoritative. */
export const REPORT_HISTORY_COPY = {
  en: {title:"Previous reports", more:"Show earlier reports", empty:"Submitted without text", report:"Report", review:"Review note", submitted:"Submitted", completion:"Completion note", cancellation:"Cancellation note", archive:"Archive note"},
  ru: {title:"Предыдущие отчёты", more:"Показать более ранние отчёты", empty:"Сдано без текста", report:"Отчёт", review:"Замечания к отчёту", submitted:"Сдан", completion:"Комментарий к завершению", cancellation:"Причина отмены", archive:"Комментарий к архивированию"},
  uk: {title:"Попередні звіти", more:"Показати давніші звіти", empty:"Здано без тексту", report:"Звіт", review:"Зауваження до звіту", submitted:"Здано", completion:"Коментар до завершення", cancellation:"Причина скасування", archive:"Коментар до архівування"},
};
const el = (tag,text) => { const node=document.createElement(tag); if(text!==undefined)node.textContent=text; return node; };

export function renderReportHistory(card,item,isCurrent) {
  if (!isCurrent() || card._error) return null;
  const copy=REPORT_HISTORY_COPY[card._config?.language || card._hass?.language?.split("-")[0]] || REPORT_HISTORY_COPY.en;
  const section=el("section"); section.dataset.reportHistory=item.id;
  if(item.report_type==="text" && item.report==="")section.append(el("p",`${copy.report}: ${copy.empty}`));
  for (const [field,label] of [["completion_note","completion"],["cancellation_note","cancellation"],["archive_note","archive"]])
    if(typeof item[field]==="string" && item[field])section.append(el("p",`${copy[label]}: ${item[field]}`));
  if(!card.parent) return section.childNodes.length ? section : null;
  const reports=(Array.isArray(item.previous_reports)?item.previous_reports:[]).filter(row=>typeof row?.report==="string");
  if(!reports.length)return section.childNodes.length ? section : null;
  const details=el("details"), list=el("ol"), more=el("button",copy.more);
  details.append(el("summary",`${copy.title} · ${reports.length}`),list,more);section.append(details);
  more.type="button";
  const actor=card._data?.actor, epoch=card._data?.actor_revision, generation=card._generation, entry=card._config?.entry_id;
  let shown=0;
  const append=()=>{
    if(!card.parent || card._error || !isCurrent() || card._data?.actor!==actor || card._data?.actor_revision!==epoch || card._generation!==generation || card._config?.entry_id!==entry){section.remove();return;}
    const end=Math.min(shown+20,reports.length);
    for(let index=shown;index<end;index++){
      const report=reports[reports.length-1-index], row=el("li");
      row.append(el("p",`${copy.report}: ${report.report || copy.empty}`));
      if(typeof report.review_note==="string" && report.review_note)row.append(el("p",`${copy.review}: ${report.review_note}`));
      if(typeof report.submitted_at==="string"){
        const date=new Date(report.submitted_at);
        if(Number.isFinite(date.getTime())){
          let formatted=report.submitted_at;
          try {formatted=new Intl.DateTimeFormat(card._config?.language || card._hass?.language || "en",{dateStyle:"medium",timeStyle:"short",timeZone:card._data?.settings?.timezone || "UTC"}).format(date);} catch {}
          row.append(el("small",`${copy.submitted}: ${formatted}`));
        }
      }
      list.append(row);
    }
    shown=end;more.hidden=shown===reports.length;
  };
  more.addEventListener("click",append);append();
  return section;
}
