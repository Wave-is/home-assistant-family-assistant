/* Explicit private projection; all course content is plain text, not generated HTML. */
const copy = {
  en:{assign:"Assign course",grade:"Grade",language:"Lesson language",child:"Child",archive:"Archive",answer:"Answer",check:"Check",mastered:"Mastered",accuracy:"Accuracy",review:"Review scheduled",empty:"No assignments",correct:"Correct!",again:"Try another example",video:"Find a video on YouTube",off:"Academy is disabled or unavailable"},
  uk:{assign:"Призначити курс",grade:"Клас",language:"Мова уроку",child:"Дитина",archive:"Архівувати",answer:"Відповідь",check:"Перевірити",mastered:"Засвоєно",accuracy:"Точність",review:"Повторення заплановано",empty:"Немає призначень",correct:"Правильно!",again:"Спробуй ще один приклад",video:"Знайти відео на YouTube",off:"Academy вимкнено або недоступна"},
  ru:{assign:"Назначить курс",grade:"Класс",language:"Язык урока",child:"Ребёнок",archive:"Архивировать",answer:"Ответ",check:"Проверить",mastered:"Освоено",accuracy:"Точность",review:"Повторение запланировано",empty:"Нет назначений",correct:"Правильно!",again:"Попробуй другой пример",video:"Найти видео на YouTube",off:"Academy выключена или недоступна"}
};
const el=(tag,value)=>{const node=document.createElement(tag);if(value!==undefined)node.textContent=String(value);return node;};
const select=(form,label,items)=>{const wrap=el("label",label),node=el("select");for(const [key,name] of items){const option=el("option",name);option.value=key;node.append(option);}wrap.append(node);form.append(wrap);return node;};
export function renderAcademy(card,body){
  const t=copy[card._config?.language || card._hass?.language?.split("-")[0]] || copy.en;
  const data=card._academy;
  if(!data){body.append(el("p",t.off));return;}
  if(card.parent){
    const children=card._data.members.filter(m=>m.active&&m.role==="child");
    if(children.length){
      const form=el("form");
      const member=select(form,t.child,children.map(m=>[m.id,m.name]));
      const grade=select(form,t.grade,[[6,6],[7,7]]);
      const language=select(form,t.language,[["uk","Українська"],["en","English"]]);
      const topicList=el("fieldset");
      const refreshTopics=()=>{topicList.replaceChildren();for(const topic of data.catalog.filter(x=>x.grade===Number(grade.value))){
        const label=el("label",topic.title),input=el("input");input.type="checkbox";input.checked=true;input.value=topic.id;label.prepend(input);topicList.append(label);
      }};
      grade.addEventListener("change",refreshTopics);refreshTopics();form.append(topicList);
      const submit=el("button",t.assign);submit.type="submit";form.append(submit);
      form.addEventListener("submit",e=>{e.preventDefault();const child=children.find(m=>m.id===member.value);
        card.command("academy.assign",{member:child.id,member_revision:child.revision,grade:Number(grade.value),language:language.value,topics:[...topicList.querySelectorAll("input:checked")].map(x=>x.value)});});
      body.append(form);
    }
  }
  if(!data.assignments.length)body.append(el("p",t.empty));
  for(const row of data.assignments){
    const section=el("section");section.append(el("h3",row.id+" · "+t.grade+" "+row.grade+" · "+(card._data.members.find(m=>m.id===row.member)?.name || "")));
    const meter=el("progress");meter.max=row.topics.length;meter.value=row.mastered;
    section.append(meter,el("p",t.mastered+" "+row.mastered+"/"+row.topics.length+" · "+t.accuracy+" "+(row.attempts?Math.round(100*row.correct/row.attempts)+"%":"—")));
    if(card.parent){
      for(const key of row.topics){const item=row.progress[key],name=data.catalog.find(x=>x.id===key)?.title || key;section.append(el("p",name+": "+item.correct+"/"+item.attempts+(item.mastered?" ✓":"")+(item.due?" · "+item.due.slice(0,10):"")));}
      if(row.active)section.append(card.button(t.archive,()=>card.command("academy.archive",{id:row.id,revision:row.revision})));
    }else if(row.question){
      const q=row.question;
      section.append(el("h4",q.title),el("p",q.lesson),el("h3",q.prompt));
      if(row.history.length)section.append(el("p",row.history.at(-1).correct?t.correct:t.again));
      const video=el("a",t.video);video.href="https://www.youtube.com/results?search_query="+encodeURIComponent(q.title+" "+row.grade+" "+(row.language==="uk"?"математика":"math"));video.target="_blank";video.rel="noopener noreferrer";section.append(video);
      const form=el("form"),input=card.input(form,"answer",t.answer);input.maxLength=64;input.autocomplete="off";
      const submit=el("button",t.check);submit.type="submit";form.append(submit);
      form.addEventListener("submit",e=>{e.preventDefault();card.command("academy.answer",{id:row.id,revision:row.revision,topic:q.topic,answer:input.value});});section.append(form);
    }else if(row.active)section.append(el("p",t.review));
    body.append(section);
  }
}
