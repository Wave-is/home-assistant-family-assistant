# School / Школа / Школа

Development feature: a private weekly timetable, lesson materials and a 14-day
agenda, explicit private homework, reviewed backpack starts and opt-in private
preparation reminders. Enable **School timetable** in Family Assistant options and add the
**School** card (`custom:family-school-card`). The visual card editor selects the
household and language; the authenticated account determines access.

## English

Parents and owners create one active timetable per child. Choose the child, a
title, first date, optional last date, and dates without lessons. Add each weekly
lesson with weekday, start/end, subject, optional room and materials. Times are
wall-clock times in the household's configured time zone. Lessons on the same
day cannot overlap; back-to-back lessons are allowed. Exception dates suppress
all lessons for those local dates.

Review the exact child, dates and every lesson before saving. Editing replaces
the complete timetable. The child cannot be changed on an existing timetable;
archive it with a reason and create a separate record instead. An archive keeps
parent-visible history but removes that timetable from the child's view. A second
active timetable for the same child is rejected, even for another date range.

Children see only their own currently authorized timetable and upcoming materials,
never a sibling's schedule or parent history. Other adult and guest roles do not
receive school data. Any change to the child's member record invalidates the
previous identity binding: a parent must review and save that timetable again
before it reappears for the child. Old editors cannot silently follow a new
identity or overwrite a newer timetable. Retry after a lost response sends the
same reviewed operation, not a second creation.

An optional **Backpack routine** is a reference to a current enabled template
assigned to that child. Saving the link never starts or modifies a routine. Use
**Review and start preparation** for an actual school day today or tomorrow;
check the child, local date, timetable version and routine before confirming.
One timetable/date can start preparation only once, even after completion.
An unrelated active run is never silently adopted. Continue its steps in the
separate Routines card; a recorded start does not mean the bag is packed.
A changed, disabled or unauthorized
template no longer appears as a usable link; a parent must review its replacement.
An unavailable stored version is shown explicitly in the editor. Choose no routine
or a current replacement before saving; renaming the timetable never silently
removes its stored link.

Enable **Tasks** to add homework in School. A parent may choose a child; a child
can add only their own task. Review the title, optional local deadline/checklist/
lesson, reminder lead and grace period. This creates one ordinary private task
with zero penalty, not a second homework engine. The Tasks card handles starting,
checklist completion, text reports and parent review. Parents change the title,
deadline and reminder policy in School, not the generic task editor. The child
cannot be reassigned. Same-identity edits retain progress; explicitly rebinding
after a child profile change resets progress, issues a fresh private assignment
and hides the previous profile's report/review from the new child. Parents retain
that report in private history; this is not data erasure. Already-created work remains in Tasks even
after its timetable is archived or School is disabled.

Existing private task and routine notifications apply; school timetables and
homework content are not published to a family group or automatically sent to
LLM/search. This stage does **not** create homework automatically, publish a HA
calendar, import photographs/calendars or control devices. Preparation reminders
require the separate explicit controls described below.

For preparation reminders, the owner enables the global switch in integration
**Settings**, chooses the school day (0) or previous day (1) and a household-local
`HH:MM` time. Defaults are **off**, previous day, `20:00`. Each parent or child
then opens **School preparation reminders** in the School card and selects
**Enable for me**, checks the named child/recipient and saves. A parent subscribes
only their own personal chat; a child only their own timetable. Nobody silently
enrolls another recipient. Each recipient must first link their personal Telegram
chat to their family member. A saved preference while global reminders or Routines
are off does not schedule a message.

An intent is created only within five minutes of the configured time, for an
actual school day with a current approved timetable and pinned usable backpack
routine. No missed-window backlog is generated. Quiet hours and transport retry
may defer a created message, but it expires at the first lesson. Nonexistent DST
times are skipped; repeated times use only the first occurrence. A changed source,
member identity, subscription or policy invalidates old queued content. Starting
that timetable/date's preparation suppresses its reminder. There is at most one
intent per recipient/timetable/day, including after edits or re-enabling: there is
no same-day automatic replacement. The message does not start a routine, create
homework, control a device or award/deduct points.

## Русский

Включите **Школьное расписание** и добавьте карточку **Школа**. Родитель или
владелец создаёт одно активное расписание на ребёнка: название, период,
даты без уроков и уроки по дням недели. Для урока укажите время начала и конца,
предмет, при необходимости кабинет и материалы. Время относится к часовому
поясу семьи. Пересечения уроков запрещены; соседние интервалы допустимы.
Исключение отменяет все уроки указанной местной даты.

