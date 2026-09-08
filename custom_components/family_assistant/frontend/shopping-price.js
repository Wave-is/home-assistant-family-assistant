/* Exact opt-in totals; no currency lookup or floating-point arithmetic. */
export const PRICE_COPY = {
  en: {enabled:"Record the total paid for this quantity",total:"Total paid (up to 4 decimals)",currency:"Currency code (3 Latin letters)",shared:"Optional. Price history is visible to all active family members. No accounting or currency conversion.",invalid:"Check the total (0–999999999) and the three-letter currency code.",history:"Purchase price"},
  ru: {enabled:"Записать сумму за это количество",total:"Уплаченная сумма (до 4 знаков)",currency:"Код валюты (3 латинские буквы)",shared:"Необязательно. История цен видна всем активным членам семьи. Это не бухгалтерский учёт и не конвертация валют.",invalid:"Проверьте сумму (0–999999999) и код валюты из трёх букв.",history:"Цена покупки"},
  uk: {enabled:"Записати суму за цю кількість",total:"Сплачена сума (до 4 знаків)",currency:"Код валюти (3 латинські літери)",shared:"Необов’язково. Історія цін видима всім активним членам родини. Це не бухгалтерський облік і не конвертація валют.",invalid:"Перевірте суму (0–999999999) і код валюти з трьох літер.",history:"Ціна покупки"}
};

export function parsePrice(total, currency) {
  if (typeof total !== "string" || typeof currency !== "string" || total.length > 14 || currency.length !== 3) return null;
  const normalized = total.replace(",", ".");
  const match = normalized.match(/^(0|[1-9][0-9]{0,8})(?:\.([0-9]{1,4}))?$/);
  // JavaScript $ can match before a final newline: require the entire match too.
  if (!match || match[0] !== normalized || !/^[A-Za-z]{3}$/.test(currency)) return null;
  const fractional = match[2] || "";
  if (BigInt(match[1] + fractional.padEnd(4, "0")) > 9999999990000n) return null;
  const cleanFraction = fractional.replace(/0+$/, "");
  return {total: cleanFraction ? `${match[1]}.${cleanFraction}` : match[1], currency: currency.toUpperCase()};
}

export function renderPriceFields(parent, copy, state, {disabled = false, isCurrent, onChange} = {}) {
  const fieldset = document.createElement("fieldset");
  fieldset.className = "shopping-price-fields";
  fieldset.style.display = "block";
  const legend = document.createElement("legend");
  legend.textContent = copy.history;
  fieldset.append(legend);
  const checkboxLabel = document.createElement("label");
  checkboxLabel.className = "check";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = state.includePrice === true;
  checkboxLabel.append(checkbox, document.createTextNode(copy.enabled));
  fieldset.append(checkboxLabel);
  const makeInput = (name, label, value, maxLength) => {
    const wrap = document.createElement("label");
    wrap.textContent = label;
    const input = document.createElement("input");
    Object.assign(input, {type:"text",name,value:typeof value === "string" ? value : "",maxLength,autocomplete:"off"});
    wrap.append(input);
    fieldset.append(wrap);
    return input;
  };
  const totalInput = makeInput("price_total", copy.total, state.priceTotal, 14);
  totalInput.inputMode = "decimal";
  const currencyInput = makeInput("price_currency", copy.currency, state.priceCurrency, 3);
  const shared = document.createElement("p");
  shared.className = "sub";
  shared.textContent = copy.shared;
  fieldset.append(shared);
  const current = () => typeof isCurrent === "function" && isCurrent() && !disabled;
  const update = () => {
    checkbox.disabled = Boolean(disabled);
    totalInput.disabled = currencyInput.disabled = Boolean(disabled) || !checkbox.checked;
  };
  update();
  checkbox.addEventListener("change", () => {
    if (!current()) return;
    state.includePrice = checkbox.checked;
    update();
    onChange?.();
  });
  for (const [input, key] of [[totalInput,"priceTotal"],[currencyInput,"priceCurrency"]]) {
    const handler = () => {
      if (!current() || input.disabled) return;
      state[key] = input.value;
      onChange?.();
    };
    input.addEventListener("input", handler);
    input.addEventListener("change", handler);
  }
  parent.append(fieldset);
  return {fieldset,totalInput,currencyInput,checkbox};
}
