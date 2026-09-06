/* Localized, accessible routine-condition editor. It renders text safely and preserves drafts. */
const CONDITION_COPY = {
  en: {
    help: "How conditions work",
    timeWindow: "Time window",
    condition: "Skip the routine when",
    hint: "Conditions only observe approved Home Assistant entities; they never control devices. Unknown or stale observations remain unknown, including when negated.",
    templateHint:
      "Checked once when the routine starts. If true, all steps are skipped; unknown never skips.",
    none: "No condition",
    kind: "Condition type",
    negate: "Negate result",
    mode: "Household mode",
    entity: "Observed entity",
    state: "Expected exact state",
    maxAge: "Maximum age (seconds, 1–3600)",
    start: "Start time",
    end: "End time",
    timezone: "Time zone",
    all: "All conditions",
    any: "Any condition",
    add: "Add condition",
    remove: "Remove",
    replace: "Replace condition",
    unsupported:
      "This existing condition is not supported by this editor. Replace it explicitly to edit it.",
    depth: "Maximum condition nesting reached.",
    nodes: "Maximum condition count reached.",
    conjunction: "A group must contain at least one condition.",
    entityHint: "Only entities in the approved observation list are available.",
    stateHint: "unknown and unavailable are never valid expected states.",
    modes: {
      normal: "Normal",
      holidays: "Holidays",
      guests: "Guests",
      ill: "Illness",
      vacation: "Vacation",
    },
  },
  ru: {
    help: "Как работают условия",
    timeWindow: "Временной интервал",
    condition: "Пропустить распорядок, если",
    hint: "Условия только наблюдают за разрешёнными объектами Home Assistant и никогда ими не управляют. Неизвестное или устаревшее наблюдение остаётся неизвестным, в том числе при отрицании.",
    templateHint:
      "Проверяется один раз при запуске. Если условие истинно, все шаги пропускаются. Неизвестный результат не вызывает пропуск.",
    none: "Без условия",
    kind: "Тип условия",
    negate: "Инвертировать результат",
    mode: "Режим дома",
    entity: "Наблюдаемый объект",
    state: "Точное ожидаемое состояние",
    maxAge: "Максимальная давность (секунды, 1–3600)",
    start: "Начало",
    end: "Конец",
    timezone: "Часовой пояс",
    all: "Все условия",
    any: "Любое условие",
    add: "Добавить условие",
    remove: "Удалить",
    replace: "Заменить условие",
    unsupported:
      "Это сохранённое условие не поддерживается редактором. Для изменения явно замените его.",
    depth: "Достигнута максимальная глубина условий.",
    nodes: "Достигнуто максимальное число условий.",
    conjunction: "Группа должна содержать хотя бы одно условие.",
    entityHint: "Доступны только объекты из разрешённого списка наблюдения.",
    stateHint:
      "unknown и unavailable нельзя указывать как ожидаемые состояния.",
    modes: {
      normal: "Обычный",
      holidays: "Каникулы / праздники",
      guests: "Гости",
      ill: "Болезнь",
      vacation: "Отпуск",
    },
  },
  uk: {
    help: "Як працюють умови",
    timeWindow: "Часовий інтервал",
    condition: "Пропустити розпорядок, якщо",
    hint: "Умови лише спостерігають за дозволеними об’єктами Home Assistant і ніколи ними не керують. Невідоме або застаріле спостереження залишається невідомим, навіть при запереченні.",
    templateHint:
      "Перевіряється один раз під час запуску. Якщо умова істинна, усі кроки пропускаються. Невідомий результат не спричиняє пропуск.",
    none: "Без умови",
    kind: "Тип умови",
    negate: "Інвертувати результат",
    mode: "Режим дому",
    entity: "Об’єкт спостереження",
    state: "Точний очікуваний стан",
    maxAge: "Максимальна давність (секунди, 1–3600)",
    start: "Початок",
    end: "Кінець",
    timezone: "Часовий пояс",
    all: "Усі умови",
    any: "Будь-яка умова",
    add: "Додати умову",
    remove: "Видалити",
    replace: "Замінити умову",
    unsupported:
      "Ця збережена умова не підтримується редактором. Для зміни явно замініть її.",
    depth: "Досягнуто максимальної глибини умов.",
    nodes: "Досягнуто максимальної кількості умов.",
    conjunction: "Група має містити щонайменше одну умову.",
    entityHint: "Доступні лише об’єкти з дозволеного списку спостереження.",
    stateHint: "unknown і unavailable не можна вказувати як очікувані стани.",
    modes: {
      normal: "Звичайний",
      holidays: "Канікули / свята",
      guests: "Гості",
      ill: "Хвороба",
      vacation: "Відпустка",
    },
  },
};
const MODES = ["normal", "holidays", "guests", "ill", "vacation"],
  KINDS = ["mode", "entity_state", "time_window", "all", "any"];
