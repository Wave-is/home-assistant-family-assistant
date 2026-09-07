# Private family digests / Личные семейные дайджесты / Особисті родинні дайджести

## English

Enable **Private family digests** in Home Assistant under **Settings → Devices &
services → Family Assistant → Configure → Household preferences**. Only the
household owner sets the global morning, evening and weekly schedule under
**Digest schedule**. All three kinds are off by default. Times use the household
time zone; the defaults are 07:00 morning, 19:00 evening, and Sunday (day 6) at
18:00 weekly.

Add the dedicated card manually:

```yaml
type: custom:family-digests-card
entry_id: YOUR_FAMILY_ASSISTANT_ENTRY_ID
```

Every current non-guest member uses their own Home Assistant account and this card
to review and save their own morning, evening and weekly choices. The owner cannot
subscribe another person. Global policy and personal consent are both required for
delivery. Connect the household's own Telegram bot and link that member's current
private chat in Family Assistant settings. A family group is not a digest target.

**Preview** is an explicit, current, private read: it is not sent, saved as digest
history, or refreshed automatically. It works before subscribing so a member can
review the scope. The preview can show bounded details for that member's tasks,
calendar, routine steps and, for a child, school lessons. Shopping, low-stock and
expiring pantry items, maintenance and polls are counts only. At most 10 detail
rows appear in a section. It excludes media, dietary and presence data, ballots,
task reports, identifiers, and raw Home Assistant attributes. It does not call an
LLM or internet search. Counts can still reveal personal information in a small
household; they are minimized, not anonymous.

The morning digest covers its scheduled local date, evening covers the next local
date, and weekly covers the next seven local dates. The scheduler creates an
intent only during the five minutes after the configured local time and does not
backfill a missed window. Quiet hours or a delivery retry may delay an already
created message. A morning message expires at the earlier of six hours after its
schedule or the next household-local midnight; an evening message expires after
six hours, even if that crosses midnight; a weekly message expires after 24 hours.
Content is rebuilt from current authorized data immediately before sending, so
the summary window remains tied to its scheduled digest even when delivery waits.

Sent, superseded and otherwise resolved daily records are retained for 35 days,
weekly records for 16 weeks, and failed records for 90 days. Pending, sending and
uncertain records are not automatically pruned. Digest markers and retained
events are capped at 10,000 each. At a cap, new digests pause and Home Assistant
Repairs shows **Digest retention needs review** with counts only. Review delivery
health and resolve outstanding notifications manually; the Repair does not name
recipients or include message text.

Three monotonic retired-through dates survive cleanup and reload. Changing the
clock, schedule or time zone cannot recreate an already retired old period.
Outstanding unresolved deliveries are not erased by this boundary. The card drops
a displayed or in-flight preview after an observed state or module change; a new
preview requires another explicit click.

Digests never start routines, complete tasks, place orders, change devices, award
points or apply penalties. This page describes the bounded integration slice and
its tested contract; it is not a claim that a particular household or production
bot has been configured or accepted.

## Русский

Включите **Личные семейные дайджесты** в Home Assistant: **Настройки → Устройства
и службы → Family Assistant → Настроить → Параметры семьи**. Только владелец
задаёт общее утреннее, вечернее и еженедельное расписание в разделе
**Расписание дайджестов**. По умолчанию все три вида выключены. Используется
часовой пояс семьи; исходные значения — 07:00 для утреннего, 19:00 для вечернего
и воскресенье (день 6) в 18:00 для еженедельного дайджеста.

Добавьте отдельную карточку вручную:

```yaml
type: custom:family-digests-card
entry_id: ID_ЗАПИСИ_FAMILY_ASSISTANT
```

Каждый текущий участник без роли гостя входит под своей учётной записью Home
Assistant и в этой карточке проверяет и сохраняет только собственный выбор.
Владелец не может подписать другого участника. Для отправки нужны и общая
политика, и личное согласие. Подключите собственного Telegram-бота семьи и
привяжите текущий личный чат участника в настройках Family Assistant. Семейная
группа не может быть получателем дайджеста.

Кнопка **Предпросмотр** выполняет явное текущее личное чтение: результат не
отправляется, не сохраняется как история дайджеста и не обновляется автоматически.
Предпросмотр доступен до подписки, чтобы участник мог оценить состав. Он показывает
ограниченные сведения о собственных задачах, календаре и шагах распорядков, а для
ребёнка — об уроках. Покупки, малые и истекающие запасы, обслуживание и
голосования представлены только счётчиками. В разделе не более 10 подробных строк.
Медиа, пищевые и данные присутствия, бюллетени, отчёты задач, идентификаторы и
необработанные атрибуты Home Assistant исключены. LLM и интернет-поиск не
вызываются. В небольшой семье даже счётчики могут раскрывать личные сведения: это
минимизация данных, а не анонимность.

Утренний дайджест охватывает назначенную местную дату, вечерний — следующую дату,
еженедельный — следующие семь местных дат. Намерение создаётся только в течение
пяти минут после заданного местного времени; пропущенное окно не догоняется.
Тихие часы или повтор доставки могут задержать уже созданное сообщение. Утреннее
сообщение истекает через шесть часов либо в следующую местную полночь — что раньше;
вечернее — через шесть часов, даже если срок переходит через полночь; еженедельное
— через 24 часа. Непосредственно перед отправкой содержимое заново собирается из
текущих разрешённых данных, а период сводки остаётся привязан к расписанию.

