# Family polls / Семейные голосования / Родинні голосування

## English

Enable **Family polls** in Home Assistant under **Settings → Devices & services →
Family Assistant → Configure → Household preferences**. Only the household owner
can change integration options. Then add the dedicated card manually:

```yaml
type: custom:family-polls-card
entry_id: YOUR_FAMILY_ASSISTANT_ENTRY_ID
```

A parent or owner creates a poll with one question, 2–10 unique choices, a closing
time, and an explicit list of 1–50 current non-guest family members. Review the
whole poll and the privacy warning before confirming. Each eligible member sees
only polls addressed to their current profile and casts or changes only their own
vote until the poll closes. A parent who was not selected as a voter cannot vote.

Choice totals appear only after the recorded deadline or an early close by a
parent. The family view never shows who selected which choice. A parent can archive
a closed poll: this freezes the totals and deletes the individual ballot mapping.
Only parents see the archive. Purge is a separate, explicit, irreversible owner
action; it requires reviewing the archived revision and confirming deletion.
Archive and purge do not erase copies already retained in Home Assistant backups.

“Private ballot” is not the same as an anonymous survey. Home Assistant
administrators, the local integration Store, and people able to read backups may
access the underlying data. Results from a one-person electorate, or a count that
leaves only one possible voter, can also reveal that person's choice by inference.
Use polls for bounded family decisions, not sensitive surveys.

With a linked Telegram bot, send `/polls` in a **private chat**. Choose a numbered
option, review it, then press **Confirm**; the same flow is used to change a vote or
for parent close/archive actions. Reviews expire after about five minutes. If a
review is stale, reopen `/polls` and start again. If the confirmation succeeded but
its response was lost, pressing the same confirmation again retries the exact
frozen operation rather than creating another vote. In a family group, `/polls`
returns only a constant instruction to use private chat—never a question, choice,
or result. Reopen `/polls` when Telegram says more polls were omitted.

Poll text is not automatically copied from a bot reply into the optional language
model fallback. Text that a user deliberately pastes or types is still ordinary
untrusted user input and may be processed by that enabled conversation provider.
This slice sends no reminders and never changes devices, tasks, points, alarms,
routines, shopping, or other external systems.

## Русский

Включите **Семейные голосования** в Home Assistant: **Настройки → Устройства и
службы → Family Assistant → Настроить → Настройки семьи**. Параметры интеграции
меняет только владелец семьи. Затем вручную добавьте отдельную карточку:

```yaml
type: custom:family-polls-card
entry_id: ID_ЗАПИСИ_FAMILY_ASSISTANT
```

Родитель или владелец задаёт вопрос, 2–10 уникальных вариантов, время закрытия и
явный список из 1–50 текущих участников семьи без роли гостя. Перед подтверждением
проверьте всё голосование и предупреждение о приватности. Каждый включённый в
список участник видит голосования только для своей текущей учётной записи и до
закрытия выбирает или меняет только свой голос. Родитель, которого не добавили в
список участников, голосовать не может.

Итоги показываются только после срока или досрочного закрытия родителем. Семейное
представление никогда не показывает связь «участник — вариант». Архивация
фиксирует счётчики и удаляет индивидуальные бюллетени; архив видят только родители.
Полное удаление — отдельное необратимое действие владельца с проверкой текущей
версии архива и явным подтверждением. Архивация и удаление не стирают уже созданные
резервные копии Home Assistant.

«Приватный бюллетень» не означает анонимный опрос. Администраторы Home Assistant,
локальное хранилище интеграции и пользователи с доступом к резервным копиям могут
увидеть исходные данные. При единственном участнике или однозначном раскладе выбор
можно определить по итогам. Не используйте семейные голосования для чувствительных
анонимных исследований.

В личном чате со связанным Telegram-ботом отправьте `/polls`, выберите пронумерованный
вариант, проверьте его и нажмите **Подтвердить**. Так же меняется голос и
подтверждаются закрытие или архивация родителем. Проверка действует около пяти
минут; если она устарела, снова откройте `/polls`. Если действие выполнилось, но
ответ потерялся, повтор той же кнопки подтверждения повторно использует точно ту же
зафиксированную операцию и не создаёт новый голос. В семейной группе `/polls`
показывает только постоянную просьбу перейти в личный чат — без вопроса, вариантов
и итогов. Если список сокращён, снова откройте `/polls`.

Текст голосования из ответа бота не переносится автоматически в необязательную
языковую модель. Текст, который пользователь сам вставил или набрал, остаётся
обычным недоверенным вводом и может обрабатываться включённым провайдером диалога.
Напоминаний и автоматических действий с устройствами, задачами, баллами, тревогами,
рутинами, покупками или внешними системами здесь нет.

## Українська

Увімкніть **Родинні голосування** в Home Assistant: **Налаштування → Пристрої та
служби → Family Assistant → Налаштувати → Налаштування родини**. Параметри
інтеграції змінює лише власник родини. Потім вручну додайте окрему картку:

```yaml
type: custom:family-polls-card
entry_id: ID_ЗАПИСУ_FAMILY_ASSISTANT
```

Батько, мати або власник задає запитання, 2–10 унікальних варіантів, час закриття
та явний список із 1–50 поточних учасників родини без ролі гостя. Перед
підтвердженням перевірте все голосування й попередження про приватність. Кожен
включений учасник бачить лише голосування для свого поточного профілю та до
закриття подає або змінює тільки власний голос. Батьки, яких не включили до списку,
голосувати не можуть.

Підсумки з'являються лише після строку або дострокового закриття батьками. Родинне
подання ніколи не показує зв'язок «учасник — варіант». Архівація фіксує лічильники
та видаляє індивідуальні бюлетені; архів бачать лише батьки. Повне видалення —
окрема незворотна дія власника з перевіркою поточної версії архіву та явним
підтвердженням. Архівація й видалення не стирають уже створені резервні копії
Home Assistant.

«Приватний бюлетень» не означає анонімне опитування. Адміністратори Home Assistant,
локальне сховище інтеграції та люди з доступом до резервних копій можуть прочитати
початкові дані. За одного учасника або однозначного розподілу вибір також можна
визначити з підсумків. Не використовуйте родинні голосування для чутливих анонімних
досліджень.

У приватному чаті з під'єднаним Telegram-ботом надішліть `/polls`, виберіть
пронумерований варіант, перевірте його й натисніть **Підтвердити**. Так само
змінюється голос і підтверджується закриття чи архівація батьками. Перевірка діє
близько п'яти хвилин; якщо вона застаріла, знову відкрийте `/polls`. Якщо дія
виконалася, але відповідь загубилася, повтор тієї самої кнопки використовує точно
ту саму зафіксовану операцію та не створює нового голосу. У родинній групі `/polls`
повертає лише сталу пораду перейти до приватного чату — без запитання, варіантів чи
підсумків. Якщо список скорочено, знову відкрийте `/polls`.

Текст голосування з відповіді бота не переноситься автоматично до необов'язкової
мовної моделі. Текст, який користувач сам вставив або набрав, залишається звичайним
недовіреним введенням і може оброблятися ввімкненим провайдером діалогу. Нагадувань
і автоматичних дій із пристроями, завданнями, балами, тривогами, рутинами,
покупками чи зовнішніми системами в цьому зрізі немає.
