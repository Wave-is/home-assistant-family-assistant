# Source consistency and private packaging

## English

Two matching Store reads are not enough: the legacy Court can commit an automatic
minus before Assistant persists a task rollover or alarm acknowledgement. A
correction likewise spans a request, a score reversal and a saved acknowledgement.

Before constructing a whole read-only copy, `migration.source_links` checks both
sides of these explicit receipts. It requires exact source keys, the historical
assignee at the rollover (not today's possibly reassigned person), one system
assessment, and any requested reversal's acknowledgement and cancelled score.
Malformed, duplicate, missing or contradictory links block the whole copy. The
Options wizard gives a translated source-consistency error before creating a
Store/entry. No automatic repair, balance adjustment or history deletion occurs.

Ordinary manual Court decisions are not guessed to be automatic penalties. Old
alarm events outside the current Court period may have pruned runs: these are
counted as **archive-only**, not verified. A missing current-period alarm run
requires review. Passing this check is necessary but **does not prove coherent
capture**, settle all legacy processes or authorize activation. Obtain the final
export with the source's supported, separately reviewed capture procedure.

The pure internal helper `migration.copy_package.build_copy_bundle` now produces
the [documented private ZIP](legacy-copy-wizard.md) from exact Store-wrapper bytes,
member mappings, complete reviewer sets, historical photo associations and actual
selected attachment bytes. Keyword arguments are `assistant_store`, `court_store`,
`member_mapping`, `reviewer_sets`, `photos`, `attachments`. It does not fetch or
write files. Canonical JSON, fixed ZIP metadata, stored compression and sorted file
names preserve byte-identical retries for identical input. Source-file bytes and
list ordering remain exact; changing them intentionally changes the package.

Input counts/sizes and the final allocation are bounded before ZIP construction;
the independent parser rechecks its output. Packaging is not image validation or
member authorization: the wizard still performs those reviews. The archive is
unencrypted private data. Do not put it in Git, an LLM prompt, diagnostics or an
issue. A source exporter and user-friendly mapping editor remain separate work.

## Русский

Совпадение двух хранилищ с памятью ещё не доказывает согласованность: суд мог
сохранить автоматический минус раньше переноса задачи или подтверждения штрафа
будильника. Отмена минуса тоже состоит из запроса, отмены в суде и подтверждения
в задачах.

Перед созданием проверочной копии сверяются обе стороны этих записей: точные
ключи, исполнитель на момент события, отсутствие дублей, результат отмены и её
подтверждение. Текущий исполнитель не подставляется вместо прежнего после
переназначения. Несоответствие останавливает весь перенос до записи копии;
мастер показывает отдельную ошибку. Никакие баллы и исходные записи не исправляются
и не удаляются автоматически.

Ручные решения родителей не считаются автоматическими штрафами. Старые штрафы
будильника вне текущей отчётной недели могут не иметь уже очищенного запуска:
они учитываются только как архив, не как проверенные. Отсутствующий запуск для
текущей недели требует проверки. Успех этой сверки **не доказывает согласованность
самого экспорта** и не разрешает включение старых автоматизаций.

Внутренний `build_copy_bundle` собирает повторяемый ZIP из явно переданных
приватных данных по формату мастера: без чтения/записи файлов, получения снимков
из Telegram или угадывания участников. Лимиты проверяются до сборки, результат
повторно проверяет независимый парсер. Архив не зашифрован, его нельзя отправлять
модели или публиковать. Удобный экспортёр и редактор сопоставлений ещё не готовы.

## Українська

Збіг двох сховищ із пам’яттю ще не доводить узгодженість: суд міг зберегти
автоматичний мінус раніше за перенесення завдання чи підтвердження штрафу
будильника. Скасування мінуса також складається із запиту, скасування в суді
та підтвердження в завданнях.

Перед створенням перевірочної копії звіряються обидві сторони записів: точні
ключі, виконавець на момент події, відсутність дублів, результат скасування та
підтвердження. Поточного виконавця не підставляють замість попереднього після
перепризначення. Невідповідність зупиняє все перенесення до запису копії; майстер
показує окрему помилку. Жодних балів чи вихідних записів автоматично не виправляють
і не видаляють.

Ручні рішення батьків не вважаються автоматичними штрафами. Старі штрафи
будильника поза поточним звітним тижнем можуть не мати вже очищеного запуску:
їх враховують лише як архів, а не перевірені записи. Відсутній запуск поточного
тижня потребує перевірки. Успіх цієї звірки **не доводить узгодженість самого
експорту** й не дозволяє вмикати старі автоматизації.

Внутрішній `build_copy_bundle` створює повторюваний ZIP із явно переданих приватних
даних за форматом майстра: без читання/запису файлів, отримання фото з Telegram
чи вгадування учасників. Ліміти перевіряються до збірки, результат повторно
перевіряє незалежний парсер. Архів не зашифрований, його не можна надсилати моделі
чи публікувати. Зручний експортер і редактор зіставлень ще не готові.