Отправленные, заменённые и другие завершённые дневные записи хранятся 35 дней,
еженедельные — 16 недель, неудачные — 90 дней. Ожидающие, отправляемые и записи с
неопределённым результатом автоматически не удаляются. Для маркеров и сохранённых
событий установлен отдельный предел 10 000. При достижении предела новые дайджесты
приостанавливаются, а Home Assistant Repairs показывает **Нужно проверить хранение
дайджестов** только со счётчиками. Проверьте доставку и вручную разберите
незавершённые уведомления; получателей и текста сообщений в предупреждении нет.

Три постоянно сохраняемые границы обработанных дат переживают очистку и
перезапуск. Откат часов, расписания или часового пояса не создаёт уже удалённый
старый период заново. Нерешённые доставки эта граница не удаляет. После получения
изменённой ревизии состояния или списка модулей карточка скрывает старый и
ожидающий предпросмотр; для нового нужно снова нажать кнопку.

Дайджесты не запускают распорядки, не завершают задачи, не оформляют заказы, не
управляют устройствами, не начисляют баллы и не назначают штрафы. Здесь описан
ограниченный реализованный контракт, а не факт настройки или приёмки в конкретной
семье либо рабочем Telegram-боте.

## Українська

Увімкніть **Особисті родинні дайджести** в Home Assistant: **Налаштування →
Пристрої та служби → Family Assistant → Налаштувати → Параметри родини**. Лише
власник задає спільний ранковий, вечірній і щотижневий розклад у розділі
**Розклад дайджестів**. Типово всі три види вимкнено. Використовується часовий пояс
родини; початкові значення — 07:00 для ранкового, 19:00 для вечірнього та неділя
(день 6) о 18:00 для щотижневого дайджесту.

Додайте окрему картку вручну:

```yaml
type: custom:family-digests-card
entry_id: ID_ЗАПИСУ_FAMILY_ASSISTANT
```

Кожен поточний учасник без ролі гостя входить під власним обліковим записом Home
Assistant і в цій картці перевіряє та зберігає лише власний вибір. Власник не може
підписати когось іншого. Для надсилання потрібні і спільна політика, і особиста
згода. Під'єднайте власного Telegram-бота родини та прив'яжіть поточний особистий
чат учасника в налаштуваннях Family Assistant. Родинна група не може бути
одержувачем дайджесту.

Кнопка **Попередній перегляд** виконує явне поточне особисте читання: результат не
надсилається, не зберігається як історія дайджесту й не оновлюється автоматично.
Перегляд доступний до підписки, щоб учасник міг оцінити склад. Він показує
обмежені відомості про власні завдання, календар і кроки розпорядків, а для дитини
— про уроки. Покупки, малі та прострочувані запаси, обслуговування й голосування
подано лише лічильниками. У розділі не більше 10 докладних рядків. Медіа, харчові
дані й дані присутності, бюлетені, звіти завдань, ідентифікатори та необроблені
атрибути Home Assistant виключено. LLM та інтернет-пошук не викликаються. У малій
родині навіть лічильники можуть розкривати особисті відомості: це мінімізація
даних, а не анонімність.

Ранковий дайджест охоплює призначену місцеву дату, вечірній — наступну дату, а
щотижневий — наступні сім місцевих дат. Намір створюється лише протягом п'яти
хвилин після заданого місцевого часу; пропущене вікно не надолужується. Тихі
години або повтор доставки можуть затримати вже створене повідомлення. Ранкове
повідомлення спливає через шість годин або наступної місцевої опівночі — залежно
від того, що раніше; вечірнє — через шість годин, навіть якщо строк переходить
через опівніч; щотижневе — через 24 години. Безпосередньо перед надсиланням вміст
заново збирається з поточних дозволених даних, а період зведення лишається
прив'язаним до розкладу.

Надіслані, замінені та інші завершені денні записи зберігаються 35 днів,
щотижневі — 16 тижнів, невдалі — 90 днів. Очікувані, надіслані в цей момент і
записи з невизначеним результатом автоматично не видаляються. Для маркерів і
збережених подій діє окрема межа 10 000. Після досягнення межі нові дайджести
призупиняються, а Home Assistant Repairs показує **Потрібно перевірити зберігання
дайджестів** лише з лічильниками. Перевірте доставку та вручну опрацюйте
незавершені сповіщення; одержувачів і тексту повідомлень у попередженні немає.

Три збережені межі опрацьованих дат переживають очищення та перезапуск. Відкат
годинника, розкладу чи часового поясу не відтворює вже видалений старий період.
Невирішені доставки ця межа не видаляє. Після отримання нової ревізії стану чи
списку модулів картка приховує старий і ще очікуваний попередній перегляд;
новий перегляд потребує окремого натискання.

Дайджести не запускають розпорядки, не завершують завдання, не оформлюють
замовлення, не керують пристроями, не нараховують бали й не застосовують штрафи.
Тут описано обмежений реалізований контракт, а не факт налаштування чи приймання в
конкретній родині або робочому Telegram-боті.
