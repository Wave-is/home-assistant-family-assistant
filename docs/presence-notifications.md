# Reminders on return / Напоминания по возвращении / Нагадування після повернення

## English

Off by default. In the **Presence** card, below display-only sharing, open your
notification preference or (owner/parent only) a current child's preference.
Configure a presence source first using [Presence sources](presence.md). Review
the named person, set the maximum wait (15–1440 minutes, default 720), and give
**separate explicit consent**. Dashboard sharing neither enables nor disables
background notification observations. Adults consent only for themselves; a
parent may approve for a child without a linked HA account.

Only personal Telegram task assignment/due/reminder notices, subscribed family
digests, pantry expiry and school preparation reminders can wait. The source
must freshly report home under the approving HA account's current entity read
permission. Away, missing/stale/future evidence, an inactive HA account or denied
read permission means wait, never an assumption of home. Group messages, direct
replies, all wake-up stages and incident closures keep their existing rules.

Held messages survive an integration reload and are checked at most once a
minute per pending delivery. Upon return they drain at most one held message per
person per two minutes. The ordinary quiet-hour and recipient/source checks still
apply. Expired messages are cancelled (`presence_wait_expired`), not sent on a
later return. Shortening the wait can shorten existing holds; increasing it never
extends their original deadline. No generic summary replaces actionable messages.

Disabling this preference restores ordinary delivery of still-valid, unexpired
messages to the **same** pinned recipient. Changing that recipient's identity
invalidates held delivery. Source/member/approver family-record changes revoke
the old consent; ordinary delivery resumes until explicitly renewed. In contrast,
missing HA read permission or an inactive approving HA account does not invent
consent or home status: observation is denied and the existing hold expires.

No source state, coordinates, zone name or location history is stored or sent to
Telegram, models, search or diagnostics. Private HA configuration/backups contain
the chosen entity, consent metadata and outbox hold/deadline/delivery timestamps;
those timestamps may indirectly reveal reminder timing. This is not a presence,
wakefulness or safety guarantee and controls no locks, sirens or other devices.

## Русский

По умолчанию выключено. В карточке **Семья дома**, ниже настроек отображения
присутствия, выберите свою доставку уведомлений или доставку ребёнку (для родителей
и владельца). Сначала настройте [источник присутствия](presence.md). Проверьте имя,
задайте ожидание 15–1440 минут (по умолчанию 720) и дайте **отдельное согласие**.
Разрешение показывать статус на карточке не включает и не выключает эту проверку.
Взрослый настраивает только себя; за ребёнка может согласиться родитель с аккаунтом
HA, даже если у ребёнка такого аккаунта нет.

Ждут только личные Telegram-напоминания о назначении/сроках задач, подключённые
дайджесты, сроки продуктов и подготовка к школе. Отправка разрешена при свежем
показании «дома» и действующем праве чтения источника у давшего согласие аккаунта
HA. «Не дома», неизвестные, старые или будущие данные, нет прав или аккаунт HA
выключен — ожидание. Семейный чат, прямые ответы, все этапы будильника и закрытие
инцидентов эта настройка не задерживает; их обычные правила сохраняются.

Очередь сохраняется после перезагрузки. Проверка — не чаще раза в минуту на
ожидающее сообщение, выдача накопленного — не чаще одного сообщения человеку за
две минуты. После лимита сообщение отменяется, а не приходит при позднем
возвращении. Уменьшение лимита сокращает ожидание; увеличение не продлевает уже
заведённый срок. Тихие часы и проверка актуальности получателя/задачи сохраняются.

Выключение настройки возвращает обычную доставку ещё актуальных и не просроченных
сообщений тому же получателю. Замена его привязки не перенаправляет старую очередь.
Изменение семейной записи участника/родителя или источника отменяет старое согласие:
обычная доставка до нового явного выбора. Если же отозвано именно право чтения HA
или выключен аккаунт HA, показание неизвестно и очередь ждёт до лимита.

Состояние источника, координаты и зоны не записываются и не передаются боту/ИИ.
В закрытых настройках и резервной копии HA остаются источник, согласие и времена
ожидания/доставки; время сообщений может косвенно раскрывать время напоминаний.
Это не доказательство присутствия, безопасности или пробуждения и не управление
сиреной, замками либо другими устройствами.

## Українська

Типово вимкнено. У картці **Родина вдома**, нижче показу присутності, виберіть свою
доставку або доставку дитині (батьки/власник). Спочатку налаштуйте
[джерело присутності](presence.md). Перевірте ім'я, задайте очікування 15–1440 хвилин
(типово 720) і надайте **окрему явну згоду**. Згода на показ статусу на картці не
вмикає й не вимикає ці перевірки. Дорослі погоджуються лише за себе; батьки можуть
налаштувати дитину без її облікового запису HA.

Очікують лише особисті Telegram-нагадування про завдання, підключені дайджести,
терміни продуктів і підготовку до школи. Потрібне свіже показання «удома» та чинне
право читання джерела в HA у того, хто дав згоду. Невідомі/застарілі/майбутні дані,
«не вдома», відсутність прав або неактивний обліковий запис HA означають очікування.
Сімейний чат, прямі відповіді, усі етапи будильника й закриття інцидентів зберігають
свої звичайні правила й не затримуються цим налаштуванням.

Черга переживає перезавантаження. Перевірка — не частіше разу на хвилину на
повідомлення, надсилання накопиченого — одного повідомлення людині за дві хвилини.
Після ліміту нагадування скасовується. Зменшення ліміту скорочує очікування;
збільшення не продовжує початковий строк. Тихі години й перевірка актуальності
одержувача/джерела залишаються чинними.

Вимкнення відновлює звичайну доставку ще актуальних і непрострочених повідомлень
тому самому одержувачу. Зміна його прив'язки не перенаправляє стару чергу. Зміна
сімейного запису учасника/батьків чи джерела скасовує стару згоду: діє звичайна
доставка до нового вибору. Втрата права читання HA або вимкнений обліковий запис
HA означають невідомий статус та очікування до ліміту.

Стани, координати й назви зон не записуються та не надсилаються боту/моделям.
Закриті налаштування й резервна копія HA містять джерело, згоду та часові позначки
черги/доставки; вони можуть непрямо розкривати час нагадувань. Це не доказ
присутності, безпеки чи пробудження й не керування сиренами або замками.
