"""Conservative natural commands. Every proposed action still goes through Engine."""

import re
from dataclasses import dataclass
from datetime import datetime

from ..const import PRIVILEGED
from ..domain.deadlines import extract_due, parse_due
from ..domain.validation import DomainError


@dataclass(frozen=True)
class Intent:
    action: str
    payload: dict


EN_LOWER = "`qwertyuiop[]asdfghjkl;'zxcvbnm,./"
RU_LOWER = "ёйцукенгшщзхъфывапролджэячсмитьбю."
EN_UPPER = '~QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>?'
RU_UPPER = "ЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,"

TRANS = str.maketrans(EN_LOWER + EN_UPPER, RU_LOWER + RU_UPPER)


def layout_trans(text: str) -> str:
    return text.translate(TRANS)


def normalize(value: str) -> str:
    val = value.casefold().replace("ё", "е")
    val = re.sub(r"([a-zа-яіїєґ])\1{2,}", r"\1", val)
    return " ".join(val.split()).strip(" .?!,;:~`#@$%^&*()-_+=\\/|[]{}\"'")


def find_member(state: dict, value: str) -> str:
    lowered = normalize(value)
    cleaned = re.sub(r"^(?:для|кому|for)\s+", "", lowered)
    matches = [
        m["id"]
        for m in state["members"].values()
        if m["active"]
        and (
            cleaned
            in {
                normalize(m["id"]),
                normalize(m["name"]),
                *(normalize(a) for a in m.get("aliases", [])),
            }
            or lowered
            in {
                normalize(m["id"]),
                normalize(m["name"]),
                *(normalize(a) for a in m.get("aliases", [])),
            }
        )
    ]
    if not matches:
        stems = {}
        for m in state["members"].values():
            if not m["active"]:
                continue
            for name in [m["id"], m["name"], *m.get("aliases", [])]:
                stem = re.sub(r"[аеиоуєюяы]$", "", normalize(name))
                if len(stem) >= 3:
                    stems.setdefault(stem, set()).add(m["id"])
        cand_stem = re.sub(r"[аеиоуєюяы]$", "", cleaned)
        if cand_stem in stems:
            matches = sorted(stems[cand_stem])
    if len(matches) != 1:
        raise DomainError("unknown_member" if not matches else "ambiguous_member")
    return matches[0]


def task_target(view, explicit, refs):
    available = {task["id"] for task in view["tasks"]}
    candidates = {explicit.upper()} if explicit else {ref for ref in refs if ref.startswith("T")}
    if len(candidates) != 1:
        raise DomainError("context_required")
    target = next(iter(candidates))
    if target not in available:
        raise DomainError("not_found")
    return target


READ_COURT_RE = re.compile(
    r"^(?:за\s+что\s+минусы(?:\s+у\s+детей)?|почему\s+минусы|почему\s+сняли\s+баллы|за\s+что\s+штраф[ы]?|"
    r"за\s+що\s+мінуси(?:\s+у\s+дітей)?|чому\s+мінуси|чому\s+зняли\s+бали|за\s+що\s+штраф[и]?|"
    r"why\s+(?:the\s+)?penalties|why\s+minus|scores|points|stats|statistics|stat|"
    r"статистика(?:\s+детей|\s+дітей|\s+баллов|\s+балів)?|стата|итоги\s+недели|підсумки\s+тижня|"
    r"семейный\s+суд|сімейний\s+суд|суд|штрафы|штрафи|баллы|бали|очки|рейтинг(?:\s+детей|\s+дітей)?|"
    r"покажи\s+(?:баллы|бали|очки|штрафы|штрафи|статистику|суд)|баланс\s+(?:баллов|балів|очков))$",
    re.I,
)