Перед сохранением проверьте ребёнка, даты и весь список уроков. Редактирование
заменяет расписание целиком. Переназначить существующий документ другому ребёнку
нельзя: архивируйте его с причиной и создайте новый. Архив сохраняет историю для
родителей, но скрывается от ребёнка. Второе активное расписание тому же ребёнку
не создаётся даже для другого периода.

Ребёнок читает только собственное актуальное расписание и материалы на ближайшие
14 дней. Чужие расписания и родительская история недоступны; роли «взрослый» и
«гость» школьных данных не получают. Любое изменение карточки ребёнка сбрасывает
привязку прежней версии: родитель должен снова проверить и сохранить расписание.
Устаревшая форма не перезаписывает новые данные. После потери ответа кнопка
повтора отправляет ту же проверенную операцию, а не создаёт дубль.

Необязательная **Рутина сборки рюкзака** ссылается на текущий включённый шаблон,
назначенный ребёнку. Сохранение связи не запускает рутину. Для учебного дня сегодня
или завтра нажмите **Проверить и начать подготовку**, проверьте ребёнка, местную
дату, версии расписания и рутины. На одну пару «расписание — дата» разрешён один
запуск, даже если он уже завершён. Чужой активный запуск не подхватывается молча.
Шаги выполняются в отдельной карточке распорядков; запись о запуске ещё не означает,
что рюкзак собран. После изменения шаблона, снятия прав или
отключения модуля ссылка перестаёт считаться доступной; её нужно проверить заново.
В редакторе старая версия явно помечается недоступной. Выберите вариант без рутины
или актуальную замену: простое переименование не удаляет связь молча.

Включите **Задачи**, чтобы добавлять домашнее задание прямо в «Школе». Родитель
выбирает ребёнка; ребёнок создаёт задание только себе. Перед подтверждением видны
название, необязательные срок, шаги и урок, время напоминания и отсрочка. Создаётся
одна обычная личная задача без штрафа. Начало, выполнение шагов, текстовый отчёт
и родительская проверка доступны в «Задачах». Название, срок и правила напоминаний
родитель меняет в «Школе»; переназначение другому ребёнку запрещено. Обычная правка
сохраняет прогресс. Перепривязка после изменения профиля ребёнка сбрасывает прогресс,
выдаёт новое личное уведомление о назначении и не раскрывает новому профилю старые
отчёт и проверку. Они остаются в родительской истории — это не удаление данных. Созданная работа остаётся
в «Задачах» даже после архивации расписания или отключения «Школы».

Работают существующие личные уведомления задач и распорядков. Расписание и содержимое
домашней работы не публикуются в семейную группу и не отправляются автоматически
в ИИ или поиск. Автосоздание домашней работы, публикация календаря HA и
проверяемый импорт фото/календаря ещё предстоят.
Этот модуль не управляет устройствами.

Для напоминаний о сборах владелец включает общий переключатель в **Настройках**
интеграции и задаёт время `ЧЧ:ММ` в часовом поясе семьи: в учебный день (0) или
накануне (1). По умолчанию выключено, накануне, `20:00`. Затем каждый родитель или
ребёнок сам нажимает **Включить для меня** в «Школе», проверяет указанного ребёнка
и личного получателя и сохраняет выбор. Родитель подписывает только себя, ребёнок
— только себя на своё расписание. Личный Telegram-чат должен быть связан с
участником семьи. Сохранённый выбор не включает общий переключатель или «Рутины».

Запись для отправки создаётся в пятиминутное окно и только для настоящего учебного
дня с актуальными расписанием и рутиной рюкзака. Пропущенные окна не догоняются.
Тихие часы и повтор доставки могут отложить сообщение, но после начала первого
урока оно уже не отправляется. При переводе часов несуществующее время пропускается,
повторяющееся используется один раз, в первое вхождение. Изменение источника,
профиля, подписки или правил отменяет актуальность старого сообщения; начатая
подготовка подавляет напоминание. Не более одной записи на получателя/расписание/день,
в том числе после правок и повторного включения. Напоминание само не запускает
рутины, не создаёт задания и не меняет баллы.

## Українська

