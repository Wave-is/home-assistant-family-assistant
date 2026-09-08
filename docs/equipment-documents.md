# Equipment documents / Документы оборудования / Документи обладнання

## English

Enable **Maintenance**, open its dashboard card, then **Documents → Add document**
under the equipment. Choose a file, name, type (manual/warranty/receipt/other) and
optional private note. **Upload privately** validates and stores the file for the
uploader only. Review it, then explicitly **Attach to equipment** to share with
current parents and the owner. Uploading is not attachment. Documents do not alter
equipment revisions, service schedules, tasks, stock, alarms or scores.

Files stay in private Home Assistant storage outside the HACS-managed component.
Nothing is sent to Telegram, AI or an external document provider. Children and
guests cannot upload or read these files. Unattached uploads expire according to
the media retention policy. Removing a member or changing their role revokes reads.

- PDF, static JPEG, PNG or WebP; at most 10 MiB per file and 10 attached documents
  per equipment item. PDF is limited to 100 pages and bounded object complexity.
- PDF parsing is strict and rejects encrypted files, forms, embedded files and
  interactive actions, including many linked PDFs. Rejection is deliberate; use
  a noninteractive copy. Verification runs in a bounded helper, not the HA event loop.
- **Download file** first obtains an authenticated private copy; click the resulting
  download link to save it. No document is previewed inline. Validation is not
  antivirus protection or a guarantee against all malicious/polyglot files.
  Original metadata may remain; use trusted documents and an updated local viewer.
- Only the owner may **Remove file**, after reviewing the warning and entering a
  reason. Access is revoked immediately; the collector later removes private bytes.
  Parent-visible history and existing backups remain. Removed history is shown in
  batches of 20; the complete retained document ledger is capped at 5,000 records.
- A lost response retains the exact request for **Retry exact request**. Changing
  equipment or identity invalidates the draft. Do not create a second request to
  work around an uncertain first one.

Use a verified Home Assistant backup before upgrading. Restoring files and their
Store metadata must be coherent; do not copy attachments into `www` or public URLs.
No migration of household documents is performed by installing this release.

## Русский

Включите **Обслуживание дома**, откройте его карточку и раздел
**Документы → Добавить документ** у нужного оборудования. Выберите файл, название,
тип и необязательную приватную заметку. **Загрузить приватно** сохраняет файл только
для загрузившего. После проверки нажмите **Прикрепить к оборудованию**: файл станет
доступен действующим родителям и владельцу. Дети и гости доступа не получают.
Документ не меняет регламенты, задачи, остатки, будильники или баллы.

Файлы хранятся приватно в HA, вне обновляемой через HACS папки. В Telegram и ИИ они
не отправляются. Неприкреплённые загрузки имеют срок хранения; изменение роли или
удаление участника отзывает доступ. Поддерживаются PDF и статичные JPEG/PNG/WebP,
до 10 МиБ; не более 10 прикреплённых документов на оборудование. PDF — до 100 страниц,
с ограничением сложности. Зашифрованные PDF, формы, вложения и интерактивные действия
(в том числе многие ссылки) отклоняются. Используйте неинтерактивную копию.

**Скачать файл** подготавливает приватную ссылку: нажмите её для сохранения. Встроенного
просмотра нет. Проверка формата — не антивирус; исходные метаданные могут сохраняться.
Используйте доверенные файлы и актуальную программу просмотра. Удаление доступно
только владельцу, с причиной и отдельным подтверждением: доступ прекращается сразу,
байты удаляются позднее. История для родителей и существующие резервные копии остаются.
История удалённых документов раскрывается по 20 записей; общий предел — 5 000 записей.

При потере ответа повторяется **тот же запрос**, без дубля. Смена пользователя или
оборудования отменяет устаревший черновик. Перед обновлением сделайте проверенную
резервную копию HA; файлы и их метаданные нужно восстанавливать согласованно.
Не помещайте документы в `www` или по публичным ссылкам. Установка ничего не переносит
из домашней системы автоматически.

## Українська

Увімкніть **Обслуговування дому**, відкрийте картку та розділ
**Документи → Додати документ** потрібного обладнання. Виберіть файл, назву, тип і
необов'язкову приватну примітку. **Завантажити приватно** зберігає файл лише для того,
хто його завантажив. Після перевірки натисніть **Прикріпити до обладнання**: доступ
отримають чинні батьки й власник. Діти та гості доступу не мають. Документи не змінюють
регламенти, завдання, запаси, будильники або бали.

Файли зберігаються приватно в HA, поза папкою оновлення HACS. До Telegram чи ШІ вони
не надсилаються. Неприкріплені файли мають строк зберігання; зміна ролі або видалення
учасника відкликає доступ. Дозволено PDF і статичні JPEG/PNG/WebP до 10 МіБ, не більше
10 прикріплених документів на обладнання. PDF — до 100 сторінок з обмеженням складності.
Зашифровані PDF, форми, вкладення та інтерактивні дії (зокрема багато посилань)
відхиляються. Використовуйте неінтерактивну копію.

**Завантажити файл** готує приватне посилання: натисніть його для збереження. Вбудованого
перегляду немає. Перевірка формату — не антивірус; початкові метадані можуть залишатися.
Використовуйте довірені файли й актуальний переглядач. Видалення доступне лише власнику,
з причиною та окремим підтвердженням. Доступ припиняється одразу, байти видаляються згодом.
Історія для батьків та наявні резервні копії залишаються. Історія видалених документів
розкривається по 20 записів; загальна межа — 5 000 записів.

За втрати відповіді повторюється **той самий запит**, без дублювання. Зміна користувача
або обладнання скасовує застарілу чернетку. Перед оновленням створіть перевірену резервну
копію HA; файли та їхні метадані слід відновлювати узгоджено. Не кладіть документи в
`www` чи за публічними посиланнями. Встановлення не переносить домашні документи автоматично.