READ_TASKS_RE = re.compile(
    r"^(?:какие\s+задачи|список\s+задач|мои\s+задачи|статус\s+задач|статус\s+заданий|покажи\s+задачи|покажи\s+задания|"
    r"покажи\s+список\s+задач|актуальные\s+задачи|активные\s+задачи|текущие\s+задачи|задачи|задания|дела|что\s+делать|чо\s+делать|"
    r"что\s+по\s+задачам|что\s+надо\s+сделать|что\s+нужно\s+сделать|список\s+дел|покажи\s+дела|все\s+задачи|открытые\s+задачи|"
    r"напомни\s+задачи|напомни\s+дела|что\s+там\s+по\s+задачам|какие\s+дела|какие\s+задания|таски|глянуть\s+задачи|"
    r"посмотреть\s+задачи|задачки|дела\s+на\s+сегодня|"
    r"мої\s+завдання|список\s+завдань|яки\s+завдання|які\s+завдання|покажи\s+завдання|активні\s+завдання|поточні\s+завдання|"
    r"завдання|що\s+робити|шо\s+робити|що\s+по\s+завданнях|шо\s+по\s+завданнях|що\s+треба\s+зробити|шо\s+треба\s+зробити|"
    r"список\s+справ|покажи\s+справи|справи|мої\s+справи|"
    r"відкриті\s+завдання|актуальні\s+завдання|подивитися\s+завдання|глянути\s+справи|"
    r"my\s+tasks|tasks|tasks\s+status|show\s+tasks|task\s+list|todo|todo\s+list|what\s+to\s+do|current\s+tasks|active\s+tasks|all\s+tasks)$",
    re.I,
)

READ_SHOPPING_RE = re.compile(
    r"^(?:список\s+покупок|что\s+купить|чо\s+купить|покупки|покажи\s+покупки|покажи\s+список\s+покупок|шоппинг|список\s+в\s+магазин|"
    r"что\s+нужно\s+купить|что\s+надо\s+купить|что\s+докупить|что\s+брать\s+в\s+магазине|надо\s+купить|глянуть\s+покупки|"
    r"посмотреть\s+покупки|в\s+магазин|что\s+в\s+покупках|список\s+продуктов|продукты|купить|"
    r"що\s+купити|шо\s+купити|шопінг|шопинг|покажи\s+шопінг|покажи\s+шопинг|список\s+до\s+магазину|що\s+треба\s+купити|"
    r"шо\s+треба\s+купити|що\s+придбати|шо\s+придбати|"
    r"подивитися\s+покупки|до\s+магазину|продукти|список\s+продуктів|"
    r"shopping|shopping\s+list|what\s+to\s+buy|groceries|grocery\s+list|buy\s+list|show\s+shopping)$",
    re.I,
)

READ_ALARMS_RE = re.compile(
    r"^(?:будильники|список\s+будильников|какие\s+будильники|покажи\s+будильники|мои\s+будильники|активные\s+будильники|будильник|"
    r"когда\s+подъем|подъем|будильник[и]?\s+на\s+завтра|"
    r"список\s+будильників|які\s+будильники|покажи\s+будильник[и]?|мої\s+будильники|активні\s+будильники|коли\s+підйом|підйом|"
    r"alarms|alarm\s+list|show\s+alarms|active\s+alarms|my\s+alarms|alarm)$",
    re.I,
)

READ_CALENDAR_RE = re.compile(
    r"^(?:календарь|календар|планы|плани|расписание|розклад|какие\s+планы|які\s+плани|планы\s+на\s+сегодня|плани\s+на\s+сьогодні|"
    r"планы\s+на\s+неделю|плани\s+на\s+тиждень|события|події|покажи\s+календарь|покажи\s+календар|что\s+запланировано|що\s+заплановано|"
    r"calendar|schedule|plans|events|agenda|show\s+calendar)$",
    re.I,
)

READ_ROUTINES_RE = re.compile(
    r"^(?:рутины|рутини|привычки|звички|расписание\s+рутин|розклад\s+рутин|мои\s+рутины|мої\s+рутини|покажи\s+рутины|покажи\s+рутини|"
    r"регулярные\s+дела|регулярні\s+справи|routines|habits|show\s+routines|daily\s+routines)$",
    re.I,
)

READ_REWARDS_RE = re.compile(
    r"^(?:награды|нагороди|винагороди|магазин\s+наград|магазин\s+винагород|каталог\s+наград|каталог\s+винагород|подарки|подарунки|"
    r"что\s+можно\s+купить\s+за\s+баллы|що\s+можна\s+купити\s+за\s+бали|витрина\s+наград|призы|призи|"
    r"rewards|rewards\s+shop|store|presents|prizes)$",
    re.I,
)

