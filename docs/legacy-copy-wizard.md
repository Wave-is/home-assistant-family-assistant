# Legacy copy wizard / Мастер проверочной копии / Майстер перевірочної копії

[Source consistency and deterministic private packaging / Согласованность и сборка
архива / Узгодженість і створення архіву](legacy-source-links.md)

[Interrupted upload recovery / Восстановление после обрыва /
Відновлення після переривання](legacy-recovery.md)

[Resume a complete saved copy / Продолжить сохранённую копию /
Продовжити збережену копію](legacy-copy-resume.md)

## English

For guided preparation from the two source files instead of a hand-built ZIP,
use [Prepare a read-only copy from exports](legacy-preparation.md).

This advanced **read-only migration review** passed an isolated native HA test. It is not
automatic source discovery, a general backup importer or activation of an old
installation. Start with an isolated public-integration instance. Do not replace
a running legacy integration to make this menu appear: both use the same domain,
so a controlled, separately verified cutover is still required.

1. Obtain a coherent private export and rollback copy using the source's supported
   API/backup procedure. Independently copied live Stores are not proof of a
   coherent capture. Stop here if old records, pending operations or reviewer
   authority cannot be reconciled. Never send this export to an LLM or public issue.
2. Configure the destination family members and HA bindings normally. The wizard
   uses their exact IDs/revisions; it does not guess people or roles from names.
   Prepare the private bundle described below, including complete effective legacy
   reviewer sets and all historical photo-submission matches. Inspect the actual
   photographs locally first. The separate preparation wizard can collect these
   associations and package the files; coherent source export remains a prerequisite.
3. As the original household owner, also an active HA administrator, choose
   **Configure → Legacy read-only copy**. Supply a distinct copy name and the ZIP.
   Review every associations page. It includes participants, reviewer sets and
   photo-event/digest/file links. A stale page confirmation cannot advance another
   page. These are associations, not a machine proof of what a photo depicts.
4. Review the whole-copy counts and fingerprint and explicitly confirm creation.
   Before this confirmation, no Family Assistant Store or ConfigEntry is written.
   HA manages the temporary uploaded file and removes it after consumption;
   local bounded image verification can use temporary files.
5. A separate sealed ConfigEntry is created, with an owner-only dashboard view.
   The current prototype and original source are not overwritten. All copied
   alarms remain disabled; no messages, sirens, penalties or network effects run.
   Finish closes the review without updating the prototype's options.

On either review step, select **Discard this review only** to release the private
review slot immediately. This never deletes an already-created copy or its saved
retry intent, including after an uncertain result.

Only one private review is retained in memory, for 15 minutes; it has a maximum
of 1,000 association rows, shown ten per page. Changed authority, members, runtime,
language/time zone or expiry invalidates the review. After an uncertain result or
restart, reuse **the same ZIP bytes, copy name and unchanged destination members**.
An immutable native Store intent retains the ID/preparation time for the exact
package and target. Do not rename/rebuild the archive to recover an uncertain
attempt. Registered does not necessarily mean loaded; the UI reports this
distinction without forcing an unloaded entry to start.

### Private bundle format

The ZIP is a classic single-volume archive (no ZIP64), at most **96 MiB**. It has
only `manifest.json` and the declared `photos/KEY` files, no directory entries,
symlinks, encrypted members, traversal names or extra files. Only stored/deflated
compression is supported. The parser validates the central-directory size/count
before allocating ZIP entries and never extracts the archive into a directory.

The UTF-8 JSON manifest is at most 24 MiB, without duplicate keys or non-finite
numbers. It has exactly these fields:

| Field | Required value |
| --- | --- |
| `version` | Integer `1`, not a boolean |
| `kind` | `family_assistant_legacy_shadow` |
| `assistant_store` | Canonical base64 of the exact Assistant Store-wrapper bytes, at most 8 MiB decoded; key `family_assistant.tasks`, version 1 |
| `court_store` | Canonical base64 of the exact Court Store-wrapper bytes, at most 8 MiB decoded; key `family_court.ledger`, version 1 |
| `member_mapping` | Legacy ID → `{member_id, member_revision}`, or `{archive_only: true}` only where permitted by preflight |
| `reviewer_sets` | Each report-required task ID → the **complete** list of its effective legacy reviewer IDs, not just the last reviewer |
| `photos` | List of the exact historical associations below; empty only if no submission image is required |

Each photo association has exactly `task_id`, positive integer `event_sequence`,
lowercase 64-hex `report_sha256` and a unique `attachment_key` (1–64 ASCII letters,
digits or underscores). The ZIP contains `photos/attachment_key` with its actual
image bytes. The digest identifies the original report note, not the image;
source inventory must produce it from the exact historical submission. The
existing bounded decoder independently validates image bytes and preserves
verified canonical evidence. Maximum 512 photos, 10 MiB each and 64 MiB total.

All source JSON, mappings, history and images remain private in HA. The package
is **not encrypted**: keep it in private local storage, never in the HACS/public
repository. No household credentials or provider configuration belongs in it.
Unknown records, missing photos or changed reviewer rights block the whole copy;
there is no partial import or automatic privilege expansion.

## Русский

Расширенный **мастер проверки копии только для чтения** прошёл изолированный тест HA.
Это не автоматический поиск источника, не импорт любого бэкапа и не включение
старых автоматизаций. Используйте отдельный тестовый экземпляр публичной
интеграции. Не заменяйте рабочую старую интеграцию ради появления меню: их домен
совпадает, поэтому настоящее переключение требует отдельной проверки.

