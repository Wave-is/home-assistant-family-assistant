# Isolated migration review / Проверка переноса / Перевірка перенесення

## English

This is an engineering-stage read-only copy, not an enabled migration wizard or
permission to replace an existing household. There is no public import/activation
endpoint yet. Do not edit `.storage`, replace a live Store, remove the isolation
marker or enable an older integration against a migration copy.

The pure `migration.shadow.build_shadow_candidate` constructor requires an exact
empty target with explicitly configured identities, a current whole conversion
review, complete source reviewer sets and an explicit preparation timestamp.
Any blocked record, changed parent authority or nonempty target rejects the whole
construction. It does not choose a partial set of successful modules.

Tasks and personal reminders retain their IDs; separate shopping, court and alarm
IDs have an exact private source-to-target map. Original source bytes, notes,
historical scores and transport receipts stay in the private archive, not active
message queues or model context. Current-week score totals are checked. New record
revision/construction timestamps are not invented historical user actions.

The persistent `legacy-shadow-v1` data schema cannot be loaded as an ordinary
writable household by earlier public releases. All modules remain off, schedules
disabled and automatic penalties off. Loaded shadows start no scheduler, Telegram,
LLM/search, recipe, presence, media-cleanup or network workers, even if Options
erroneously enable providers. No sensor/calendar/Assist entities are published,
so their state changes cannot trigger unrelated household automations.
Commands, internal clock writes and Options changes
are rejected. Backup release and entry reload do not unlock the copy.

Only a current owner can inspect the family projection. Cards show a localized
read-only notice, visible counts and up to 20 records per section with no mutation
controls. Source archives, identities and fingerprints never enter diagnostics.

This does **not** verify coherent real source capture, resolve old photo evidence,
authorize changed reviewer sets, transfer real bot ownership, or provide a cutover
and activation procedure. Those remain separate gates. Validation uses fictional
sources and isolated actual Home Assistant Store/auth/Options/reload tests only.

## Русский

Это копия для инженерной проверки, а не готовый мастер миграции. Публичного
действия импорта или включения пока нет. Не редактируйте `.storage`, не заменяйте
живое хранилище и не снимайте защиту вручную.

Копия создаётся только целиком в пустом целевом пространстве, с явно указанными
участниками и полным списком прав родителей. Непереносимая запись или расхождение
прав останавливают сборку. Задачи сохраняют номера; для покупок, баллов и
будильников сохраняется приватное сопоставление старых и новых номеров. Вся
исходная история остаётся в приватном архиве, а не в очереди сообщений или у LLM.

Копия доступна только владельцу и только для чтения. Модули, будильники, штрафы,
сообщения, фоновые проверки и обращения к устройствам отключены. Перезапуск или
завершение резервного копирования не включает её. Старый публичный релиз отвергает
специальную схему этой копии. Карточки показывают предупреждение и первые 20
доступных записей каждого раздела без кнопок изменения.

Это ещё не проверка реального захвата старой базы, не восстановление фотоотчётов
и не переключение домашнего бота. Согласованный захват, неоднозначные права,
фотографии и процедура включения требуют отдельной проверки. Рабочая домашняя
установка этим релизом не заменялась.

## Українська

Це копія для інженерної перевірки, а не готовий майстер міграції. Публічної дії
імпорту або активації поки немає. Не редагуйте `.storage`, не замінюйте робоче
сховище та не прибирайте захист вручну.

Копія створюється лише цілком у порожньому цільовому просторі, з явно визначеними
учасниками та повним переліком батьківських прав. Непереносний запис або
розбіжність прав зупиняє побудову. Завдання зберігають номери; для покупок, балів
і будильників залишається приватне зіставлення старих та нових номерів. Уся
початкова історія зберігається в приватному архіві, а не в черзі повідомлень чи LLM.

Копія доступна лише власнику та лише для читання. Модулі, будильники, штрафи,
повідомлення, фонові перевірки й звернення до пристроїв вимкнено. Перезапуск або
завершення резервного копіювання не активує її. Старий публічний реліз відхиляє
спеціальну схему копії. Картки показують попередження та перші 20 доступних
записів кожного розділу без кнопок зміни.

Це ще не перевірка реального знімка старої бази, не відновлення фотозвітів та не
перемикання домашнього бота. Узгоджений знімок, неоднозначні права, фотографії
та процедура активації потребують окремої перевірки. Робочу домашню установку
цим релізом не замінено.
