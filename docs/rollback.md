# Rollback and recovery guide / Руководство по откату и восстановлению / Посібник із відкату та відновлення

[Application upgrade acceptance / Проверка обновления / Перевірка оновлення](release-upgrade-acceptance.md)

[Interrupted copy recovery / Восстановление после обрыва / Відновлення після переривання](legacy-recovery.md)

[Release policy / Политика релизов / Політика релізів](release.md)

## English

Family Assistant is designed around atomic persistence, durable operation receipts,
and explicit boundaries. When an update, migration, or network command encounters an
issue, rollback restores a safe state without corrupting family data or leaking private
records.

### 1. Data isolation and storage boundaries

Family Assistant stores all operational household state in Home Assistant's native Store:

- **Household state**: `.storage/family_assistant.<entry_id>` — includes members, tasks,
  shopping, court, alarms, routines, network plans, and outbox.
- **Media blobs**: `family_assistant_data/<entry_hash>/` — stores verified image files,
  task attachments, and equipment documents.
- **Recovery journals**: `family_assistant_recovery/` — temporary staging and interrupted
  migration artifacts, kept strictly isolated from active household data.

A code upgrade or rollback **never** deletes or mutates Store files directly. Replacing
the integration files under `custom_components/family_assistant` preserves all existing
storage files verbatim.

### 2. Integration code rollback

To roll back to a previous release:

1. Stop Home Assistant or use HACS to install the desired previous release version.
2. If restoring manually, replace `custom_components/family_assistant/` with the exact
   runtime release package (e.g. from the published GitHub release archive).
3. Restart Home Assistant.
4. The previous integration version will boot, reload the existing Store, and resume
   scheduled operations. The immutable `schema_version` guard ensures that any schema
   incompatibility fails closed rather than corrupting data.

### 3. Migration copy rollback and cleanup

When using the legacy copy wizard or source preparation wizard:

- The migration candidate is created with `schema_version: "legacy-shadow-v1"` in an
  isolated, read-only shadow state.
- If migration is interrupted or discarded, selecting **Discard only this review**
  clears in-memory staging without modifying the running household or deleting saved intents.
- Temporary uploaded photos in `family_assistant_recovery/` can be safely inspected or
  retained via the recovery screen.
- A shadow copy cannot execute commands, trigger sirens, or send notifications; removing
  a shadow Config Entry in Home Assistant leaves the original installation completely unaffected.

### 4. RouterOS / MikroTik rollback

Network configuration operations enforce strict read-back and target-scoped rollback:

- **Static lease creation**: Before converting a dynamic DHCP lease, a snapshot of the
  existing lease state is taken. A failed read-back triggers scoped removal of the new
  reservation; the client recovers via DHCP renewal.
- **Kid Control profile modifications**: Changes to rates or schedules are applied with
  exact diffs. If the router rejects an update, previous state is retained.
- **Strict enforcement**: Strict mode cannot be activated without passing 8 hard
  preconditions. If conditions change, strict mode disengages cleanly without breaking
  connectivity.

### 5. Clock rollback protection

If the host system clock rolls backward (e.g. due to NTP synchronization or battery faults):

- **Alarms**: Nonce challenges and expired runs remain expired; clock regression cannot
  re-trigger a previously finished or dismissed alarm challenge.
- **School reminders and digests**: A monotonic pruning floor (`retired_through`) prevents
  clock rollback from regenerating previously sent notifications or reminders.
- **Outbox**: Deduplication keys prevent re-delivery of delivered messages after a time jump.

---

## Русский

Архитектура Family Assistant построена на принципах атомарной фиксации состояния,
долговечных квитанций операций и жестких границах изоляции. При возникновении ошибок
обновления, миграции или сетевого взаимодействия механизм отката возвращает систему
в безопасное состояние без повреждения семейных данных и утечки приватных записей.

### 1. Изоляция данных и границы хранения

Все рабочие данные семейного пространства хранятся в штатном хранилище Home Assistant:

- **Состояние семьи**: `.storage/family_assistant.<entry_id>` — участники, задачи,
  покупки, суд, будильники, расписания, сетевые планы и исходящие сообщения.
- **Медиафайлы**: `family_assistant_data/<entry_hash>/` — проверенные изображения,
  вложения к отчетам и документы оборудования.
- **Журналы восстановления**: `family_assistant_recovery/` — временные остатки и файлы
  прерванных копий, изолированные от рабочей семьи.

Обновление или откат версии кода **никогда** не изменяет и не удаляет файлы хранилища
напрямую. Замена файлов в каталоге `custom_components/family_assistant` сохраняет все
пользовательские данные в неизменном виде.

### 2. Откат версии интеграции

Для возврата на предыдущую версию:

1. Остановите Home Assistant или выберите предыдущую версию в HACS.
2. При ручной установке замените каталог `custom_components/family_assistant/` файлами
   из проверенного архива релиза.
3. Запустите Home Assistant.
4. Предыдущая версия интеграции загрузится, прочитает существующее хранилище и возобновит
   работу. Защитная проверка `schema_version` гарантирует, что несовместимая схема
   приведет к безопасной остановке, а не к повреждению базы.

### 3. Откат и очистка проверочной копии

При использовании мастера проверочной копии старой семьи:

