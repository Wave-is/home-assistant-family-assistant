# Family Today / Семья сегодня / Родина сьогодні

## English

`custom:family-assistant-card` is a compact, display-only overview. It uses the
same current, role-filtered `family_assistant/view` response as the dedicated
cards. Opening Today makes no command, provider, presence, or refresh request of
its own.

The overview can show:

- up to four overdue tasks and four tasks due in the next 48 hours;
- parent-only counts and up to four task reports waiting for review;
- up to eight calendar, school, and next enabled alarm items combined;
- approved and pending shopping counts, without duplicating the shopping list;
- up to four active routine or alarm runs;
- up to eight normalized presence rows already authorized by the presence
  projection;
- up to eight current member point balances from the visible active ledger,
  without ledger reasons;
- parent-only counts of non-healthy component signals and unresolved delivery issues.

The dedicated card named below each section remains the place for details and
actions. Today has no edit, approve, start, or retry controls.

Disabled modules are omitted even if an old browser object still contains a
bucket. A child or adult receives only rows already projected for that member.
A guest receives no family overview. Parent presence rows still require the
other member's current consent and the requesting HA account's entity-read
permission. `Reported home`, `Reported away`, and `Unknown` are normalized
observations, not precise location or proof of occupancy. Today never displays
raw presence entity IDs, coordinates, task reports, media, school materials,
alarm challenges, routine nonces, delivery recipients, or health codes.

## Русский

`custom:family-assistant-card` — компактный обзор только для чтения. Он использует
тот же актуальный ответ `family_assistant/view` с ролевой фильтрацией, что и
отдельные карточки. При открытии обзор не отправляет собственных команд и не
запрашивает провайдера, присутствие или дополнительное обновление.

Обзор может показать:

- до четырёх просроченных задач и четырёх задач со сроком в ближайшие 48 часов;
- только родителям: счётчики и до четырёх отчётов по задачам на проверке;
- суммарно до восьми ближайших событий календаря, уроков и включённых будильников;
- счётчики одобренных и ожидающих покупок без копии списка покупок;
- до четырёх активных запусков рутин или будильников;
- до восьми уже разрешённых строк нормализованного присутствия;
- до восьми текущих балансов участников из видимой активной истории без причин
  начислений;
- только родителям: количество сигналов о неполадках и нерешённых проблем доставки.

Под каждой секцией названа отдельная карточка, в которой доступны подробности и
действия. В обзоре нет кнопок изменения, одобрения, запуска или повтора.

Выключенные модули не показываются, даже если старый объект браузера ещё содержит
их данные. Ребёнок или взрослый получает только уже спроецированные для него
строки. Гость не получает семейный обзор. Строки присутствия других участников
для родителя всё равно требуют их актуального согласия и права чтения сущности у
запрашивающего аккаунта HA. Статусы «сообщено: дома», «сообщено: не дома» и
«неизвестно» — нормализованные наблюдения, а не точное местоположение или
доказательство присутствия. Обзор не показывает исходные ID сущностей
присутствия, координаты, отчёты и медиа задач, школьные материалы, задания
будильника, nonce рутин, получателей доставки или внутренние коды состояния.

## Українська

`custom:family-assistant-card` — компактний огляд лише для читання. Він
використовує ту саму актуальну відповідь `family_assistant/view` із рольовою
фільтрацією, що й окремі картки. Під час відкриття огляд не надсилає власних
команд і не запитує провайдера, присутність чи додаткове оновлення.

Огляд може показати:

- до чотирьох прострочених завдань і чотирьох завдань із терміном у найближчі
  48 годин;
- лише батькам: лічильники та до чотирьох звітів про завдання на перевірці;
- разом до восьми найближчих подій календаря, уроків і ввімкнених будильників;
- лічильники схвалених і очікуваних покупок без копії списку покупок;
- до чотирьох активних запусків рутин або будильників;
- до восьми вже дозволених рядків нормалізованої присутності;
- до восьми поточних балансів учасників із видимої активної історії без причин
  нарахувань;
- лише батькам: кількість сигналів про негаразди та невирішених проблем доставки.

Під кожною секцією названа окрема картка, де доступні подробиці та дії. В огляді
немає кнопок зміни, схвалення, запуску або повтору.

Вимкнені модулі не показуються, навіть якщо старий об'єкт браузера ще містить
їхні дані. Дитина або дорослий отримує лише вже спроєктовані для нього рядки.
Гість не отримує родинний огляд. Рядки присутності інших учасників для когось із
батьків усе одно потребують їхньої актуальної згоди та права читання сутності в
облікового запису HA, що робить запит. Статуси «повідомлено: вдома», «повідомлено:
не вдома» і «невідомо» — нормалізовані спостереження, а не точне
місцеперебування чи доказ присутності. Огляд не показує вихідні ID сутностей
присутності, координати, звіти й медіа завдань, шкільні матеріали, завдання
будильника, nonce рутин, одержувачів доставки чи внутрішні коди стану.
