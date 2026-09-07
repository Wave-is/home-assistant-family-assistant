# School / Школа / Школа

Development feature: a private weekly timetable, lesson materials and a 14-day
agenda. Enable **School timetable** in Family Assistant options and add the
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
assigned to that child. It never starts or modifies a routine. Use the separate
Routines card for the manual checklist. A changed, disabled or unauthorized
template no longer appears as a usable link; a parent must review its replacement.
An unavailable stored version is shown explicitly in the editor. Choose no routine
or a current replacement before saving; renaming the timetable never silently
removes its stored link.

This stage does **not** send school reminders, create homework automatically,
award/deduct points, publish a HA calendar, import photographs/calendars or send
school records to Telegram/LLM/search. Use the existing Tasks card to assign
homework explicitly and its existing reminders/lifecycle. School-specific
homework handoff, preparation reminders and reviewed imports remain separate work.

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
назначенный ребёнку. Это не запуск и не изменение рутины. Сам чек-лист открывается
в отдельной карточке распорядков. После изменения шаблона, снятия прав или
отключения модуля ссылка перестаёт считаться доступной; её нужно проверить заново.
В редакторе старая версия явно помечается недоступной. Выберите вариант без рутины
или актуальную замену: простое переименование не удаляет связь молча.

На этом этапе нет школьных уведомлений, автоматического создания домашней работы,
штрафов, публикации календаря HA, импорта фото/календаря и отправки расписания в
Telegram, ИИ или поиск. Домашнюю работу можно явно назначать в карточке задач
с её существующими сроками и напоминаниями. Специальная передача домашней работы,
подготовительные напоминания и проверяемый импорт ещё предстоят.

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
шаблон, призначений дитині. Вона не запускає й не змінює рутину; чекліст доступний
в окремій картці розпорядків. Зміна шаблону, відкликання прав або вимкнення модуля
прибирає доступне посилання. Батьки мають перевірити його заміну.
Редактор явно позначає стару версію недоступною. Оберіть варіант без рутини або
чинну заміну: просте перейменування не видаляє зв'язок непомітно.

Поки немає шкільних сповіщень, автоматичного створення домашньої роботи, штрафів,
публікації календаря HA, імпорту фото/календаря чи передавання розкладу до Telegram,
ШІ або пошуку. Домашню роботу можна явно призначати в картці завдань з її строками
й нагадуваннями. Окрема передача домашньої роботи, підготовчі нагадування та
підтверджуваний імпорт залишаються наступними етапами.

## API and privacy contract

- `school.timetable_save`: `member`, `member_revision`, `title`, `valid_from`,
  `valid_until` (date or null), `lessons`, `backpack_routine` (pinned `{id,revision}`
  or null), `exceptions` (omission means empty, also on replacement). New records
  omit both `id` and `revision`; replacement requires both current values.
- `school.timetable_archive`: `id`, `revision`, nonempty `reason` up to 500 chars.
- Receipt: only `{id,revision,status}`. Data stays under `school.timetables` in
  the household Store, separate from HACS code. No media bytes or external IDs.

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

School data is excluded from current model/search and Telegram projections,
diagnostics, entity attributes, outbox and opaque audit receipts. Ordinary HA
administrators and backups may access the underlying local storage: these are
application permissions, not encryption from the administrator. Archive is not
deletion and does not erase backups.
