# Local device review / Проверка устройств / Перевірка пристроїв

## English

Enable MikroTik and configure its read-only connection in integration Options.
Open the Home network card and read the router again. The local review section
distinguishes protected, owner-approved and unreviewed devices. HA name matches,
DHCP reservations and router comments are identification evidence, not approval.
An inventory row does not prove a device is currently online or malicious.

The owner can preview approval, rename or removal for one observed device, then
review its exact before/after label and explicitly apply the saved plan. Parents
can read; other roles cannot read this section. Protected management MACs cannot
be approved/removed through these plans. Reading and approving records makes no
changes to DHCP, Wi-Fi, firewall or Kid Control. Approval is NOT authentication.

Plans expire after two minutes and pin the current actor revision, router source,
complete observation and policy revision. Changed data requires a new review.
An uncertain reply may be retried with the exact original operation identifier;
the card does not invent a new operation automatically. When changing router
source, explicit consent archives the old policy before creating a new one.
Old approvals are not automatically transferred to another router.

Parents can send `/unknown_devices` or `show unknown devices` privately to their
own configured bot. Group requests redirect to a private conversation without
MAC/IP details. Private replies show at most ten unreviewed observations; use the
card for the rest. Queued details are revoked after source, identity, policy,
module or freshness changes. No external LLM is needed for these exact commands.

Current mode is **audit only**. Optional self-only private
[discovery alerts](network-watch.md) are a separate, off-default subscription.
Quarantine and strict allowlist enforcement are not implemented. Enforcement requires
separate topology/IPv4/IPv6/FastTrack tests, protected infrastructure exclusions
and verified router-local recovery. Stored inactive approval rows remain in the
private ledger; the card currently displays observed rows only. Limits are
1,000 complete inventory rows, 1,000 approval records, 1,000 retained plans and
50 archived source policies; reaching capacity stops new changes instead of
silently deleting history. No auto-pruning is provided in this evaluation slice.

#### Strict mode preconditions

Before enabling any strict blocking mode in production, the integration requires
explicit evidence that:

- topology tests confirm no bypass path for protected traffic categories;
- IPv4 and IPv6 restriction probes were successful in representative tests;
- FastTrack and known offload bypass behavior is measured (counter/flag evidence);
- router/HA management hosts are explicitly excluded from blocks;
- local restart and exception recovery behavior is verified.

If any precondition is missing, strict/blocking controls remain disabled and the
card shows an actionable reason.

## Русский

Включите модуль MikroTik, настройте его подключение в параметрах интеграции и
нажмите «Прочитать роутер снова» в карточке домашней сети. Видны защищённые,
одобренные владельцем и непроверенные устройства. Название из HA, статическая
лиза и комментарий — подсказки для опознания, не автоматическое одобрение.
Наличие строки не доказывает, что устройство сейчас онлайн или опасно.

Владелец выбирает устройство, проверяет название/отзыв одобрения в предпросмотре
и отдельно подтверждает сохранённый план. Родителям доступен просмотр; детям,
гостям и другим взрослым этот раздел недоступен. Защищённые MAC исключены.
Изменяется только локальный журнал: DHCP, Wi-Fi, firewall и Kid Control остаются
без изменений. Одобрение не разрешает трафик и не является аутентификацией.

План действует две минуты и привязан к владельцу, источнику роутера, наблюдению
и версии журнала. При изменениях нужен новый просмотр. Потерянный ответ можно
повторить с исходным ID операции, без дубликата. Новый источник роутера требует
явного согласия: прежние одобрения архивируются, а не переносятся автоматически.

В личном чате своего бота родители могут написать `/неизвестные` или
`покажи неизвестные устройства`. В группе бот предложит перейти в личку без
раскрытия MAC/IP. Ответ содержит до десяти строк, полный наблюдаемый список —
в карточке. Перед отправкой перепроверяются права, источник и актуальность.

Сейчас это только учёт. [Личные оповещения о новых устройствах](network-watch.md)
включаются отдельно каждым родителем. Карантин и строгая блокировка ещё не
реализованы. Для них нужны отдельные проверки
топологии, IPv6/FastTrack и локального аварийного восстановления. Ненаблюдаемые
одобренные устройства сохраняются в журнале, но пока не выводятся карточкой.
Лимиты: 1000 строк инвентаря, 1000 одобрений, 1000 планов, 50 архивов источников.
При заполнении новые изменения останавливаются; история не удаляется скрыто.

#### Пререквизиты строгого режима

Карантин/строгая блокировка включаются только после подтверждения:

- отдельного прогона топологии без обходов защищённых потоков;
- подтверждённой работы IPv4 и IPv6 ограничений;
- проверки FastTrack и аппаратных ускорений с измеримым изменением флагов/счетчиков;
- явного исключения HA и управляемой инфраструктуры из блокировок;
- проверки локального восстановления после рестарта и завершения исключений.

Если хотя бы одно условие не выполнено, строгий режим остаётся недоступным, а
карточка показывает причину блокировки.

## Українська

Увімкніть MikroTik, налаштуйте підключення в параметрах інтеграції та повторно
прочитайте роутер у картці домашньої мережі. Розділ розрізняє захищені, схвалені
власником і неперевірені пристрої. Назва з HA, статична оренда й коментар є
підказками для впізнання, а не схваленням. Рядок інвентарю не доводить, що
пристрій зараз онлайн або небезпечний.

Власник переглядає зміну назви/схвалення чи його відкликання та окремо підтверджує
збережений план. Батьки можуть читати; інші ролі цього розділу не бачать.
Захищені MAC виключені. Змінюється лише локальний журнал, не DHCP, Wi-Fi,
firewall чи Kid Control. Схвалення не надає мережевого доступу.

План діє дві хвилини та прив'язаний до власника, джерела роутера, спостереження
і версії журналу. Після змін потрібен новий перегляд. Втрачений запит можна
повторити з тим самим ID без дубліката. Нове джерело потребує явної згоди:
попередні схвалення архівуються і не переносяться автоматично.

У приватному чаті власного бота батьки можуть написати `/невідомі` або
`покажи невідомі пристрої`. Груповий запит пропонує перейти в особистий чат,
не розкриваючи MAC/IP. До десяти рядків у відповіді, решта — у картці.
Перед надсиланням повторно перевіряються права, джерело та актуальність.

Зараз доступний лише облік. [Особисті сповіщення про нові пристрої](network-watch.md)
кожен з батьків вмикає окремо. Карантин і суворий список дозволених
пристроїв ще не реалізовані: потрібні перевірки топології,
IPv6/FastTrack та локального відновлення. Схвалені ненаблюдувані пристрої
залишаються в журналі, але поки не показуються карткою. Ліміти: 1000 рядків,
1000 схвалень, 1000 планів, 50 архівів джерел. Нові зміни зупиняються при
заповненні; історія не видаляється автоматично.

#### Попередні вимоги для строгого режиму

Карантин та суворий список дозволених пристроїв вмикаються лише після підтвердження:

- окремого прогона топології без обходів для захищених потоків;
- підтверджених IPv4/IPv6 обмежень на репрезентативних тестах;
- вимірювання FastTrack/апаратних прискорень (лічильники або прапорці);
- явного виключення HA, роутера керування та критичних сервісів;
- перевірки локального відновлення після рестарту і завершення дозволених винятків.

Якщо будь-яка умова не виконана, строгий режим лишається недоступним, а карточка
показує причину відмови.