Увімкніть **Шкільний розклад** і додайте картку **Школа**. Батьки або власник
створюють один активний розклад на дитину: назву, період, дати без уроків і
щотижневі уроки. Для уроку задайте початок, кінець, предмет, за потреби кабінет
і матеріали. Час — місцевий у часовому поясі сім'ї. Перетини заборонені,
сусідні інтервали дозволені. Виняток прибирає всі уроки зазначеної місцевої дати.

Перед збереженням перевірте дитину, дати й усі уроки. Редагування замінює розклад
цілком. Перепризначити його іншій дитині не можна: архівуйте з причиною та створіть
окремий запис. Архів зберігає батьківську історію, але прихований від дитини.
Другий активний розклад тієї самої дитини відхиляється навіть для іншого періоду.

Дитина читає лише власний чинний розклад і матеріали на найближчі 14 днів.
Розклади інших дітей та батьківська історія приховані; ролі «дорослий» і «гість»
шкільних даних не отримують. Будь-яка зміна картки дитини скасовує прив'язку
попередньої версії: батьки мають перевірити й зберегти розклад знову. Застаріла
форма не перезапише нові дані. Після втрати відповіді кнопка повторення надсилає
ту саму перевірену операцію без створення дубліката.

Необов'язкова **Рутина складання рюкзака** посилається на поточний увімкнений
шаблон, призначений дитині. Збереження зв'язку не запускає рутину. Для навчального
дня сьогодні або завтра натисніть **Перевірити й почати підготовку** та перевірте
дитину, місцеву дату, версії розкладу й рутини. Для пари «розклад — дата» можливий
лише один запуск, навіть після завершення. Інший активний запуск не підхоплюється
мовчки. Кроки виконуються в картці розпорядків; запис про запуск ще не означає,
що рюкзак зібрано. Зміна шаблону, відкликання прав або вимкнення модуля
прибирає доступне посилання. Батьки мають перевірити його заміну.
Редактор явно позначає стару версію недоступною. Оберіть варіант без рутини або
чинну заміну: просте перейменування не видаляє зв'язок непомітно.

Увімкніть **Завдання**, щоб додавати домашню роботу в «Школі». Батьки вибирають
дитину; дитина може створювати завдання лише собі. Перевірте назву, необов'язкові
термін, кроки й урок, час нагадування та відстрочку. Створюється одне звичайне
приватне завдання без штрафу. Початок, виконання кроків, текстовий звіт і батьківська
перевірка доступні в «Завданнях». Назву, термін і правила нагадувань батьки змінюють
у «Школі»; перепризначення іншій дитині заборонено. Звичайна зміна зберігає прогрес.
Повторна прив'язка після зміни профілю дитини скидає прогрес, надсилає нове приватне
сповіщення про призначення й не показує новому профілю попередній звіт та перевірку.
Вони залишаються в батьківській історії — це не видалення даних. Створена робота залишається в «Завданнях»
навіть після архівації розкладу чи вимкнення «Школи».

Діють наявні приватні сповіщення завдань і розпорядків. Розклад і вміст домашньої
роботи не публікуються в сімейну групу та не передаються автоматично до ШІ чи пошуку.
Автостворення домашньої роботи, календар HA та
підтверджуваний імпорт фото/календаря залишаються наступними етапами.
Модуль не керує пристроями.

Для нагадувань власник вмикає загальний перемикач у **Налаштуваннях** інтеграції,
обирає навчальний день (0) або напередодні (1) та час `ГГ:ХХ` у часовому поясі
сім'ї. Типово вимкнено, напередодні, `20:00`. Кожен одержувач сам натискає
**Увімкнути для мене** в «Школі», перевіряє дитину й особистого одержувача та
зберігає вибір. Батьки підписують лише себе; дитина — лише себе на власний розклад.
Особистий Telegram-чат має бути пов'язаний з учасником. Збереження вибору не вмикає
загальне правило чи модуль «Рутини».

Запис для надсилання створюється лише в п'ятихвилинне вікно для фактичного
навчального дня з чинним розкладом і рутиною рюкзака. Пропущені вікна не надолужуються.
Тихі години й повтор доставки можуть відкласти повідомлення, але воно прострочується
на початку першого уроку. Неіснуючий час переходу на літній час пропускається,
повторений час використовується лише вперше. Зміна джерела, профілю, підписки або
правил скасовує актуальність старого повідомлення; почата підготовка пригнічує
нагадування. Не більш ніж один запис на одержувача/розклад/день навіть після змін
і повторного ввімкнення. Жодні рутини, завдання, пристрої чи бали не змінюються.

