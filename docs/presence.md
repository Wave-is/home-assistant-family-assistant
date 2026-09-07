# Reported presence / Сообщённое присутствие / Повідомлена присутність

## English

This guide covers the first, display-only Presence slice. It reports limited
evidence from one configured Home Assistant source. It is not precise location,
continuous tracking, confirmed occupancy, or a safety signal.

The household owner opens **Presence sources** under **Settings → Devices &
services → Family Assistant → Configure** and selects one registered `person` or
`device_tracker` entity for a current non-guest family member. This preparation
is allowed while the Presence module is off. Configuring a source does not grant
consent and does not make it readable. Only the current household owner can add,
replace, or remove a source. Before personal consent or any observation read,
the owner must enable **Presence** under **Household preferences**.

The named family member must then open their own Presence card through their
linked Home Assistant account, review their name and current source/member
versions, and choose **Enable sharing**. Owners and parents cannot enable another
person's sharing. A child without a linked Home Assistant account cannot consent
in this slice; guardian-managed consent is not implemented. Add the card manually:

```yaml
type: custom:family-presence-card
entry_id: YOUR_FAMILY_ASSISTANT_ENTRY_ID
```

After consent, the person sees their own normalized status. Current owners and
parents may also see that person's `reported home`, `reported away`, or `unknown`
status and observation time. Adults and children do not see other people's rows.
Home Assistant permissions remain an independent gate: the requesting HA user
must have read permission for each source. Consent or a Family Assistant parent
role never grants HA entity access. Without that permission the source is not
read and the card reports unknown/unavailable.

Evidence older than the configured freshness limit, unavailable or missing
entities, malformed timestamps, and future-dated reports become **unknown**.
Named zones are reduced to `reported away`; their names are not shown. Unknown is
never interpreted as home or away, and a prior good value is not reused. The
owner can set the freshness limit from 30 to 3600 seconds; the default is 300.

Disabling sharing stops subsequent reads and removes the row from parent views.
Removing or replacing the source, changing the member record, unlinking the HA
account, changing role, deactivating the member, or disabling the module also
invalidates the old access. A newly current source requires a fresh self-consent.
The source entity ID is retained in private integration Options and may exist in
HA backups, but observed states, times, coordinates, zone names, attributes, and
location history are not stored by this feature.

Presence is not sent to Telegram, language models, search providers, diagnostics,
or Home Assistant entity attributes. It does not start routines, alter tasks or
points, send or delay notifications, operate devices, or make automation and
safety decisions. Those broader vision items are outside this slice, and real
household source acceptance remains a separate deployment check.

## Русский

Это руководство описывает первый, только информационный раздел присутствия. Он
показывает ограниченные данные из одного выбранного источника Home Assistant. Это
не точное местоположение, не непрерывное отслеживание, не подтверждение, что кто-то
дома, и не сигнал безопасности.

Владелец семьи открывает **Источники присутствия**: **Настройки → Устройства и
службы → Family Assistant → Настроить** — и выбирает одну зарегистрированную
сущность `person` или `device_tracker` для текущего участника семьи без роли гостя.
Источник можно подготовить, пока модуль «Присутствие» выключен. Выбор источника не
означает согласие и сам по себе не разрешает чтение. Добавлять, заменять и удалять
источники может только текущий владелец семьи. До личного согласия или любого
чтения наблюдений владелец должен включить **Присутствие** в **Настройках семьи**.

После этого указанный участник входит через собственную связанную учётную запись
Home Assistant, открывает свою карточку, проверяет имя и текущие версии участника и
источника и нажимает **Включить передачу**. Владелец или родитель не может дать
согласие за другого человека. Ребёнок без связанной учётной записи Home Assistant
пока не может дать такое согласие; управление согласием опекуном не реализовано.
Карточка добавляется вручную:

```yaml
type: custom:family-presence-card
entry_id: ID_ЗАПИСИ_FAMILY_ASSISTANT
```

После согласия участник видит свой нормализованный статус. Текущие владельцы и
родители также могут видеть его статус «по данным источника — дома», «не дома» или
«неизвестно» и время наблюдения. Взрослые и дети не видят строки других людей.
Права Home Assistant проверяются отдельно: у запрашивающего пользователя HA должно
быть право чтения каждого источника. Согласие и роль родителя в Family Assistant
не дают доступ к сущности HA. Без такого права источник не читается, а карточка
показывает «неизвестно/недоступно».