Сначала получите согласованный приватный экспорт и точку возврата штатным API
или резервным копированием источника. Две независимо скопированные рабочие базы
не доказывают согласованность. Настройте участников и привязки HA в новой семье,
затем подготовьте ZIP по таблице выше с точными ID/ревизиями, полными списками
проверяющих и всеми историческими фото. Реальные фотографии проверьте локально.
[Отдельный мастер подготовки](legacy-preparation.md#русский) собирает архив через
выбор участников, проверяющих и фото. Получение согласованного экспорта остаётся
отдельной процедурой. Архив нельзя отправлять модели или в публичный issue.

Первоначальный владелец семьи, также администратор HA, открывает **Настроить →
Проверочная копия старой семьи**. Укажите отдельное название, загрузите ZIP,
проверьте каждую страницу связей, затем общие количества и отпечаток. Только
последнее явное подтверждение разрешает запись копии. До него штатно существует
лишь временный загруженный файл HA и временные файлы проверки изображений —
хранилища Family Assistant и запись интеграции не создаются.

Создаётся отдельная защищённая запись, доступная для просмотра только владельцу.
Исходная и текущая семья не перезаписываются; скопированные будильники выключены,
сообщения, сирены, штрафы и сетевые команды не запускаются. После завершения
выберите копию по имени в карточке дашборда. Не снимайте защитную отметку ради запуска.

На любом шаге проверки можно выбрать **Отменить только проверку**. Это сразу
освободит место для новой проверки, не удаляя уже созданную копию и сохранённый
план повтора, в том числе после потери ответа.

Одновременно хранится одна проверка на 15 минут, до 1 000 строк по десять на
странице. Смена участников, прав, рабочего модуля, языка/часового пояса или истечение
срока отменяет проверку. После потери ответа или перезапуска повторно используйте
**тот же файл ZIP, название копии и неизменённый состав участников**. Сохранённый
план удерживает прежние ID и время подготовки. Регистрация без загрузки показывается
отдельно и не вызывает принудительный запуск.

Формат ZIP/JSON строго соответствует таблице: до 96 МиБ, без ZIP64, каталогов,
ссылок и лишних файлов; только `manifest.json` и `photos/KEY`. До 512 фото, по
10 МиБ и всего 64 МиБ. Архив не распаковывается в каталог. Отпечаток отчёта относится
к точной исторической записи, а не к содержанию снимка. Архив **не зашифрован**:
храните его приватно и никогда не добавляйте в публичный репозиторий. Пароли и
настройки провайдеров туда не включаются. Неполные данные или изменённые права
блокируют всю копию; частичного импорта и автоматической выдачи прав нет.

## Українська

Розширений **майстер перевірки копії лише для читання** пройшов ізольований тест HA.
Це не автоматичний пошук джерела, не імпорт довільного бекапу та не активація старих
автоматизацій. Використовуйте окремий тестовий екземпляр публічної інтеграції. Не
замінюйте робочу стару інтеграцію заради меню: їхній домен збігається, а справжнє
перемикання потребує окремої перевірки.

Спочатку отримайте узгоджений приватний експорт і точку повернення штатним API чи
резервним копіюванням джерела. Незалежні копії двох робочих сховищ не доводять
узгодженість. Налаштуйте учасників та прив’язки HA в новій родині, підготуйте ZIP
за таблицею вище з точними ID/ревізіями, повними переліками перевіряльників та всіма
історичними фото. Самі фотографії перевірте локально. Підготовка архіву поки
можлива через [окремий майстер](legacy-preparation.md#українська), де вибирають
учасників, перевіряльників і фото. Узгоджений експорт отримують окремою процедурою.
Не надсилайте архів моделі чи до публічного issue.

Початковий власник родини, також адміністратор HA, відкриває **Налаштувати →
Перевірочна копія старої родини**. Укажіть окрему назву, завантажте ZIP, перевірте
кожну сторінку зв’язків, потім загальні кількості та відбиток. Лише останнє явне
підтвердження дозволяє запис. До нього є тільки штатний тимчасовий файл HA та
тимчасові файли перевірки зображень, без запису сховища чи інтеграції Family Assistant.

Створюється окремий захищений запис із переглядом лише для власника. Вихідна й
поточна родина не перезаписуються; скопійовані будильники вимкнені, повідомлення,
сирени, штрафи й мережеві команди не запускаються. Після завершення виберіть копію
за назвою у картці дашборда. Не прибирайте захисну позначку заради активації.

На будь-якому кроці перевірки можна вибрати **Скасувати лише перевірку**. Це одразу
звільнить місце для нової перевірки, не видаляючи вже створену копію та збережений
план повтору, зокрема після втрати відповіді.

Одночасно зберігається одна перевірка на 15 хвилин, до 1 000 рядків по десять на
сторінці. Зміна учасників, прав, модуля, мови/часового поясу чи завершення строку
скасовує перевірку. Після втрати відповіді або перезапуску повторно використайте
**той самий ZIP, назву копії та незмінний склад учасників**. Збережений план
утримує попередні ID й час підготовки. Реєстрація без завантаження показується
окремо та не спричиняє примусового запуску.

ZIP/JSON має точно відповідати таблиці: до 96 МіБ, без ZIP64, каталогів, посилань
і зайвих файлів; тільки `manifest.json` та `photos/KEY`. До 512 фото, по 10 МіБ,
разом 64 МіБ. Архів не розпаковується в каталог. Відбиток звіту стосується точної
історичної події, а не змісту фотографії. Архів **не зашифрований**: зберігайте його
приватно, ніколи не додавайте до публічного репозиторію. Паролі й налаштування
провайдерів до нього не включаються. Неповні дані чи змінені права блокують усю
копію; часткового імпорту й автоматичного надання прав немає.
