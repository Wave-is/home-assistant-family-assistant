/* Canonical names never depend on who loaded a legacy family-*-card first. */
export const CARD_VIEWS = Object.freeze([
  ["today", "assistant"], ["shopping", "shopping"], ["tasks", "tasks"],
  ["court", "court"], ["alarms", "alarms"], ["health", "health"],
  ["conversation", "conversation"], ["mikrotik", "network"],
  ["calendar", "calendar"], ["routines", "routines"], ["pantry", "pantry"],
  ["meals", "meals"], ["school", "school"], ["maintenance", "maintenance"],
  ["polls", "polls"], ["presence", "presence"], ["digests", "digests"],
  ["home_status", "home-status"],
].map(pair=>Object.freeze(pair)));

export function cardView(type) {
  const name=String(type || "").replace(/^custom:/, "");
  return CARD_VIEWS.find(([view, suffix])=>name===`family-${suffix}-card`
    || (view!=="today" && name===`family-assistant-${suffix}-card`))?.[0] || "today";
}

export function registerCards(BaseCard, labels) {
  window.customCards=window.customCards || [];
  for(const [view, suffix] of CARD_VIEWS){
    const legacy=`family-${suffix}-card`;
    const canonical=view==="today"?legacy:`family-assistant-${suffix}-card`;
    if(!customElements.get(canonical)){
      class Card extends BaseCard {static defaultView=view;static familyAssistantCard=true;}
      customElements.define(canonical,Card);
    }
    const registered=customElements.get(canonical);
    // A browser registry is immutable. Never advertise a foreign constructor as ours.
    if(registered.familyAssistantCard===true
      && !window.customCards.some(card=>card.type===canonical)){
      window.customCards.push({type:canonical,name:`Family Assistant · ${labels[view]}`,
        description:labels[view],preview:true});
    }
    // Keep saved dashboards working when this alias is free. Existing legacy
    // resources remain untouched; the picker offers only namespaced new cards.
    if(legacy!==canonical && !customElements.get(legacy)){
      class CompatibilityCard extends registered {}
      customElements.define(legacy,CompatibilityCard);
    }
  }
}