READ_WALLET_RE = re.compile(
    r"^(?:кошелек|кошелёк|гаманець|мой\s+кошелек|мой\s+кошелёк|мій\s+гаманець|баланс\s+кошелька|баланс\s+гаманця|"
    r"сколько\s+у\s+меня\s+баллов|скільки\s+у\s+мене\s+балів|баланс|wallet|my\s+wallet)$",
    re.I,
)

READ_WATCHLIST_RE = re.compile(
    r"^(?:цены|ціни|отслеживание\s+цен|відстеження\s+цін|вишлист|вішліст|список\s+цен|список\s+цін|мониторинг\s+цен|моніторинг\s+цін|"
    r"мои\s+ссылки|мої\s+посилання|watchlist|prices|price\s+watch|tracked\s+prices)$",
    re.I,
)

READ_PATTERNS = [
    (
        "read.mine",
        re.compile(r"^(?:мои\s+(?:задачи|дела)|мої\s+(?:завдання|справи)|my\s+tasks)$", re.I),
    ),
    ("read.court", READ_COURT_RE),
    ("read.tasks", READ_TASKS_RE),
    ("read.shopping", READ_SHOPPING_RE),
    ("read.alarms", READ_ALARMS_RE),
    ("read.calendar", READ_CALENDAR_RE),
    ("read.routines", READ_ROUTINES_RE),
    ("read.rewards", READ_REWARDS_RE),
    ("read.wallet", READ_WALLET_RE),
    ("read.watchlist", READ_WATCHLIST_RE),
]

SHOPPING_ADD_RE = re.compile(
    r"^(?:купи(?:ть)?|надо\s+купить|нужно\s+купить|добавь\s+(?:в|до)\s+(?:покуп(?:ки|ок)|списо?к\s+покупок)|"
    r"купити|треба\s+купити|потрібно\s+купити|додай\s+(?:в|у|до)\s+(?:покуп(?:ки|ок)|списо?к\s+покупок)|"
    r"buy|add\s+to\s+shopping)\s+(.+)$",
    re.I,
)

SHOPPING_PURCHASE_RE = re.compile(
    r"^(?:(?:купил[аи]?|придбав|придбала|придбано|куплено|bought|purchased)\s+(S\d{6})|"
    r"(S\d{6})\s+(?:купил[аи]?|придбав|придбала|придбано|куплено|bought|purchased))$",
    re.I,
)

TASK_CREATE_PATTERNS = [
    re.compile(
        r"^(?:назначь(?:те)?|назначить|постав(?:ь(?:те)?|ить|те|ити)?|признач(?:те)?|призначити|"
        r"задай(?:те)?|задати|дай(?:те)?|дати|assign)\s+"
        r"(.{1,80}?)\s+(?:задач[ауе]|завдання|task)\s*[:.]?\s+(.+)$",
        re.I,
    ),
    re.compile(
        r"^(?:(?:постав(?:ь(?:те)?|ить|те|ити)?|назначь(?:те)?|назначить|"
        r"создай(?:те)?|создать|добавь(?:те)?|добавить|дай(?:те)?|дать|"
        r"створи(?:ть)?|додай(?:те)?|додати|признач(?:те)?|призначити|"
        r"add|create|give|assign)\s+)?"
        r"(?:задач[ауе]|завдання|task)\s+"
        r"(?:(?:для|кому|for)\s+)?(.+)$",
        re.I,
    ),
    re.compile(r"^(.{1,80}?)\s+(?:задача|завдання|task)\s*[:.]?\s+(.+)$", re.I),
]


# A minus before a number can belong to an invalid deadline ("in - 2 days").
# Do not move that validation failure into the recipient slot.
_ASSIGNMENT_SEPARATOR = re.compile(r":(?!\d)|\.(?=\s|$)|(?<=\s)-(?=\s+(?!\d)\S|$)|[–—]")