- Копия создается со специальной схемой `schema_version: "legacy-shadow-v1"` в режиме
  чтения без запуска автоматизаций.
- При прерывании или отмене кнопка **Отменить только проверку** освобождает память,
  не затрагивая рабочую семью и сохраняя план повтора.
- Временные загруженные фотографии в `family_assistant_recovery/` сохраняются и могут быть
  безопасно проверены через экран восстановления.
- Копия для проверки не может отправлять сообщения, включать сирены или менять роутер;
  удаление записи Config Entry в Home Assistant никак не влияет на основную установку.

### 4. Откат изменений MikroTik / RouterOS

Сетевые операции используют обязательное обратное чтение (read-back) и точечный откат:

- **Статические лизы**: Перед преобразованием динамического лиза сохраняется снимок его
  состояния. Ошибка обратного чтения запускает удаление новой статической записи, а клиент
  продолжает работу через штатное обновление DHCP.
- **Kid Control**: Изменения скорости или расписаний применяются с точным diff. Ошибка
  роутера возвращает предыдущие параметры.
- **Строгий режим**: Не может включиться без выполнения матрицы из 8 предусловий. При
  нарушении топологии строгий режим безопасно блокируется без разрыва соединений.

### 5. Защита от перевода часов назад

При откате системного времени хоста (синхронизация NTP, сбой RTC):

- **Будильники**: Задания и завершенные запуски остаются завершенными; перевод часов
  не может повторно включить уже решенный будильник.
- **Напоминания и дайджесты**: Монотонная граница очистки (`retired_through`) исключает
  повторную отправку уже доставленных напоминаний и сводок.
- **Очередь сообщений**: Ключи дедупликации предотвращают повторную доставку сообщений.

---

## Українська

Архітектура Family Assistant ґрунтується на принципах атомарної фіксації стану,
довговічних квитанцій операцій і суворих межах ізоляції. У разі виникнення помилок
оновлення, міграції чи мережевої взаємодії механізм відкату повертає систему
в безпечний стан без пошкодження сімейних даних та витоку приватних записів.

### 1. Ізоляція даних і межі зберігання

Усі робочі дані сімейного простору зберігаються у штатному сховищі Home Assistant:

- **Стан родини**: `.storage/family_assistant.<entry_id>` — учасники, завдання, покупки,
  суд, будильники, розклади, мережеві плани та вихідні повідомлення.
- **Медіафайли**: `family_assistant_data/<entry_hash>/` — перевірені зображення,
  вкладення до звітів і документи обладнання.
- **Журнали відновлення**: `family_assistant_recovery/` — тимчасові файли перерваних
  копій, ізольовані від робочої родини.

Оновлення або відкат версії коду **ніколи** не змінює і не видаляє файли сховища
безпосередньо. Заміна файлів у каталозі `custom_components/family_assistant` зберігає всі
користувацькі дані в незмінному вигляді.

### 2. Відкат версії інтеграції

Для повернення на попередню версію:

1. Зупиніть Home Assistant або виберіть попередню версію в HACS.
2. У разі ручного встановлення замініть каталог `custom_components/family_assistant/`
   файлами з перевіреного архіву релізу.
3. Запустіть Home Assistant.
4. Попередня версія інтеграції завантажиться, прочитає наявне сховище та відновить
   роботу. Захисна перевірка `schema_version` гарантує, що несумісна схема
   призведе до безпечної зупинки, а не до пошкодження бази.

### 3. Відкат та очищення перевірочної копії

Під час використання майстра перевірочної копії старої родини:

- Копія створюється зі спеціальною схемою `schema_version: "legacy-shadow-v1"` у режимі
  читання без запуску автоматизацій.
- У разі переривання або скасування кнопка **Скасувати лише перевірку** звільняє пам'ять,
  не зачіпаючи робочу родину та зберігаючи план повтору.
- Тимчасові завантажені фотографії у `family_assistant_recovery/` зберігаються і можуть бути
  безпечно перевірені через екран відновлення.
- Копія для перевірки не може надсилати повідомлення, вмикати сирени чи змінювати роутер;
  вилучення запису Config Entry в Home Assistant жодним чином не впливає на основну установку.

### 4. Відкат змін MikroTik / RouterOS

Мережеві операції використовують обов'язкове зворотне читання (read-back) і точковий відкат:

- **Статичні лізи**: Перед перетворенням динамічного ліза зберігається знімок його
  стану. Помилка зворотного читання запускає вилучення нового статичного запису, а клієнт
  продовжує роботу через штатне оновлення DHCP.
- **Kid Control**: Зміни швидкості чи розкладів застосовуються з точним diff. Помилка
  роутера повертає попередні параметри.
- **Суворий режим**: Не може увімкнутися без виконання матриці з 8 передумов. У разі
  порушення топології суворий режим безпечно блокується без розриву з'єднань.

### 5. Захист від переведення годинника назад

У разі відкату системного часу хоста (синхронізація NTP, збій RTC):

- **Будильники**: Завдання та завершені запуски залишаються завершеними; переведення часу
  не може повторно ввімкнути вже вирішений будильник.
- **Нагадування й дайджести**: Монотонна межа очищення (`retired_through`) унеможливлює
  повторне надсилання вже доставлених нагадувань і зведень.
- **Черга повідомлень**: Ключі дедуплікації запобігають повторній доставці повідомлень.
