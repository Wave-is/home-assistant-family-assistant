/* Home Assistant's family control center. All household data comes from its
   authorized panel projection; existing cards own day-to-day module workflows. */
import {PANEL_STYLES} from "./panel-styles.js";
import {PANEL_COPY, PANEL_LANGUAGES, PANEL_MODULES, moduleCopy} from "./panel-copy.js";
import {searchSettings} from "./panel-search.js";
import {ERRORS} from "./errors.js";

const AVATARS = {adult:"🧑", child:"🧒", cat:"🐱", dog:"🐶", robot:"🤖", flower:"🌼", star:"⭐"};
const TABS = [["overview","🏠"],["members","👥"],["modules","⚙️"],["connections","🔌"],["advanced","🛠️"]];
const clone = value => JSON.parse(JSON.stringify(value));
const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
};

export class FamilyAssistantPanel extends HTMLElement {
  constructor() {
    super(); this.attachShadow({mode:"open"});
    this._tab="overview"; this._search=""; this._generation=0;
    this._onUnload = event => {if(this.hasDraft){event.preventDefault();event.returnValue="";}};
  }
  get lang() {const lang=this._hass?.language?.split("-")[0];return PANEL_COPY[lang]?lang:"en";}
  get t() {return PANEL_COPY[this.lang];}
  get owner() {return this._data?.view?.role==="owner" && !this._data?.view?.read_only;}
  get members() {return this._data?.members || this._data?.view?.members || [];}
  get settings() {return this._data?.view?.settings || {};}
  get hasDraft() {return this._dirty || (!!this._workspaceDirty && !!this._embedded?.shadowRoot?.querySelector("form"));}
  set hass(value) {
    const changed = this._hass?.user?.id !== value?.user?.id || this._hass?.connection !== value?.connection;
    const languageChanged = this._hass?.language !== value?.language;
    this._hass=value;
    if(changed || !this._initialized) {
      this._initialized=true; this.reset();
      if(this.isConnected) void this.loadData();
    } else {
      if(this._embedded) this._embedded.hass=value;
      if(languageChanged && !this.hasDraft && !this._workspace) this.render();
    }
  }
  connectedCallback() {
    window.addEventListener("beforeunload",this._onUnload);
    window.clearInterval(this._timer);
    this._timer=window.setInterval(()=>{if(!this.hasDraft&&!this._writing&&!this._wizardOpen&&!this._workspace)void this.loadData({quiet:true});},30000);
    if(this._hass) void this.loadData(); else this.render();
  }
  disconnectedCallback() {
    window.removeEventListener("beforeunload",this._onUnload);
    window.clearInterval(this._timer); this._timer=null;
    this._generation++; this._loading=false; this._writing=false;
    this._invite=null; this._preview=null; this._embedded=null;
  }
  reset() {
    this._generation++; this._entries=null; this._entry=null; this._data=null;
    this._loading=false;this._writing=false;this._error=null;this._notice=null;
    this._member=null;this._draft=null;this._dirty=false;this._pending=null;
    this._wizardOpen=false;this._module=null;this._workspace=null;this._workspaceMember=null;this._workspaceSchoolSection=null;this._embedded=null;
    this._invite=null;this._enrollmentConsent=null;this._preview=null;this._tab="overview";this._search="";this._workspaceDirty=false;this._testing=false;this._phrase="";
    this.render();
  }
  async loadData({quiet=false}={}) {
    if(!this._hass || this._loading || this._writing || !this.isConnected) return false;
    const generation=this._generation;this._loading=true;
    if(!quiet && !this._data)this.render();
    try {
      if(!this._entries){
        const entries=await this._hass.callWS({type:"family_assistant/households"});
        if(generation!==this._generation)return false;
        if(!Array.isArray(entries))throw new Error("invalid_response");
        this._entries=entries;
        if(entries.length===1)this._entry=entries[0].entry_id;
      }
      if(!this._entry){this._error=null;return true;}
      const data=await this._hass.callWS({type:"family_assistant/panel",entry_id:this._entry});
      if(generation!==this._generation)return false;
      if(!data?.view?.settings || !Array.isArray(data.view.members))throw new Error("invalid_response");
      const oldRole=this._data?.view?.role;
      this._data=data;this._error=null;this._observedAt=new Date();
      if(oldRole && oldRole!==data.view.role){this._member=null;this._draft=null;this._pending=null;this._dirty=false;this._invite=null;}
      if(data.view.read_only){this._draft=null;this._pending=null;this._dirty=false;this._wizardOpen=false;}
      return true;
    } catch(error) {
      if(generation!==this._generation)return false;
      this._error=this.errorText(error);
      // Never keep a private projection after authorization is lost.
      if(["forbidden","not_found","not_ready","unauthorized"].includes(error?.code)){
        this._data=null;this._entries=null;this._entry=null;this._draft=null;
        this._member=null;this._dirty=false;this._invite=null;this._embedded=null;
      }
      return false;
    } finally {
      if(generation===this._generation){this._loading=false;if(!quiet || !this._dirty)this.render();}
    }
  }
  errorText(error) {
    if(error?.code==="conflict")return this.t.conflict;
    return ERRORS[this.lang]?.[error?.code] || this.t.failure;
  }
  button(label, action, {primary=false,disabled=false,id}={}) {
    const button=el("button",label,`btn ${primary?"btn-primary":"btn-secondary"}`);
    button.type="button";button.disabled=disabled||!!this._writing;if(id)button.id=id;
    button.addEventListener("click",action);return button;
  }
  notice(text,error=false) {
    const node=el("div",text,`panel-notice ${error?"panel-error":""}`);
    node.setAttribute("role",error?"alert":"status");return node;
  }
  section(title) {const section=el("section",null,"card");section.append(el("h3",title,"card-title"));return section;}
  navigate(action) {
    if(this._writing)return false;
    if(this.hasDraft&&!window.confirm(this.t.discard))return false;
    this._dirty=false;this._draft=null;this._pending=null;this._notice=null;this._error=null;
    this._member=null;this._module=null;this._workspace=null;this._workspaceMember=null;this._workspaceSchoolSection=null;this._embedded=null;
    this._search="";this._preview=null;this._workspaceDirty=false;action();this.render();return true;
  }
  setTab(tab) {this.navigate(()=>{this._tab=tab;this._wizardOpen=false;});}
  openModuleView(id,workspace=false) {
    this.navigate(()=>{this._tab="modules";this._module=id;this._workspace=workspace?(id==="price_watch"?"shopping":id):null;this._wizardOpen=false;});
  }
  openMemberView(member) {
    this.navigate(()=>{this._tab="members";this._wizardOpen=false;this._member=clone(member || {name:"",role:"child",language:this.settings.language||"en",aliases:[],active:true});this._memberTab="main";});
  }
  openMemberWorkspace(member,view,schoolSection="all") {
    if(!member?.id||!["school","alarms","digests"].includes(view))return;
    this.navigate(()=>{this._tab="members";this._module=view;this._workspace=view;this._workspaceMember=clone(member);this._workspaceSchoolSection=schoolSection;this._wizardOpen=false;});
  }
  async selectFamily(entryId) {
    if(!this.navigate(()=>{}))return;
    this._generation++;this._entry=entryId||null;this._data=null;this._loading=false;
    this._invite=null;this._tab="overview";this._wizardOpen=false;
    await this.loadData();
  }
  async command(action,payload,{onSuccess}={}) {
    if(this._writing||!this._entry||!this._hass||!this.owner)return false;
    const generation=this._generation,entry=this._entry;
    const fingerprint=JSON.stringify([entry,action,payload]);
    if(this._pending && this._pending.fingerprint!==fingerprint){this._error=this.t.conflict;this.render();return false;}
    if(!this._pending)this._pending={fingerprint,action,payload:clone(payload),id:crypto.randomUUID()};
    const pending=this._pending;this._writing=true;this._error=null;this._notice=null;this.render();
    let accepted=false;
    try {
      const result=await this._hass.callWS({type:"family_assistant/execute",entry_id:entry,action:pending.action,payload:pending.payload,operation_id:pending.id});
      accepted=true;
      if(generation!==this._generation)return false;
      const data=await this._hass.callWS({type:"family_assistant/panel",entry_id:entry});
      if(generation!==this._generation)return false;
      if(!data?.view?.settings)throw new Error("invalid_response");
      if(action==="settings.patch" && Object.entries(pending.payload.changes).some(([key,value])=>JSON.stringify(data.view.settings[key])!==JSON.stringify(value)))throw new Error("readback_mismatch");
      if(action==="members.save"){
        const member=(data.members||data.view.members||[]).find(member=>member.id===(result?.id||pending.payload.id));
        if(!member||Object.entries(pending.payload).some(([key,value])=>key!=="revision"&&JSON.stringify(member[key]??null)!==JSON.stringify(value)))throw new Error("readback_mismatch");
      }
      if(action==="settings.onboarding" && ["step","completed"].some(key=>data.onboarding?.[key]!==pending.payload[key]))throw new Error("readback_mismatch");
      this._data=data;this._observedAt=new Date();this._dirty=false;this._draft=null;this._pending=null;
      this._notice=this.t.saved;if(onSuccess)onSuccess(data);return true;
    } catch(error) {
      if(generation===this._generation){this._error=accepted?this.t.unverified:this.errorText(error);}
      return false;
    } finally {if(generation===this._generation){this._writing=false;this.render();}}
  }
  saveSettings(changes, revision=this._data?.settings_revision,options={}) {
    return this.command("settings.patch",{revision,changes},options);
  }
  async toggleModule(id,enabled) {
    const modules=new Set(this.settings.modules || []);if(enabled)modules.add(id);else modules.delete(id);
    return this.saveSettings({modules:[...modules].sort()});
  }
  async saveMember() {
    if(!this._draft)return;
    const d=this._draft;
    const payload={name:d.name.trim(),role:d.role,language:d.language,aliases:d.aliasesText.split(",").map(v=>v.trim()).filter(Boolean),active:d.active,ha_user_id:d.ha_user_id.trim()||null,birth_date:d.birth_date||null,avatar:d.avatar||null};
    if(d.id){payload.id=d.id;payload.revision=d.revision;}
    await this.command("members.save",payload,{onSuccess:()=>{this._member=null;}});
  }
  field(form,draft,key,label,{type="text",options,required=false,min,max,hint}={}) {
    const wrap=el("label",label,"form-group"),input=el(options?"select":"input");
    input.className="form-control";input.name=key;input.setAttribute("aria-label",label);
    if(options)for(const [value,title]of options){const option=el("option",title);option.value=value;input.append(option);}
    else input.type=type;
    if(type==="checkbox")input.checked=!!draft[key];else input.value=draft[key]??"";
    input.required=required;if(min!==undefined)input.min=String(min);if(max!==undefined)input.max=String(max);
    if(type==="text")input.maxLength=key==="aliasesText"?1620:128;
    input.disabled=this._writing||!!this._pending||!this.owner;
    input.addEventListener(type==="checkbox"||options?"change":"input",()=>{
      if(this._writing||this._pending||!this.owner)return;
      draft[key]=type==="checkbox"?input.checked:type==="number"?Number(input.value):input.value;this._dirty=true;
    });wrap.append(input);if(hint)wrap.append(el("small",hint,"panel-muted"));form.append(wrap);return input;
  }
  render() {
    const focus=this.shadowRoot.activeElement;
    const selection=focus?.id==="panel-search"?focus.selectionStart:null;
    this.shadowRoot.replaceChildren(el("style",PANEL_STYLES));
    const root=el("div",null,"panel-container");this.shadowRoot.append(root);
    root.append(this.renderHeader());
    if(this._error)root.append(this.notice(this._error,true));
    if(this._notice)root.append(this.notice(this._notice));
    if(!this._data){
      const box=this.section(this._loading?this.t.loading:(!this._entries?.length?this.t.noHousehold:this.t.choose));
      if(!this._loading)box.append(this.button(this.t.retry,()=>this.loadData()));root.append(box);return;
    }
    if(this._data.view.read_only)root.append(this.notice(this.t.readOnly));
    root.append(this.renderTabs());
    if(this._search.trim())root.append(this.renderSearch());
    else if(this._wizardOpen)root.append(this.renderWizard());
    else if(this._member)root.append(this.renderMember());
    else if(this._module)root.append(this.renderModule());
    else if(this._tab==="members")root.append(this.renderMembers());
    else if(this._tab==="modules")root.append(this.renderModules());
    else if(this._tab==="connections")root.append(this.renderConnections());
    else if(this._tab==="advanced")root.append(this.renderAdvanced());
    else root.append(this.renderOverview());
    if(this._invite)root.append(this.renderInvite());
    root.append(this.renderTabs(true));
    if(selection!==null){const search=this.shadowRoot.querySelector("#panel-search");search.focus();search.setSelectionRange(selection,selection);}
  }
  renderHeader() {
    const header=el("header",null,"header"),brand=el("div",null,"header-brand");
    brand.append(el("div","🏠","brand-icon-box"));const text=el("div");
    text.append(el("h1","Family Assistant"),el("p",this.settings.name||this.t.subtitle));brand.append(text);header.append(brand);
    const search=el("div",null,"search-box"),input=el("input");
    input.type="search";input.id="panel-search";input.placeholder=this.t.search;input.value=this._search;input.setAttribute("aria-label",this.t.search);
    input.disabled=!this._data||this._writing||this.hasDraft;
    input.addEventListener("input",()=>{this._search=input.value;this.render();});search.append(el("span","⌕","search-icon"),input);header.append(search);
    const controls=el("div",null,"header-right");
    if(this._entries?.length>1){
      const select=el("select");select.className="form-control";select.setAttribute("aria-label",this.t.choose);
      const placeholder=el("option",this.t.choose);placeholder.value="";select.append(placeholder);
      for(const entry of this._entries){const option=el("option",entry.title);option.value=entry.entry_id;select.append(option);}
      select.value=this._entry||"";select.disabled=this._writing;select.addEventListener("change",()=>this.selectFamily(select.value));controls.append(select);
    }
    if(this.owner)controls.append(this.button(this._data?.onboarding?.completed?this.t.wizard:this.t.resume,()=>this.navigate(()=>{this._wizardOpen=true;this._tab="overview";}),{primary:true,id:"setup-guide"}));
    controls.append(this.button(this.t.refresh,()=>this.loadData(),{disabled:this._loading||this.hasDraft||!!this._workspace,id:"panel-refresh"}));header.append(controls);return header;
  }
  renderTabs(mobile=false) {
    const nav=el("nav",null,mobile?"mobile-bottom-nav":"nav-tabs-bar");nav.setAttribute("aria-label",this.t.settings);
    for(const [id,icon]of TABS){const button=this.button(mobile?"":`${icon} ${this.t[id]}`,()=>this.setTab(id));
      if(mobile){button.append(el("span",icon,"panel-nav-icon"),el("span",this.t[`mobile_${id}`]));button.setAttribute("aria-label",this.t[id]);}
      button.className=`${mobile?"bottom-nav-item":"nav-tab-item"} ${this._tab===id?"active":""}`;button.setAttribute("aria-current",this._tab===id?"page":"false");nav.append(button);}
    return nav;
  }
  avatar(member,size="") {
    const avatar=el("div",null,`panel-avatar ${size}`);
    avatar.textContent=AVATARS[member.avatar] || (member.name||"?").trim().slice(0,2).toLocaleUpperCase();
    avatar.setAttribute("aria-hidden","true");return avatar;
  }
  renderMembers(compact=false) {
    const section=this.section(this.t.members),grid=el("div",null,compact?"panel-members-strip":"grid panel-members-grid");
    for(const member of this.members){
      const card=this.button("",()=>this.openMemberView(member));card.className="panel-member-card";
      card.append(this.avatar(member),el("strong",member.name),el("span",this.t[member.role]||this.t.guest,"panel-muted"));
      if(member.active===false)card.append(el("span",this.t.inactive,"badge"));
      grid.append(card);
    }
    if(this.owner){const add=this.button(`＋ ${this.t.addMember}`,()=>this.openMemberView(null),{id:"add-member"});add.className="panel-member-card panel-add-member";grid.append(add);}
    section.append(grid);return section;
  }
  renderOverview() {
    const wrap=el("div",null,"panel-stack");wrap.append(this.renderMembers(true));
    const columns=el("div",null,"grid grid-cols-3"),quick=this.section(this.t.quick),actions=el("div",null,"panel-quick-grid");
    for(const id of ["tasks","shopping","school","court"]){const m=moduleCopy(id,this.lang);actions.append(this.button(`${m.icon} ${m.title}`,()=>this.openModuleView(id,true)));}quick.append(actions);
    columns.append(quick,this.renderConnectionSummary(),this.renderAttention());wrap.append(columns);
    const enabled=this.section(this.t.modules),chips=el("div",null,"panel-actions");
    for(const id of this.settings.modules||[]){const m=moduleCopy(id,this.lang);chips.append(this.button(`${m.icon} ${m.title}`,()=>this.openModuleView(id)));}
    if(!chips.childElementCount)chips.append(el("p",this.t.disabled,"panel-muted"));enabled.append(chips);wrap.append(enabled);
    return wrap;
  }
  renderConnectionSummary() {
    const box=this.section(this.t.health),tg=this._data.connections?.telegram;
    box.append(this.statusRow(this.t.telegram,tg?.configured===false?this.t.notLinked:tg?.bot_connected===true?this.t.configured:this.t.unknown));
    box.append(this.statusRow(moduleCopy("conversation",this.lang).title,this._data.connections?.conversation?.configured?this.t.configured:this.t.unknown));
    if(this._observedAt)box.append(el("small",`${this.t.checked}: ${this._observedAt.toLocaleString(this.lang)}`,"panel-muted"));
    box.append(this.button(this.t.connections,()=>this.setTab("connections")));return box;
  }
  statusRow(label,value) {const row=el("div",null,"panel-status-row");row.append(el("span",label),el("strong",value));return row;}
  memberLinked(member) {return typeof member.telegram_linked==="boolean"?(member.telegram_linked?this.t.linked:this.t.notLinked):"telegram_id" in member?(member.telegram_id?this.t.linked:this.t.notLinked):this.t.unknown;}
  renderAttention() {
    const box=this.section(this.t.attention);
    const problems=(this._data.capabilities||[]).filter(cap=>cap.enabled&&cap.ready===false);
    for(const cap of problems){const m=moduleCopy(cap.id,this.lang);const row=el("div",null,"panel-issue");row.append(el("strong",m.title),el("span",(cap.issues||[]).map(code=>this.t[`reason_${code}`]||this.t.configure).join(" · ")||this.t.configure,"panel-muted"),this.button(this.t.configure,()=>this.openModuleView(cap.id)));box.append(row);}
    let memberProblems=0;
    for(const readiness of this._data.member_readiness||[]){
      const member=this.members.find(member=>member.id===readiness.id);if(member?.role!=="child"||member.active===false)continue;
      for(const id of ["school","alarms"]){if(!(this.settings.modules||[]).includes(id)||!readiness[id]?.issues?.length)continue;
        const row=el("div",null,"panel-issue");row.append(el("strong",member.name),el("span",readiness[id].issues.map(code=>this.t[`reason_${code}`]||this.t.configure).join(" · "),"panel-muted"),this.button(moduleCopy(id,this.lang).title,()=>this.openMemberWorkspace(member,id)));box.append(row);memberProblems++;
      }
    }
    if(!problems.length&&!memberProblems)box.append(el("p",this.t.noIssues,"panel-muted"));
    box.append(this.button(this.t.health,()=>this.navigate(()=>{this._tab="advanced";this._workspace="health";})));return box;
  }
  renderModules() {
    const wrap=el("div",null,"panel-stack"),head=this.section(this.t.modules);head.append(el("p",this.t.enabledHint,"panel-muted"));wrap.append(head);
    const grid=el("div",null,"grid grid-cols-3");
    for(const [id]of PANEL_MODULES){
      const m=moduleCopy(id,this.lang),cap=this._data.capabilities?.find(c=>c.id===id),enabled=(this.settings.modules||[]).includes(id);
      const card=this.section(`${m.icon} ${m.title}`);card.classList.add("panel-module-card");
      card.append(el("p",m.description,"panel-muted"),this.statusRow(this.t.settings,enabled?this.t.enabled:this.t.disabled));
      if(enabled)card.append(this.statusRow(this.t.readiness,cap?.ready===true?this.t.ready:cap?.ready===false?this.t.configure:this.t.unknown));
      card.append(this.button(this.t.configure,()=>this.openModuleView(id),{primary:true}));grid.append(card);
    }wrap.append(grid);return wrap;
  }
  renderSearch() {
    const section=this.section(this.t.search),results=searchSettings(this._search,this.lang);
    for(const result of results){const button=this.button("",()=>result.moduleId?this.openModuleView(result.moduleId):this.setTab(result.section));button.className="panel-search-result";button.append(el("strong",result.title),el("span",result.description),el("small",`${this.t[result.section]} → ${result.title}`,"panel-muted"));section.append(button);}
    if(!results.length)section.append(el("p",this.t.noResults));return section;
  }
  memberDraft() {
    if(!this._draft){const m=this._member;this._draft={...clone(m),aliasesText:(m.aliases||[]).join(", "),ha_user_id:m.ha_user_id||"",birth_date:m.birth_date||"",avatar:m.avatar||"",active:m.active!==false};}
    return this._draft;
  }
  renderMember() {
    const m=this._member,d=this.memberDraft(),wrap=el("div",null,"panel-stack"),header=this.section(m.name||this.t.newMember);
    const bar=el("div",null,"panel-actions");bar.append(this.button(`← ${this.t.members}`,()=>this.navigate(()=>{})),this.avatar(d));header.append(bar);
    const tabs=el("div",null,"panel-subtabs");
    for(const [id,label]of [["main",this.t.overview],["notifications",this.t.notifications],...(m.role==="child"?[["school",moduleCopy("school",this.lang).title]]:[]),["advanced",this.t.advanced]]){
      const b=this.button(label,()=>{this._memberTab=id;this.render();});b.classList.toggle("active",id===this._memberTab);tabs.append(b);
    }header.append(tabs);wrap.append(header);
    if(!this.owner)wrap.append(this.notice(this.t.memberOnlyOwner));
    const form=el("form",null,"card");form.id="member-form";
    form.addEventListener("submit",event=>{event.preventDefault();if(form.reportValidity())void this.saveMember();});
    if(this._memberTab==="main"){
      const columns=el("div",null,"grid grid-cols-2"),basics=el("div"),accounts=el("div");
      this.field(basics,d,"name",this.t.name,{required:true});
      this.field(basics,d,"role",this.t.role,{options:["owner","parent","adult","child","guest"].map(role=>[role,this.t[role]])});
      this.field(basics,d,"language",this.t.language,{options:Object.entries(PANEL_LANGUAGES)});
      this.field(basics,d,"aliasesText",this.t.aliases,{hint:this.t.aliasesHint});
      accounts.append(el("h4",this.t.accounts));
      accounts.append(this.statusRow(this.t.telegram,this.memberLinked(m)));
      if(m.id&&this.owner)accounts.append(this.button(this.t.invite,()=>this.generateTelegramInvite(m.id),{disabled:this._dirty}));
      accounts.append(this.statusRow(this.t.haUser,m.ha_user_id?this.t.linked:this.t.notLinked),el("p",this.t.haHint,"panel-muted"));
      accounts.append(this.renderMemberReadiness(m));
      columns.append(basics,accounts);form.append(columns);
    } else if(this._memberTab==="advanced"){
      this.field(form,d,"birth_date",this.t.birthday,{type:"date"});
      this.field(form,d,"avatar",this.t.avatar,{options:[["","—"],...Object.entries(AVATARS)]});
      this.field(form,d,"ha_user_id",this.t.userId);
      this.field(form,d,"active",this.t.active,{type:"checkbox"});
      const details=el("details");details.append(el("summary",this.t.details));
      if(m.telegram_id)details.append(this.statusRow("Telegram ID",String(m.telegram_id)));form.append(details);
    } else {
      form.append(el("p",this.t.personalHint,"panel-muted"));
      for(const id of this._memberTab==="school"?["school"]:["digests",...(m.role==="child"?["school"]:[]),"alarms"]){const info=moduleCopy(id,this.lang);form.append(this.button(`${info.icon} ${info.title}`,()=>this.openMemberWorkspace(m,id,this._memberTab==="notifications"?"reminders":"all")));}
    }
    if(this.owner){const footer=el("div",null,"panel-actions");const save=this.button(this._writing?this.t.saving:this.t.save,()=>{if(form.reportValidity())void this.saveMember();},{primary:true,id:"save-member"});footer.append(save,this.button(this.t.cancel,()=>this.navigate(()=>{})));form.append(footer);}
    wrap.append(form);return wrap;
  }
  renderMemberReadiness(member) {
    const box=el("section",null,"panel-member-readiness");box.append(el("h4",this.t.readiness));
    const readiness=this._data.member_readiness?.find(item=>item.id===member.id);
    for(const id of ["alarms",...(member.role==="child"?["school"]:[])]){
      const info=moduleCopy(id,this.lang),record=readiness?.[id],enabled=(this.settings.modules||[]).includes(id);
      box.append(this.statusRow(info.title,!enabled?this.t.disabled:record?.issues?.length?this.t.configure:(id==="alarms"?record?.enabled>0:record?.timetables>0)?this.t.configured:this.t.unknown));
      if(enabled)for(const code of record?.issues||[])box.append(el("p",this.t[`reason_${code}`]||this.t.configure,"panel-muted"));
      if(member.id)box.append(this.button(`${this.t.configure}: ${info.title}`,()=>this.openMemberWorkspace(member,id)));
    }return box;
  }
  renderSettingsForm(kind="family") {
    const source=this.settings;
    if(!this._draft)this._draft={revision:this._data.settings_revision,...(kind==="family"?{name:source.name,language:source.language,timezone:source.timezone||this._hass.config?.time_zone||"UTC"}:kind==="school"?{school_preparation_reminders:!!source.school_preparation_reminders,school_preparation_days_before:source.school_preparation_days_before??1,school_preparation_time:source.school_preparation_time||"19:00"}:kind==="court"?{automatic_penalties:!!source.automatic_penalties,daily_penalty_cap:source.daily_penalty_cap??0}:{pantry_expiry_reminders:!!source.pantry_expiry_reminders,pantry_expiry_days:source.pantry_expiry_days??3})};
    const d=this._draft,form=el("form",null,"card"),fields=el("div",null,"grid grid-cols-2");
    if(kind==="family"){
      this.field(fields,d,"name",this.t.familyName,{required:true});this.field(fields,d,"language",this.t.language,{options:Object.entries(PANEL_LANGUAGES)});this.field(fields,d,"timezone",this.t.timezone,{required:true});
    }else if(kind==="school"){
      this.field(fields,d,"school_preparation_reminders",this.t.schoolReminders,{type:"checkbox"});
      this.field(fields,d,"school_preparation_days_before",this.t.reminderDay,{options:[["0",this.t.sameDay],["1",this.t.previousDay]]});
      this.field(fields,d,"school_preparation_time",this.t.time,{type:"time",required:true});
    }else if(kind==="court"){
      this.field(fields,d,"automatic_penalties",this.t.autoPenalties,{type:"checkbox"});this.field(fields,d,"daily_penalty_cap",this.t.penaltyCap,{type:"number",min:0,max:100,required:true,hint:this.t.zeroCap});
    }else {
      this.field(fields,d,"pantry_expiry_reminders",this.t.expiryReminders,{type:"checkbox"});this.field(fields,d,"pantry_expiry_days",this.t.expiryDays,{type:"number",min:0,max:30,required:true});
    }
    const submit=async()=>{
      if(!form.reportValidity())return;
      const {revision,...changes}=d;
      if(kind==="school")changes.school_preparation_days_before=Number(changes.school_preparation_days_before);
      await this.saveSettings(changes,revision);
    };
    form.addEventListener("submit",event=>{event.preventDefault();void submit();});form.append(fields);
    if(this.owner)form.append(this.button(this.t.save,submit,{primary:true,id:"save-settings"}));
    return form;
  }
  renderModule() {
    const id=this._module,m=moduleCopy(id,this.lang),wrap=el("div",null,"panel-stack"),header=this.section(`${m.icon} ${m.title}`);
    const scope=this._workspaceMember;
    if(scope){
      header.append(el("h4",`${this.t.memberContext}: ${scope.name}`),this.button(`← ${scope.name}`,()=>this.openMemberView(this.members.find(member=>member.id===scope.id)||scope)));
      wrap.append(header,this.button(this.t.allMembers,()=>this.openModuleView(id,true)),this.renderWorkspace(this._workspace));return wrap;
    }
    header.append(el("p",m.description,"panel-muted"));
    const enabled=(this.settings.modules||[]).includes(id),row=el("div",null,"panel-actions");
    row.append(this.button(`← ${this.t.modules}`,()=>this.setTab("modules")));
    const toggle=el("label",enabled?this.t.enabled:this.t.disabled,"panel-toggle"),check=el("input");check.type="checkbox";check.checked=enabled;check.disabled=!this.owner||this._writing||this._dirty;check.setAttribute("aria-label",`${m.title}: ${this.t.enabled}`);
    check.addEventListener("change",()=>this.toggleModule(id,check.checked));toggle.prepend(check);row.append(toggle);header.append(row);wrap.append(header);
    const nav=el("div",null,"panel-subtabs");nav.append(this.button(this.t.settings,()=>this.navigate(()=>{this._module=id;})),this.button(this.t.dailyUse,()=>this.openModuleView(id,true)));if(id==="pantry")nav.append(this.button("🍽️",()=>this.navigate(()=>{this._module=id;this._workspace="meals";})));
    wrap.append(nav);
    if(this._workspace)wrap.append(this.renderWorkspace(this._workspace));
    else {
      const cap=this._data.capabilities?.find(c=>c.id===id),status=this.section(this.t.readiness);
      status.append(this.statusRow(this.t.settings,enabled?this.t.enabled:this.t.disabled));
      if(enabled)status.append(this.statusRow(this.t.readiness,cap?.ready===true?this.t.ready:cap?.ready===false?this.t.configure:this.t.unknown));
      for(const code of cap?.issues||[])status.append(el("p",this.t[`reason_${code}`]||this.t.configure,"panel-muted"));
      status.append(el("p",this.t.enabledHint,"panel-muted"));wrap.append(status);
      if(["school","court","pantry"].includes(id))wrap.append(this.renderSettingsForm(id));
      const details=this.section(this.t.memberModules);details.append(el("p",this.t.instructions,"panel-muted"));details.append(this.button(this.t.dailyUse,()=>this.openModuleView(id,true),{primary:true}));wrap.append(details);
    }return wrap;
  }
  renderWorkspace(view) {
    const host=el("div",null,"panel-workspace");host.addEventListener("input",()=>{this._workspaceDirty=true;});host.addEventListener("change",()=>{this._workspaceDirty=true;});
    const config={type:"custom:family-assistant-card",entry_id:this._entry,view,...(this._workspaceMember?{member_id:this._workspaceMember.id,...(view==="school"?{school_section:this._workspaceSchoolSection||"all"}:{})}:{})};
    const mount=()=>{
      if(!host.isConnected||!this._hass||!this._entry)return;
      const card=document.createElement("family-assistant-card");card.setConfig(config);card.hass=this._hass;this._embedded=card;host.replaceChildren(card);
    };
    if(customElements.get("family-assistant-card"))queueMicrotask(mount);
    else {host.append(this.notice(this.t.loading));import("./family-assistant.js").then(()=>mount()).catch(()=>{if(host.isConnected)host.replaceChildren(this.notice(this.t.failure,true));});}
    return host;
  }
  renderConnections() {
    const wrap=el("div",null,"panel-stack"),tg=this._data.connections?.telegram||{},box=this.section(this.t.telegram);
    box.append(this.statusRow(this.t.telegram,tg.configured===false?this.t.notLinked:tg.bot_connected?this.t.configured:this.t.unknown));
    if(tg.bot_username)box.append(el("p",`@${tg.bot_username}`));
    for(const [key,label]of [["send_ok","send"],["commands_ok","commands"],["text_ok","text"]]){
      const timestamp=tg[`${key.replace("_ok","")}_checked_at`];
      box.append(this.statusRow(this.t[label],tg[key]===true?this.t.observed:tg[key]===false?this.t.unavailable:this.t.unknown));
      if(timestamp)box.append(el("small",`${this.t.checked}: ${this.formatDate(timestamp)}`,"panel-muted"));
    }
    box.append(this.statusRow(this.t.group,tg.group_ok?this.t.linked:this.t.notLinked));
    if(tg.group_name)box.append(el("p",tg.group_name));
    if(tg.checked_at)box.append(el("p",`${this.t.checked}: ${this.formatDate(tg.checked_at)}`,"panel-muted"));
    const actions=el("div",null,"panel-actions");actions.append(this.button(this.t.refresh,()=>this.loadData()),this.integrationLink(this.t.configureTelegram));
    if(this.owner)actions.append(this.button(this.t.groupInvite,()=>this.generateTelegramInvite(null,"group"),{id:"invite-group"}));box.append(actions);wrap.append(box);
    const people=this.section(this.t.members);for(const member of this.members){const row=el("div",null,"panel-status-row");row.append(el("strong",member.name),el("span",this.memberLinked(member)));if(this.owner&&member.active!==false)row.append(this.button(this.t.invite,()=>this.generateTelegramInvite(member.id)));people.append(row);}wrap.append(people);
    if(this.owner&&this._data.enrollments?.length){
      const pending=this.section(this.t.pendingInvites);
      for(const record of this._data.enrollments){
        const member=this.members.find(member=>member.id===record.member),row=el("div",null,"panel-status-row");
        row.append(el("strong",record.kind==="group"?this.t.group:member?.name||this.t.members),el("span",this.t[`enrollment_${record.state}`]||this.t.unknown),this.button(this.t.reviewInvite,()=>this.openEnrollment(record)));pending.append(row);
      }wrap.append(pending);
    }
    const assistant=this.section(moduleCopy("conversation",this.lang).title);assistant.append(el("p",this.t.localReady,"panel-muted"),this.integrationLink(this.t.configureAssistant));
    if(this.owner)assistant.append(this.renderRecognition());wrap.append(assistant);return wrap;
  }
  integrationLink(label=this.t.integration) {
    const link=el("a",label,"btn btn-secondary");link.href="/config/integrations/integration/family_assistant";
    link.addEventListener("click",event=>{if(this.hasDraft&&!window.confirm(this.t.discard))event.preventDefault();});return link;
  }
  renderRecognition() {
    const form=el("form",null,"panel-stack");form.append(el("h4",this.t.recognition),el("p",this.t.previewHint,"panel-muted"));
    const label=el("label",this.t.phrase,"form-group"),input=el("textarea");input.className="form-control";input.value=this._phrase||"";input.maxLength=2000;input.required=true;input.name="phrase";input.disabled=this._testing;
    input.addEventListener("input",()=>{this._phrase=input.value;this._preview=null;});label.append(input);form.append(label);
    const run=async()=>{
      if(this._testing||!form.reportValidity())return;
      const generation=this._generation,entry=this._entry;this._testing=true;this._preview=null;this.render();
      try{const result=await this._hass.callWS({type:"family_assistant/ai_sandbox_test",entry_id:entry,text:input.value});if(generation===this._generation)this._preview=result;}
      catch(error){if(generation===this._generation)this._error=this.errorText(error);}
      finally{if(generation===this._generation){this._testing=false;this.render();}}
    };
    form.addEventListener("submit",event=>{event.preventDefault();void run();});form.append(this.button(this.t.preview,run,{primary:true,disabled:this._testing}));
    if(this._preview){const result=this.section(this.t.recognition);
      if(this._preview.recognized){
        const intent=this._preview.intent||"",prefix=intent.split(".")[0],m=moduleCopy(prefix==="members"?"tasks":prefix,this.lang);
        result.append(this.statusRow(this.t.action,PANEL_MODULES.some(([id])=>id===prefix)?m.title:this.t.preview));
        for(const assessment of this._preview.payload?.assessments||[]){const member=this.members.find(member=>member.id===assessment.member);result.append(el("p",`${member?.name||this.t.members}: ${assessment.points>0?"+":""}${assessment.points} · ${assessment.reason||""}`));}
        if(this._preview.payload?.title)result.append(el("p",this._preview.payload.title));
        const details=el("details");details.append(el("summary",this.t.details),el("code",intent));result.append(details);
      }else result.append(el("p",this.t.noMatch));form.append(result);
    }return form;
  }
  async generateTelegramInvite(memberId,kind="member") {
    if(!this.owner||this._writing)return;
    const generation=this._generation;this._writing=true;this._error=null;this.render();
    try{
      const result=await this._hass.callWS({type:"family_assistant/telegram_invite",entry_id:this._entry,...(kind==="group"?{kind}:{member_id:memberId})});
      if(generation!==this._generation)return;
      if(!result.id||!result.code||!result.expires_at)throw new Error("invalid_response");
      this._enrollmentConsent=null;this._invite={...result,kind,member:memberId,state:"issued"};
    }catch(error){if(generation===this._generation)this._error=this.errorText(error);}
    finally{if(generation===this._generation){this._writing=false;this.render();}}
  }
  async openEnrollment(record) {
    this._enrollmentConsent=null;this._invite=clone(record);this.render();await this.refreshEnrollment();
  }
  async refreshEnrollment() {
    if(!this.owner||!this._invite?.id||this._writing)return;
    const generation=this._generation,id=this._invite.id;this._writing=true;this._enrollmentConsent=null;this._error=null;this.render();
    try {
      const status=await this._hass.callWS({type:"family_assistant/telegram_enrollment",entry_id:this._entry,enrollment_id:id});
      if(generation!==this._generation||id!==this._invite?.id)return;
      if(status.id!==id||!status.state||!status.expires_at)throw new Error("invalid_response");
      this._invite={...this._invite,...status};
    }catch(error){if(generation===this._generation)this._error=this.errorText(error);}
    finally{if(generation===this._generation){this._writing=false;this.render();}}
  }
  enrollmentFingerprint(record) {return JSON.stringify([record.id,record.candidate?.chat_id,record.candidate?.user_id]);}
  enrollmentExpired(record) {const expires=new Date(record.expires_at).valueOf();return !Number.isFinite(expires)||expires<=Date.now();}
  async confirmEnrollment() {
    const record=this._invite;
    if(!this.owner||this._writing||record?.state!=="captured"||this._enrollmentConsent!==this.enrollmentFingerprint(record))return;
    if(this.enrollmentExpired(record)){this._error=this.t.enrollment_expired;this.render();return;}
    const candidate=record.candidate;
    if(!Number.isSafeInteger(candidate?.chat_id)||!Number.isSafeInteger(candidate?.user_id)){this._error=this.t.failure;this.render();return;}
    const generation=this._generation,id=record.id;this._writing=true;this._error=null;this._notice=null;this.render();let accepted=false;
    try {
      await this._hass.callWS({type:"family_assistant/telegram_enrollment_confirm",entry_id:this._entry,enrollment_id:id,candidate:{chat_id:candidate.chat_id,user_id:candidate.user_id}});accepted=true;
      const status=await this._hass.callWS({type:"family_assistant/telegram_enrollment",entry_id:this._entry,enrollment_id:id});
      if(generation!==this._generation||id!==this._invite?.id)return;
      if(status.id!==id||status.state!=="confirmed")throw new Error("readback_mismatch");
      const data=await this._hass.callWS({type:"family_assistant/panel",entry_id:this._entry});
      if(generation!==this._generation||id!==this._invite?.id)return;
      if(!data?.view?.settings)throw new Error("invalid_response");
      this._data=data;this._invite={...record,...status};this._enrollmentConsent=null;this._notice=this.t.enrollment_confirmed;
    }catch(error){if(generation===this._generation){this._enrollmentConsent=null;this._error=accepted?this.t.unverified:this.errorText(error);}}
    finally{if(generation===this._generation){this._writing=false;this.render();}}
  }
  formatDate(value) {const date=new Date(value);return Number.isNaN(date.valueOf())?this.t.unknown:date.toLocaleString(this.lang);}
  renderInvite() {
    const overlay=el("div",null,"modal-overlay"),modal=el("section",null,"modal-content");modal.setAttribute("role","dialog");modal.setAttribute("aria-modal","true");modal.setAttribute("aria-label",this.t.invite);
    const result=this._invite,member=this.members.find(member=>member.id===result.member);
    modal.append(el("h3",result.kind==="group"?this.t.groupInvite:this.t.invite),el("p",result.kind==="group"?this.t.group:member?.name||this.t.members));
    if(this._error)modal.append(this.notice(this._error,true));
    let value=result.kind==="group"?result.instruction:result.code;
    if(result.kind!=="group"&&result.url){try{const url=new URL(result.url);if(url.protocol==="https:"&&url.hostname==="t.me"&&url.username===""&&url.password==="")value=url.href;}catch{/* Only the verified code remains. */}}
    const input=el("input");input.className="form-control";input.value=value||"";input.readOnly=true;input.setAttribute("aria-label",this.t.invite);
    if(value){modal.append(el("p",result.kind==="group"?this.t.groupInviteHint:this.t.inviteHint),input);}
    else modal.append(el("p",this.t.inviteResumed,"panel-muted"));
    modal.append(el("p",`${this.t.expires}: ${this.formatDate(result.expires_at)}`));
    const expired=result.state!=="confirmed"&&this.enrollmentExpired(result),status=expired?"expired":result.state;
    modal.append(this.notice(this.t[`enrollment_${status}`]||this.t.unknown));
    if(result.state==="captured"&&!expired){
      const candidate=result.candidate||{};modal.append(el("strong",candidate.name||this.t.unknown));
      if(candidate.username)modal.append(el("p",`@${candidate.username}`));
      modal.append(this.statusRow(this.t.telegramChatId,candidate.chat_id),this.statusRow(this.t.telegramUserId,candidate.user_id));
      const label=el("label",this.t.enrollmentConsent,"panel-enrollment-consent"),checkbox=el("input");checkbox.type="checkbox";checkbox.name="confirm_account";checkbox.checked=this._enrollmentConsent===this.enrollmentFingerprint(result);checkbox.disabled=this._writing;
      const button=this.button(this.t.confirmLink,()=>this.confirmEnrollment(),{primary:true,disabled:!checkbox.checked,id:"confirm-enrollment"});
      checkbox.addEventListener("change",()=>{this._enrollmentConsent=checkbox.checked?this.enrollmentFingerprint(result):null;button.disabled=!checkbox.checked||this._writing;});label.prepend(checkbox);modal.append(label,button);
    }
    const close=()=>{this._invite=null;this.render();};
    const actions=el("div",null,"panel-actions");
    if(value&&result.state==="issued"&&!expired)actions.append(this.button(this.t.copy,async()=>{try{await navigator.clipboard.writeText(value);this._notice=this.t.copied;}catch{this._error=this.t.failure;}this.render();}));
    if(!expired&&["issued","captured"].includes(result.state))actions.append(this.button(this.t.refresh,()=>this.refreshEnrollment(),{id:"refresh-enrollment"}));
    if(expired||result.state==="superseded"||(!value&&result.state==="issued"))actions.append(this.button(this.t.invite,()=>this.generateTelegramInvite(result.member,result.kind)));
    actions.append(this.button(this.t.close,close));modal.append(actions);
    modal.addEventListener("keydown",event=>{
      if(event.key==="Escape"){event.preventDefault();close();}
      if(event.key==="Tab"){
        const nodes=[...modal.querySelectorAll("input,button:not(:disabled)")];const first=nodes[0],last=nodes.at(-1);
        if(event.shiftKey&&this.shadowRoot.activeElement===first){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&this.shadowRoot.activeElement===last){event.preventDefault();first.focus();}
      }
    });queueMicrotask(()=>{if(modal.isConnected)(modal.querySelector("input,button")||modal).focus();});overlay.append(modal);return overlay;
  }
  renderAdvanced() {
    const wrap=el("div",null,"panel-stack");if(this._workspace==="health"){wrap.append(this.renderWorkspace("health"));return wrap;}
    wrap.append(this.section(this.t.familyName),this.renderSettingsForm());const box=this.section(this.t.advanced);
    box.append(el("p",this.t.connectionHint,"panel-muted"),this.integrationLink(),this.button(this.t.health,()=>this.navigate(()=>{this._tab="advanced";this._workspace="health";})));wrap.append(box);return wrap;
  }
  async wizardStep(step,{completed=false,skip}={}) {
    if(this._dirty){this._error=this.t.draft;this.render();return;}
    const onboarding=this._data.onboarding,skipped=new Set(onboarding.skipped||[]);if(skip)skipped.add(skip);
    await this.command("settings.onboarding",{revision:onboarding.revision,step,completed,skipped:[...skipped]},{onSuccess:()=>{if(completed){this._wizardOpen=false;this._tab="overview";}}});
  }
  renderWizard() {
    const step=this._data.onboarding?.step||1,wrap=el("div",null,"panel-stack"),header=this.section(this.t.wizard),steps=el("ol",null,"panel-wizard-steps");
    for(const [index,label]of [this.t.members,this.t.connections,this.t.modules,this.t.review].entries()){const item=el("li",`${index+1}. ${label}`,step===index+1?"active":"");if(step===index+1)item.setAttribute("aria-current","step");steps.append(item);}header.append(steps);wrap.append(header);
    if(step===1){const intro=this.section(this.t.welcome);intro.append(el("p",this.t.wizardHint,"panel-muted"));wrap.append(intro,this.renderSettingsForm(),this.renderMembers(true));}
    if(step===2)wrap.append(this.renderConnections());
    if(step===3){
      const packs=this.section(this.t.modules);packs.append(el("p",this.t.packHint,"panel-muted"));
      for(const [label,ids]of [[this.t.familyPack,["tasks"]],[this.t.rewardPack,["tasks","court"]],[this.t.homePack,["shopping","pantry","maintenance"]]])packs.append(this.button(`＋ ${label}`,()=>this.saveSettings({modules:[...new Set([...(this.settings.modules||[]),...ids])].sort()})));
      wrap.append(packs,this.renderModules());
    }
    if(step===4){wrap.append(this.section(this.t.review),this.renderOverview());}
    const footer=el("div",null,"card panel-actions");
    footer.append(this.button(this.t.back,()=>this.wizardStep(step-1),{disabled:step===1}),this.button(this.t.later,()=>[2,3].includes(step)?this.wizardStep(step+1,{skip:step===2?"telegram":"modules"}):this.navigate(()=>{this._wizardOpen=false;})),this.button(step===4?this.t.finish:this.t.continue,()=>this.wizardStep(Math.min(4,step+1),{completed:step===4}),{primary:true}));wrap.append(footer);return wrap;
  }
}
if(!customElements.get("family-assistant-panel"))customElements.define("family-assistant-panel",FamilyAssistantPanel);