Просроченные данные, недоступная или отсутствующая сущность, неправильное время и
сообщения из будущего дают статус **неизвестно**. Название зоны отбрасывается и
преобразуется только в «не дома». Неизвестный статус не считается ни присутствием,
ни отсутствием, а прежнее успешное значение не используется. Владелец задаёт срок
актуальности от 30 до 3600 секунд; стандартное значение — 300 секунд.

Отключение передачи прекращает последующие чтения и убирает строку из представления
родителей. Удаление или замена источника, изменение карточки участника, отвязка
учётной записи HA, смена роли, деактивация или выключение модуля также отменяют
старый доступ. Для нового актуального источника требуется новое личное согласие.
Идентификатор сущности хранится в закрытых параметрах интеграции и может попасть в
резервные копии HA, но наблюдаемые статусы, время, координаты, названия зон,
атрибуты и история местоположения этой функцией не сохраняются.

Присутствие не передаётся в Telegram, языковые модели, поиск, диагностику или
атрибуты сущностей Home Assistant. Оно не запускает рутины, не меняет задачи или
баллы, не отправляет и не задерживает уведомления, не управляет устройствами и не
принимает решений для автоматизаций или безопасности. Эти части общего замысла не
входят в данный раздел; проверка реальных домашних источников остаётся отдельным
этапом развёртывания.

## Українська

Цей посібник описує перший, лише інформаційний розділ присутності. Він показує
обмежені дані з одного вибраного джерела Home Assistant. Це не точне
місцезнаходження, не безперервне відстеження, не підтвердження перебування вдома й
не сигнал безпеки.

Власник родини відкриває **Джерела присутності**: **Налаштування → Пристрої та
служби → Family Assistant → Налаштувати** — і вибирає одну зареєстровану сутність
`person` або `device_tracker` для поточного члена родини без ролі гостя. Джерело
можна підготувати, поки модуль «Присутність» вимкнений. Вибір джерела не є згодою й
сам собою не дозволяє читання. Додавати, замінювати та видаляти джерела може лише
поточний власник родини. До особистої згоди чи будь-якого читання спостережень
власник має ввімкнути **Присутність** у **Налаштуваннях родини**.

Після цього вказаний учасник входить через власний пов'язаний обліковий запис Home
Assistant, відкриває свою картку, перевіряє ім'я та поточні версії учасника й
джерела та натискає **Увімкнути поширення**. Власник або батьки не можуть надати
згоду за іншу людину. Дитина без пов'язаного облікового запису Home Assistant поки
не може надати таку згоду; керування згодою опікуном не реалізоване. Картка
додається вручну:

```yaml
type: custom:family-presence-card
entry_id: ID_ЗАПИСУ_FAMILY_ASSISTANT
```

Після згоди учасник бачить власний нормалізований статус. Поточні власники й батьки
також можуть бачити статус цієї людини «за даними джерела — удома», «не вдома» або
«невідомо» та час спостереження. Дорослі й діти не бачать рядків інших людей.
Права Home Assistant перевіряються окремо: користувач HA, який робить запит, повинен
мати право читання кожного джерела. Згода чи роль батьків у Family Assistant не
надає доступу до сутності HA. Без такого права джерело не читається, а картка
показує «невідомо/недоступно».

Застарілі дані, недоступна або відсутня сутність, неправильний час і повідомлення з
майбутнього дають статус **невідомо**. Назва зони відкидається й перетворюється лише
на «не вдома». Невідомий статус не вважається ні присутністю, ні відсутністю, а
попереднє успішне значення не використовується. Власник задає строк актуальності
від 30 до 3600 секунд; стандартне значення — 300 секунд.

Вимкнення поширення припиняє наступні читання й прибирає рядок із подання батьків.
Видалення чи заміна джерела, зміна картки учасника, відв'язування облікового запису
HA, зміна ролі, деактивація або вимкнення модуля також скасовують старий доступ.
Для нового актуального джерела потрібна нова особиста згода. Ідентифікатор сутності
зберігається в закритих параметрах інтеграції й може потрапити до резервних копій
HA, але спостережувані статуси, час, координати, назви зон, атрибути та історія
місцезнаходження цією функцією не зберігаються.

Присутність не передається до Telegram, мовних моделей, пошуку, діагностики чи
атрибутів сутностей Home Assistant. Вона не запускає рутини, не змінює завдання або
бали, не надсилає й не затримує сповіщення, не керує пристроями та не ухвалює рішень
для автоматизацій чи безпеки. Ці частини загального задуму не входять до цього
розділу; перевірка реальних домашніх джерел залишається окремим етапом розгортання.