## API and privacy contract

- `school.timetable_save`: `member`, `member_revision`, `title`, `valid_from`,
  `valid_until` (date or null), `lessons`, `backpack_routine` (pinned `{id,revision}`
  or null), `exceptions` (omission means empty, also on replacement). New records
  omit both `id` and `revision`; replacement requires both current values.
- `school.timetable_archive`: `id`, `revision`, nonempty `reason` up to 500 chars.
- `school.homework_create`: `member`, `member_revision`, `title`, `due_at`
  (ISO timestamp or null), `checklist` (up to 50 strings). Optional
  `reminder_minutes` (0–10080, default 60), `grace_minutes` (0–1440, default 30),
  `lesson` (null or exact `{timetable_id,timetable_revision,date,lesson_index}`).
- `school.homework_revise` (parent): exact `id`, `revision`, `member_revision`,
  `title`, `due_at`, `reminder_minutes`, `grace_minutes`. Assignee/lesson/checklist
  text remain bound; identity refresh resets the current lifecycle.
- `school.backpack_start`: exact `timetable_id`, `timetable_revision`, `member`,
  `member_revision`, local `date`, `routine_id`, `routine_revision`. Requires
  School and Routines, an actual lesson today/tomorrow, current source/participant
  authority and no already-started preparation for that timetable/date.
  Returns only `{id,revision,status,run_id}`, never step confirmation nonces.
- `school.preparation_reminder_access_set`: exact `member`, `member_revision`,
  `recipient_revision`, `subscription_revision` (null only for a first opt-in),
  `enabled` (strict bool). The authenticated actor is the recipient. Returns
  only `{member,enabled,revision}`. The view exposes only this actor's
  `preparation_reminders.policy` and `self_targets`; subscriptions for other
  recipients are never projected.
- Owner settings: `school_preparation_reminders` (bool),
  `school_preparation_days_before` (strict integer 0 or 1),
  `school_preparation_time` (zero-padded `HH:MM`). Omitted values preserve current
  preferences; old Stores default to off without rewriting user data.
- Timetable/homework receipts contain only `{id,revision,status}`; backpack
  receipts additionally contain `run_id`. Timetables stay under `school.timetables`,
  start markers under `school.preparations`, homework under `tasks`, and routine
  execution under `routine_runs` in the household Store, separate from HACS code.
  No media bytes or external IDs.

Revisions are strict JSON-safe integers `1..2^53-1`, not booleans/strings/floats.
Titles/subjects: 120 characters; rooms: 80. Lessons: 1–70 with exact fields
`weekday` (0–6, Monday first), `start`, `end` (`HH:MM`), `subject`, `room`,
`materials` (up to 12 nonempty labels, 120 chars each; 200 labels total).
Case-folded material duplicates are rejected per lesson. Up to 366 unique ISO
exception dates must fall within the validity interval. There is no implicit
lesson truncation or overnight time conversion.

The pure projection returns `timetables` and `upcoming`, covering local today
through today+13. No date is guessed if `now` is absent. Occurrences have stable
IDs and sort by date/time/member; date limits fail safely. Parent views include
history and the stored routine pair plus `backpack_routine_current`; child views
omit history/creator and expose only a currently usable routine reference.

The authenticated household view also adds `homework` (authorized private Task
projections when Tasks is enabled) and `preparations` (opaque starts plus derived
run status). Homework lives in the existing `tasks` store; preparation records
only link to an ordinary routine run. Private content/source metadata is excluded
from model/search, group Telegram, diagnostics, entity attributes and audit receipts.
Outbox records use existing private task/routine IDs and identity checks, not a
school broadcast. Ordinary HA
administrators and backups may access the underlying local storage: these are
application permissions, not encryption from the administrator. Archive is not
deletion and does not erase backups.

Preparation subscriptions and dedup markers use separate subkeys in `school`.
Their outbox intent contains only IDs, versions, date, policy fingerprint and
expiry. Current authorized names and at most 20 unique material labels are
resolved only for private delivery; overflow is stated, link previews disabled.
Current authority is checked both before claiming and again before transport.
An already in-flight network request cannot be recalled. Lifetime marker capacity
is bounded at 10,000; safe retention and a capacity health signal remain required
before the public release. The cap prevents unbounded growth, not a substitute
for that remaining retention work.