def assignment_recipient(content: str) -> tuple[int, int] | None:
    """Locate an explicit full recipient slot, without resolving or guessing a name.

    Offsets refer to the unchanged input. Without a separator after a task-first
    header, an unknown multiword name cannot be distinguished from the title.
    The strict parser may still resolve a configured name in that form; a model
    repair must not treat its first word as proof of the complete recipient.
    """
    value = content.strip()
    if re.match(r"^(?:не\b|not\b|do\s+not\b|don't\b)", value, re.I):
        return None
    offset = len(content) - len(content.lstrip())
    for index, pattern in enumerate(TASK_CREATE_PATTERNS):
        match = pattern.fullmatch(value)
        if match is None:
            continue
        start, end = match.span(1)
        if index == 1:
            separator = _ASSIGNMENT_SEPARATOR.search(match[1])
            if separator is None or not match[1][separator.end() :].strip():
                return None
            end = start + separator.start()
        candidate = value[start:end]
        start += len(candidate) - len(candidate.lstrip())
        end -= len(candidate) - len(candidate.rstrip())
        if not 1 <= end - start <= 80:
            return None
        return offset + start, offset + end
    return None


def _task_member_prefix(state, content):
    """Prefer a complete configured recipient over a matching first-word ID."""
    separator = _ASSIGNMENT_SEPARATOR.search(content)
    if separator is not None:
        candidate = content[: separator.start()].strip()
        title = content[separator.end() :].strip()
        if not candidate or not title:
            raise DomainError("ambiguous_command")
        # An explicit delimiter bounds the whole name. Never rescue an unknown
        # full slot by interpreting its trailing name words as the task title.
        return find_member(state, candidate), title
    boundaries = [match for match in re.finditer(r"\s+", content) if match.start() <= 80]
    for boundary in reversed(boundaries):
        candidate = content[: boundary.start()].rstrip(" .:")
        title = content[boundary.end() :].lstrip(" .:")
        if not title:
            continue
        try:
            member = find_member(state, candidate)
        except DomainError as error:
            if error.code == "unknown_member":
                continue
            raise
        return member, title
    raise DomainError("unknown_member")


TASK_REVISE_RE = re.compile(
    r"^(?:(?:установи(?:ть)?|постав(?:ить)?|измени(?:ть)?|смени(?:ть)?|перенеси(?:ть)?)\s+срок|"
    r"(?:встанови(?:ти)?|постав(?:ити)?|зміни(?:ти)?|перенеси(?:ти)?)\s+термін|"
    r"set\s+(?:the\s+)?deadline|change\s+(?:the\s+)?deadline|"
    r"дедлайн|срок|термін|deadline|"
    r"перенеси|перенести|продли|продлите|подовж(?:и|іть)|продовж(?:и|іть)|extend)\s+"
    r"(?:(?:задач[уие]|завдання|task|для|for)\s+)?\s*(T\d{6,})?\s*[:,-]?\s*(.+)$",
    re.I,
)

TASK_COMPLETE_SUBMIT_RE = re.compile(
    r"^(?:(T\d{6})\s+(?:готово|выполнен[оа]?|сделан[оа]?|зроблен[оа]?|виконан[оа]?|done|complete[d]?|принят[оа]?|схвален[оа]?|approved?)|"
    r"(?:готово|выполнен[оа]?|сделан[оа]?|зроблен[оа]?|виконан[оа]?|done|complete[d]?|принят[оа]?|схвален[оа]?|approved?)\s+(T\d{6})|"
    r"(.{1,80}?)\s+(?:выполнил[а]?|сделал[а]?|викона[вл]а?|зроби[вл]а?|completed)\s+(T\d{6})|"
    r"(T\d{6})\s+(.{1,80}?)\s+(?:выполнил[а]?|сделал[а]?|викона[вл]а?|зроби[вл]а?|completed))$",
    re.I,
)


