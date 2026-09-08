# Sealed copy registration / Регистрация копии / Реєстрація копії

## English

`migration.shadow_registration.async_register_shadow` is an **internal** reviewed
registration method, not a public command or migration wizard. Its caller must
have obtained the owner's explicit review of the complete source/member/reviewer/
photo candidate and retain the same fresh target ID for retries. The method
cannot prove source coherence and never authorizes activation or legacy cutover.

It reconstructs the candidate, stages exact Store/blobs, and registers a separate
native HA ConfigEntry with a read-only marker. The independent entry seal pins
the complete Store fingerprint and owner binding. Missing or altered data fails
setup before a runtime is constructed; it never falls through to a new empty
family. Restore the exact reviewed data through an appropriate verified recovery
process; do not remove the seal to bypass the failure.

An exact retry recognizes the same registered entry. A different owner, candidate,
title, configuration, Store or private blob set fails without overwrite or deletion.
Current active administrator-owner authority is rechecked across waits. A cancelled
owned Core registration is settled before releasing coordination. A lost reply
must be retried with the **same ID**, not a newly invented one.

The receipt distinguishes registered from loaded. A disabled/unloaded/retrying
entry is not force-reloaded and is never reported as a working viewer. Registration
uses Core's persistence lifecycle; atomic registration plus filesystem durability
under every possible power failure is not promised. Unknown staging residues still
need review. The [advanced private-copy wizard](legacy-copy-wizard.md) now calls
this method after upload and association review. Source bundle/mapping preparation
uses the [source preparation wizard](legacy-preparation.md). Indexed complete
attempts can [resume without reupload](legacy-copy-resume.md). Coherent source
capture still needs its own verified procedure; there is no activation endpoint.

## Русский

`async_register_shadow` — **внутренний** метод регистрации проверочной копии, а не
публичная команда или готовый мастер переноса. До вызова владелец должен явно
проверить весь набор исходных данных, участников, прав проверяющих и фотографий.
Для повторов сохраняется один новый идентификатор. Метод не доказывает согласованность
источника и не разрешает включать копию или заменять старую рабочую систему.

После повторной сборки и записи данных создаётся отдельная запись интеграции HA
с постоянной отметкой «только чтение». В ней закреплены отпечаток всех данных и
привязка владельца. Если данные отсутствуют или изменены, запуск прекращается до
создания рабочего модуля. Пустая семья вместо копии не создаётся. Нужно восстановить
точные проверенные данные подходящим проверенным способом, а не снимать защитную
отметку ради запуска.

Точный повтор узнаёт уже созданную запись. Другой владелец, набор данных, название,
настройки или фотографии вызывают отказ без перезаписи и удаления. Права действующего
администратора-владельца проверяются повторно после ожиданий. Отмена дожидается
завершения уже начатой регистрации. При потере ответа повторяется **тот же ID**.

Результат различает регистрацию и реально загруженный просмотрщик. Отключённая или
ожидающая повтора запись принудительно не запускается. Используется штатное
сохранение HA; атомарность всех файлов и регистрации при любом сбое питания не
обещается. Неизвестные остатки файлов требуют разбора. [Мастер загрузки и проверки
копии](legacy-copy-wizard.md#русский) вызывает этот метод после явного согласия.
[Подготовка из двух экспортов](legacy-preparation.md#русский) и
[продолжение сохранённой копии](legacy-copy-resume.md#русский) также доступны.
Согласованный экспорт требует отдельной проверки; включение копии пока отсутствует.

## Українська

`async_register_shadow` — **внутрішній** метод реєстрації перевірочної копії, не
публічна команда чи готовий майстер перенесення. Перед викликом власник має явно
перевірити всі вихідні дані, учасників, права перевіряльників і фотографії. Для
повторів зберігається один новий ідентифікатор. Метод не доводить узгодженість
джерела й не дозволяє активувати копію або замінювати робочу систему.

Після повторного складання та запису даних створюється окремий запис інтеграції HA
з постійною позначкою «лише читання». Вона закріплює відбиток усіх даних і прив’язку
власника. Відсутні чи змінені дані зупиняють запуск до створення робочого модуля;
порожня родина замість копії не створюється. Потрібно відновити точні перевірені
дані відповідним перевіреним способом, а не прибирати захисну позначку.

Точний повтор розпізнає наявний запис. Інший власник, дані, назва, налаштування чи
фотографії спричиняють відмову без перезапису або видалення. Права активного
адміністратора-власника повторно перевіряються після очікувань. Скасування чекає
завершення вже розпочатої реєстрації; за втрати відповіді повторюється **той самий ID**.

Результат розрізняє реєстрацію та справді завантажений переглядач. Вимкнений запис
або запис, що очікує повтору, примусово не запускається. Використовується штатне
збереження HA; атомарність усіх файлів та реєстрації за будь-якого збою живлення
не гарантується. Невідомі залишки файлів потребують розгляду. [Майстер завантаження
та перевірки копії](legacy-copy-wizard.md#українська) викликає цей метод після згоди.
[Підготовка з двох експортів](legacy-preparation.md#українська) та
[продовження збереженої копії](legacy-copy-resume.md#українська) також доступні.
Узгоджений експорт потребує окремої перевірки; активації копії ще немає.