const clone = (value) =>
  value == null ? value : JSON.parse(JSON.stringify(value));
const copyFor = (language) =>
  CONDITION_COPY[language?.split?.("-")[0]] || CONDITION_COPY.en;
const make = (tag, value, className) => {
  const node = document.createElement(tag);
  if (value != null) node.textContent = String(value);
  if (className) node.className = className;
  return node;
};
const labelled = (label, control) => {
  const node = make("label", label);
  if (control.type === "checkbox") node.className = "check";
  node.append(control);
  return node;
};
const action = (label, handler, disabled = false) => {
  const node = make("button", label);
  node.type = "button";
  node.disabled = disabled;
  node.addEventListener("click", handler);
  return node;
};
const emptyNode = () => ({ kind: "mode", mode: "normal", negate: false }),
  groupNode = (kind) => ({ kind, conditions: [emptyNode()], negate: false });
const at = (root, path) =>
  path.reduce((value, index) => value?.conditions?.[index], root);
const replaceAt = (root, path, value) => {
  if (!path.length) return value;
  const result = clone(root);
  let cursor = result;
  for (let i = 0; i < path.length - 1; i++) cursor = cursor.conditions[path[i]];
  cursor.conditions[path[path.length - 1]] = value;
  return result;
};
const countNodes = (node) =>
  !node || typeof node !== "object"
    ? 0
    : 1 +
      (Array.isArray(node.conditions)
        ? node.conditions.reduce((n, child) => n + countNodes(child), 0)
        : 0);
const CONDITION_FIELDS = {
  mode: ["kind", "negate", "mode"],
  entity_state: ["kind", "negate", "entity_id", "state", "max_age_seconds"],
  time_window: ["kind", "negate", "start", "end", "timezone"],
  all: ["kind", "negate", "conditions"],
  any: ["kind", "negate", "conditions"],
};
function shapeSupported(node, depth = 1, budget = { n: 0 }) {
  if (
    !node ||
    typeof node !== "object" ||
    Array.isArray(node) ||
    !KINDS.includes(node.kind) ||
    depth > 3 ||
    ++budget.n > 20
  )
    return false;
  if (
    Object.keys(node).some((key) => !CONDITION_FIELDS[node.kind].includes(key))
  )
    return false;
  if ("negate" in node && typeof node.negate !== "boolean") return false;
  if (node.kind === "all" || node.kind === "any") {
    return (
      Array.isArray(node.conditions) &&
      node.conditions.length >= 1 &&
      node.conditions.length <= 19 &&
      node.conditions.every((child) => shapeSupported(child, depth + 1, budget))
    );
  }
  if (node.kind === "mode") return MODES.includes(node.mode);
  if (node.kind === "entity_state")
    return (
      typeof node.entity_id === "string" &&
      typeof node.state === "string" &&
      (!("max_age_seconds" in node) ||
        typeof node.max_age_seconds === "number" ||
        typeof node.max_age_seconds === "string")
    );
  return (
    typeof node.start === "string" &&
    typeof node.end === "string" &&
    typeof node.timezone === "string"
  );
}
export { CONDITION_COPY };