def parse(state, view, content: str, now: datetime, refs=()) -> Intent | None:
    value = content.strip()
    n = normalize(value)
    timezone = state["settings"].get("timezone", "UTC")

    for intent_name, pat in READ_PATTERNS:
        if pat.search(n):
            return Intent(intent_name, {})

    if not re.search(r"[а-яіїєґ]", value, re.I):
        trans = normalize(layout_trans(value))
        for intent_name, pat in READ_PATTERNS:
            if pat.search(trans):
                return Intent(intent_name, {})

    shop_pur = SHOPPING_PURCHASE_RE.match(value)
    if shop_pur:
        sid = shop_pur.group(1) or shop_pur.group(2)
        return Intent("shopping.purchase", {"id": sid.upper()})

    shop_add = SHOPPING_ADD_RE.match(value)
    if not shop_add:
        shop_add = re.fullmatch(
            r"(?:добавь|додай)\s+(.+?)\s+(?:в|у|до)\s+(?:покупки|список\s+покупок|список\s+покупок)",
            value,
            re.I,
        )
    if shop_add:
        raw_item = shop_add.group(1).strip()
        parts = [p.strip() for p in raw_item.split("|")]
        if len(parts) > 3:
            raise DomainError("invalid_field", "shopping")
        name = parts[0]
        qty = 1.0
        unit = ""
        if len(parts) > 1:
            try:
                qty = float(parts[1].replace(",", "."))
            except ValueError:
                raise DomainError("invalid_field", "quantity") from None
        if len(parts) > 2:
            unit = parts[2]
        return Intent("shopping.add", {"name": name, "quantity": qty, "unit": unit})

    purchase = re.fullmatch(r"(?:купил[аи]?|придбав|придбала|bought|purchased)\s+(.+)", value, re.I)
    if purchase:
        from .task_commands import shopping_target

        return Intent("shopping.purchase", {"id": shopping_target(view, purchase[1].strip())})

    reminder = re.fullmatch(
        r"(?:напомни\s+мне|нагадай\s+мені|remind\s+me\s+to)\s+(.+)", value, re.I
    )
    if reminder:
        title, due = extract_due(reminder[1], now, timezone)
        if not title or due is None:
            raise DomainError("invalid_deadline")
        return Intent(
            "tasks.create",
            {
                "title": title,
                "assignee": view["actor"],
                "due_at": due,
                "personal": True,
                "report_type": "none",
                "reminder_minutes": 0,
                "grace_minutes": 0,
                "penalty": 0,
            },
        )

    # Explicit edit verbs take precedence over the broad "name task title"
    # creation shape. Assignment titles containing a move verb remain creation.
    revise = TASK_REVISE_RE.match(value)
    if revise:
        target = task_target(view, revise.group(1), refs)
        task = next(t for t in view["tasks"] if t["id"] == target)
        return Intent(
            "tasks.revise",
            {
                "id": target,
                "revision": task["revision"],
                "due_at": parse_due(revise.group(2), now, timezone),
            },
        )

    for index, pat in enumerate(TASK_CREATE_PATTERNS):
        create = pat.match(value)
        if create:
            if index == 1:
                member, task_text = _task_member_prefix(state, create.group(1))
            else:
                member, task_text = find_member(state, create.group(1)), create.group(2)
                task_text = re.sub(r"^(?:[:.]\s*|[–—]\s*|-\s+)", "", task_text)
                if not task_text.strip():
                    raise DomainError("ambiguous_command")
            title, due = extract_due(task_text, now, timezone)
            return Intent("tasks.create", {"assignee": member, "title": title, "due_at": due})

    comp = TASK_COMPLETE_SUBMIT_RE.match(value)
    short_done = re.fullmatch(r"готово|зроблено|виконано|done", value, re.I) and refs
    if comp or short_done:
        groups = comp.groups() if comp else (None,) * 6
        explicit_id = groups[0] or groups[1] or groups[3] or groups[4]
        member_name = groups[2] or groups[5]
        target = task_target(view, explicit_id, refs)
        task = next(t for t in view["tasks"] if t["id"] == target)
        if member_name:
            member = find_member(state, member_name)
            if task["assignee"] != member:
                raise DomainError("ambiguous_command")
        if view["role"] not in PRIVILEGED:
            return Intent("tasks.submit", {"id": target, "report": value})
        return Intent("tasks.complete", {"id": target})

    return None
