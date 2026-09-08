# Read-only copy staging / Запись проверочной копии / Запис перевірочної копії

## English

The internal `migration.shadow_install.async_stage_shadow` API prepares a **new,
unregistered** read-only copy. It is an engineering building block, not a public
import button, activation endpoint or permission to replace a live household.
Source capture, member/photo matching and an explicit whole-candidate owner review
remain caller prerequisites; staging does not prove source coherence.

The full candidate is reconstructed from the original private source archive,
member bindings, complete reviewer policy and freshly decoded photo evidence.
Projected records, supplied summary, blobs and exact target must agree with that
reconstruction. A current active HA administrator must also be the bound owner.
Identity and target pins are checked again across awaits. Registered or running
entries, another Store, a different staging intent, an unclaimed existing private
directory or an active backup refuse the operation.

An immutable native HA **Store intent** is written first. Verified private blobs
are published without replacing existing files and checked before a single final
native Store write. No `.storage` file is edited directly. The shared setup lock
coordinates staging with runtime setup/backup. No source file, existing household,
entity, device, provider or ConfigEntry is changed or created by this method.

An interrupted or uncertain Store write retains the intent and verified blobs.
An exact retry checks the committed state, or resumes staging, including after
process-local coordination is recreated. Cancellation drains an owned write before
releasing the lock. Different data never overwrites an earlier attempt. Unknown,
damaged or abruptly abandoned temporary files stop recovery for review; this API
does not guess ownership, delete residues or promise automatic recovery from every
filesystem/power-loss state. Reviewed cleanup remains pending; a separate internal
[sealed registration method](legacy-shadow-registration.md) now exists.

A successful receipt means only **read-only shadow staged**. It does not register
or activate the entry. Its receipt now also carries the exact ConfigEntry seal
for the separate registration step. The synthetic native-HA test separately registers its
disposable entry and verifies first setup, owner-only private photo reads, child
denial, zero entities/workers and exact reload. The source installation is untouched.

## Русский

Внутренний метод `async_stage_shadow` записывает **новую, ещё не зарегистрированную**
проверочную копию. Это часть будущего мастера, а не публичная кнопка импорта или
включения. Согласованный снимок источника, сопоставление семьи и фотографий и явная
проверка всей копии владельцем остаются отдельными условиями. Метод сам не доказывает
согласованность старых данных и не разрешает заменять работающую семью.

Перед записью копия заново собирается из исходного приватного архива, привязок
участников, полного списка прав проверяющих и декодированных фотографий. Проверяется
точное совпадение данных и отпечатков. Нужен действующий администратор HA, привязанный
как владелец. Права проверяются повторно после ожиданий. Уже зарегистрированная
запись, работающий модуль, чужое хранилище/каталог, другой план переноса или резервное
копирование блокируют запись.

Сначала через стандартный Store HA сохраняется неизменяемый план попытки, затем
без перезаписи публикуются и проверяются фотографии. Хранилище самой копии записывается
последним. Файлы `.storage` напрямую не редактируются. Метод не меняет источник,
существующую семью, устройства или провайдеры и не создаёт запись интеграции.

При неясном результате остаются план и проверенные файлы. Точный повтор проверит
завершённую запись либо продолжит попытку; отмена ждёт завершения уже начатой записи.
Другие данные поверх старых не записываются. Неизвестные, повреждённые или оставшиеся
после аварийной остановки временные файлы требуют разбора — автоматического удаления
нет. Не обещается восстановление любого сбоя питания или файловой системы.

Успех означает только «проверочная копия записана». Регистрации и включения нет.
В изолированном тесте HA отдельным шагом создаётся тестовая запись, проверяются
фотографии только для владельца, запрет ребёнку, отсутствие сущностей/фоновых
процессов и перезагрузка. Домашняя рабочая система не переключалась.

Результат записи также содержит точную защитную отметку для отдельного внутреннего
[метода регистрации](legacy-shadow-registration.md). Это не публичный мастер и не
разрешение включить перенесённые автоматизации.

## Українська

Внутрішній метод `async_stage_shadow` записує **нову, ще не зареєстровану**
перевірочну копію. Це частина майбутнього майстра, а не публічна кнопка імпорту чи
активації. Узгоджений знімок джерела, зіставлення учасників/фотографій та явна
перевірка всієї копії власником залишаються окремими передумовами. Сам метод не
доводить узгодженість джерела та не дозволяє замінювати робочу родину.

Копія повторно будується з оригінального приватного архіву, прив’язок учасників,
повного переліку прав перевіряльників і декодованих фотографій. Дані та відбитки
мають точно збігатися. Потрібен активний адміністратор HA, прив’язаний як власник;
права повторно перевіряються після очікувань. Наявний запис інтеграції, робочий модуль,
чуже сховище/каталог, інший план перенесення або резервне копіювання блокують дію.

Спочатку стандартний Store HA зберігає незмінний план спроби. Далі без перезапису
публікуються й перевіряються фотографії; сховище самої копії записується останнім.
Файли `.storage` не редагуються напряму. Джерело, робоча родина, пристрої та
провайдери не змінюються; запис інтеграції не створюється.

За невідомого результату зберігаються план і перевірені файли. Точний повтор
перевіряє завершений запис або продовжує спробу; скасування чекає на вже розпочатий
запис. Інші дані не перезаписують попередню спробу. Невідомі, пошкоджені чи залишені
після аварійної зупинки тимчасові файли потребують розгляду — автоматичного видалення
немає. Відновлення будь-якого збою живлення чи файлової системи не гарантується.

Успіх означає лише «перевірочну копію записано», без реєстрації та активації.
В ізольованому тесті HA окремо створюється тестовий запис, перевіряються доступ
власника до фотографій, відмова дитині, відсутність сутностей/фонових процесів і
перезавантаження. Домашню робочу систему не перемикали.

Результат запису також містить точну захисну позначку для окремого внутрішнього
[методу реєстрації](legacy-shadow-registration.md). Це не публічний майстер і не
дозвіл активувати перенесені автоматизації.