export function renderConditionForm({
  value = null,
  onChange = () => {},
  language = "en",
  allowlist = [],
  timezone = "UTC",
  disabled = false,
  isStale = () => false,
} = {}) {
  const copy = copyFor(language),
    fieldset = make("fieldset", "", "condition-editor");
  fieldset.append(
    make("legend", copy.condition),
    make("p", copy.templateHint, "sub"),
  );
  const help = make("details");
  help.append(make("summary", copy.help), make("p", copy.hint, "sub"));
  fieldset.append(help);
  let draft = clone(value),
    version = 0,
    body = null;
  const live = (v) =>
    fieldset.isConnected && v === version && !disabled && !isStale();
  const notify = (next, v, rerender = true) => {
    if (!live(v)) return;
    draft = clone(next);
    onChange(clone(draft));
    if (rerender) render();
  };
  const edit = (path, fn, v, rerender = false) => {
    if (!live(v)) return;
    const next = clone(draft);
    fn(path.length ? at(next, path) : next);
    notify(next, v, rerender);
  };
  const field = (node) => {
    node.disabled = Boolean(disabled || isStale());
    return node;
  };
  const kindSelect = (node, path, v, depth = 1) => {
    const select = document.createElement("select");
    select.dataset.conditionField = "kind";
    select.dataset.conditionPath = path.join(".");
    select.setAttribute("aria-label", copy.kind);
    if (!path.length) {
      const none = make("option", copy.none);
      none.value = "";
      select.append(none);
    }
    const isGroup = node?.kind === "all" || node?.kind === "any";
    const groupBlocked = () =>
      !isGroup && (depth >= 3 || countNodes(draft) - countNodes(node) + 2 > 20);
    for (const kind of KINDS) {
      const option = make(
        "option",
        kind === "mode"
          ? copy.mode
          : kind === "entity_state"
            ? copy.entity
            : kind === "time_window"
              ? copy.timeWindow
              : kind === "all"
                ? copy.all
                : copy.any,
      );
      option.value = kind;
      option.disabled = (kind === "all" || kind === "any") && groupBlocked();
      select.append(option);
    }
    select.value = node?.kind || "";
    field(select).addEventListener("change", () => {
      if (!live(v)) return;
      const kind = select.value;
      if ((!kind && path.length) || (kind && !KINDS.includes(kind))) return;
      if ((kind === "all" || kind === "any") && groupBlocked()) return;
      if (kind === node?.kind) return;
      const currentNode = at(draft, path);
      const next =
        kind === "all" || kind === "any"
          ? isGroup
            ? { ...clone(currentNode), kind }
            : groupNode(kind)
          : kind === "mode"
            ? { kind, mode: "normal", negate: false }
            : kind === "entity_state"
              ? {
                  kind,
                  entity_id: allowlist[0] || "",
                  state: "",
                  max_age_seconds: 120,
                  negate: false,
                }
              : kind === "time_window"
                ? {
                    kind,
                    start: "08:00",
                    end: "09:00",
                    timezone,
                    negate: false,
                  }
                : null;
      notify(replaceAt(draft, path, next), v, true);
    });
    return select;
  };
  const renderNode = (path, depth, v) => {
    const node = at(draft, path),
      section = make("section", "", "condition-node");
    section.dataset.conditionPath = path.join(".");
    section.append(labelled(copy.kind, kindSelect(node, path, v, depth)));
    if (
      !node ||
      typeof node !== "object" ||
      !KINDS.includes(node.kind) ||
      !shapeSupported(node)
    ) {
      section.append(make("div", copy.unsupported, "notice"));
      section.append(
        action(
          copy.replace,
          () => {
            if (live(v))
              notify(
                replaceAt(draft, path, {
                  kind: "mode",
                  mode: "normal",
                  negate: Boolean(node?.negate),
                }),
                v,
                true,
              );
          },
          disabled || isStale(),
        ),
      );
      return section;
    }
    const negate = document.createElement("input");
    negate.type = "checkbox";
    negate.className = "condition-negate";
    negate.dataset.conditionField = "negate";
    negate.dataset.conditionPath = path.join(".");
    negate.checked = node.negate === true;
    field(negate).addEventListener("change", () =>
      edit(
        path,
        (cur) => {
          cur.negate = negate.checked;
        },
        v,
        true,
      ),
    );
    section.append(labelled(copy.negate, negate));
    if (node.kind === "mode") {
      const select = document.createElement("select");
      select.dataset.conditionField = "mode";
      select.dataset.conditionPath = path.join(".");
      for (const mode of MODES) {
        const option = document.createElement("option");
        option.value = mode;
        option.textContent = copy.modes[mode];
        select.append(option);
      }
      select.value = node.mode;
      field(select).addEventListener("change", () =>
        edit(
          path,
          (cur) => {
            cur.mode = select.value;
          },
          v,
          true,
        ),
      );
      section.append(labelled(copy.mode, select));
    } else if (node.kind === "entity_state") {
      const select = document.createElement("select");
      select.dataset.conditionField = "entity_id";
      select.dataset.conditionPath = path.join(".");
      for (const id of allowlist) {
        const option = document.createElement("option");
        option.value = id;
        option.textContent = id;
        select.append(option);
      }
      if (node.entity_id && !allowlist.includes(node.entity_id)) {
        const option = document.createElement("option");
        option.value = node.entity_id;
        option.textContent = node.entity_id;
        select.append(option);
      }
      select.value = node.entity_id || "";
      field(select).addEventListener("change", () =>
        edit(
          path,
          (cur) => {
            cur.entity_id = select.value;
          },
          v,
          true,
        ),
      );
      const state = document.createElement("input");
      state.type = "text";
      state.value = node.state ?? "";
      state.maxLength = 100;
      state.dataset.conditionField = "state";
      state.dataset.conditionPath = path.join(".");
      field(state).addEventListener("input", () =>
        edit(
          path,
          (cur) => {
            cur.state = state.value;
          },
          v,
          false,
        ),
      );
      const age = document.createElement("input");
      age.type = "number";
      age.min = "1";
      age.max = "3600";
      age.step = "1";
      age.value = node.max_age_seconds == null ? 120 : node.max_age_seconds;
      age.dataset.conditionField = "max_age_seconds";
      age.dataset.conditionPath = path.join(".");
      field(age).addEventListener("input", () =>
        edit(
          path,
          (cur) => {
            const raw = age.value;
            cur.max_age_seconds =
              /^[0-9]+$/.test(raw) && Number(raw) >= 1 && Number(raw) <= 3600
                ? Number(raw)
                : raw;
          },
          v,
          false,
        ),
      );
      section.append(
        labelled(copy.entity, select),
        labelled(copy.state, state),
        labelled(copy.maxAge, age),
        make("p", `${copy.entityHint} ${copy.stateHint}`, "sub"),
      );
    } else if (node.kind === "time_window") {
      for (const [key, label, type] of [
        ["start", copy.start, "time"],
        ["end", copy.end, "time"],
        ["timezone", copy.timezone, "text"],
      ]) {
        const input = document.createElement("input");
        input.type = type;
        input.value = node[key] ?? (key === "timezone" ? timezone : "");
        input.dataset.conditionField = key;
        input.dataset.conditionPath = path.join(".");
        field(input).addEventListener("input", () =>
          edit(
            path,
            (cur) => {
              cur[key] = input.value;
            },
            v,
            false,
          ),
        );
        section.append(labelled(label, input));
      }
    } else {
      section.append(make("strong", node.kind === "all" ? copy.all : copy.any));
      const children = node.conditions;
      for (let i = 0; i < children.length; i++) {
        const row = renderNode(path.concat(i), depth + 1, v);
        row.append(
          action(
            copy.remove,
            () =>
              edit(
                path,
                (cur) => {
                  if (cur.conditions.length > 1) cur.conditions.splice(i, 1);
                },
                v,
                true,
              ),
            disabled || isStale() || children.length <= 1,
          ),
        );
        section.append(row);
      }
      const blocked = depth >= 3 || countNodes(draft) >= 20;
      section.append(
        action(
          copy.add,
          () =>
            edit(
              path,
              (cur) => {
                if (depth < 3 && countNodes(draft) < 20)
                  cur.conditions.push(emptyNode());
              },
              v,
              true,
            ),
          disabled || isStale() || blocked,
        ),
      );
      if (depth >= 3) section.append(make("p", copy.depth, "sub"));
      else if (blocked) section.append(make("p", copy.nodes, "sub"));
      if (!children.length)
        section.append(make("p", copy.conjunction, "notice"));
    }
    return section;
  };
  const render = () => {
    version += 1;
    const v = version;
    if (body) body.remove();
    body = document.createElement("div");
    body.className = "condition-body";
    if (!shapeSupported(draft)) {
      if (draft == null)
        body.append(labelled(copy.kind, kindSelect(null, [], v)));
      else {
        body.append(make("div", copy.unsupported, "notice"));
        body.append(
          action(
            copy.replace,
            () => {
              if (live(v)) notify(null, v, true);
            },
            disabled || isStale(),
          ),
        );
      }
    } else body.append(renderNode([], 1, v));
    fieldset.append(body);
  };
  render();
  return fieldset;
}
