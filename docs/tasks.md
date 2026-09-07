# Tasks / Задачи / Завдання

## English

Use the task card to set an assignee, optional deadline, checklist (one step per
line) and text, photo or no-text report. Deadlines use the household time zone, not the
phone's zone. Nonexistent local times are rejected; repeated times require a
first/second occurrence choice. Unchanged deadlines retain exact seconds.

An assignee can accept, start, check steps and submit a report. Parents confirm
completion or request changes with a note; submitted tasks are read-only for
the assignee. Parents can also confirm completion manually. Other members may
edit/cancel only tasks they created and still own. Guests cannot change tasks.

Clearing the deadline stops pending reminders. Title edits keep progress.
Reassignment keeps previous reports in local history and supersedes old queued
assignment/review notices. Existing score events are not automatically reversed.
Finished tasks remain in the collapsed archive. Recurring duties create separate
tasks with optional rotation; edits preserve history and omitted optional fields.
Automatic penalties default off. A text report cannot substitute for a required photo.

The recurring-task editor reviews the complete definition before saving: the
original creator, exact current assignees, rotation mode, recurrence, release and
due times, checklist, report type, reminder, grace period and optional penalty.
The original creator is immutable. A member revision change pauses the whole
series, including rotation, until a parent explicitly reviews and saves the
current identities; it never silently transfers work to a same-ID replacement.
Older definitions without identity lineage are parent-visible but inert until
reviewed. If the original creator is no longer an active parent, the series
cannot be transferred or repaired, although it can be disabled.

Saving a definition starts its newly reviewed schedule from that moment. It does
not create a backlog or alter tasks already generated. A due time earlier than
the release time means the next local day. Spring-gap times and nonexistent
monthly dates are skipped; repeated autumn time uses the first occurrence. A
zero-hour catchup setting still permits an approximately one-minute window.
Photo-report series create ordinary private photo tasks; upload and submission
remain separate explicit actions in the task card.

For a photo report, choose one JPEG, PNG or WebP (up to 10 MiB), review it and
explicitly confirm upload. Uploading alone does not submit the task: confirm
**Submit photo report** separately. If a response is lost, the retry uses the
same reviewed file and request; a changed task or identity requires a new review.
Photos are private Home Assistant files, not public links. The current assignee
and authorized parents can explicitly load the report; only parents see retained
previous reports. Original embedded metadata, including possible location data,
is retained. Images are not sent to Telegram, search, OCR or an LLM. HEIC, animated
images and PDF are not accepted. Unsubmitted uploads expire; submitted reports
stay in task history. This feature is in development; backup/retention acceptance
is still a release gate. See [media design and limits](media-design.md).

## Русский

В карточке задаются исполнитель, срок, шаги чек-листа и тип отчёта: текст, фото
или без текста. Срок — в часовом поясе семьи, а не телефона. При переводе часов
выберите первое или второе вхождение повторяющегося времени.

Исполнитель принимает задачу, начинает работу, отмечает шаги и сдаёт отчёт.
Родитель подтверждает выполнение или возвращает на доработку с замечанием.
На проверке исполнитель не меняет задачу. Родитель может подтвердить выполнение
вручную. Остальные редактируют и отменяют только задачи, которые сами создали
и которые по-прежнему назначены им. Гости ничего не меняют.

Очистка срока отменяет ожидающее напоминание. Правка названия не сбрасывает
прогресс. Переназначение сохраняет старый отчёт в локальной истории и отменяет
неотправленные уведомления старому исполнителю. Уже начисленные баллы отменяются
отдельно в суде. Завершённые задачи остаются в сворачиваемом архиве.
Регулярные обязанности создают отдельные задачи, в том числе по очереди.
Правка серии сохраняет историю и неуказанные дополнительные настройки.
Автоштрафы по умолчанию выключены. Текст не подменяет обязательный фотоотчёт.

Редактор регулярных задач перед сохранением показывает всю конфигурацию:
первоначального создателя, точные текущие версии исполнителей, ротацию,
расписание, время создания и срок, чек-лист, тип отчёта, напоминание, льготный
период и необязательный штраф. Первоначальный создатель неизменяем. После смены
версии участника вся серия, включая ротацию, приостанавливается до явной проверки
и сохранения родителем; работа не переходит молча новому человеку с тем же ID.
Старые серии без данных о версиях видны родителям, но не выполняются до проверки.
Если создатель больше не активный родитель, серию нельзя передать или исправить,
но можно выключить.

Сохранение запускает заново проверенное расписание с этого момента: пропущенные
задачи не создаются, уже созданные не меняются. Если срок раньше времени создания,
он наступает на следующий местный день. Несуществующее весеннее время и
несуществующие даты месяца пропускаются; при осеннем повторе берётся первое
вхождение. Нулевое окно наверстывания всё равно даёт примерно одну минуту.
Серия с фотоотчётом создаёт обычные приватные фотозадачи; загрузка и отправка
остаются отдельными явными действиями в карточке задач.

Для фотоотчёта выберите один JPEG, PNG или WebP до 10 МиБ, проверьте его и
подтвердите загрузку. Она ещё не сдаёт задачу: отдельно подтвердите
**Отправить фотоотчёт**. При потере ответа повторяется тот же файл и запрос;
изменение задачи или участника потребует новой проверки. Фото хранится приватно
в Home Assistant, без публичной ссылки. Текущий исполнитель и уполномоченные
родители открывают отчёт отдельной кнопкой; прежние отчёты видят только родители.
Встроенные метаданные оригинала, в том числе возможная геолокация, сохраняются.
Изображения не отправляются в Telegram, поиск, OCR или LLM. HEIC, анимация и PDF
не принимаются. Несданные загрузки истекают; сданные отчёты остаются в истории.
Функция пока в разработке: проверка резервного копирования и политики хранения
ещё обязательна перед релизом.

## Українська

У картці задаються виконавець, строк, кроки чек-листа та тип звіту: текст, фото
або без тексту. Строк — у часовому поясі сім’ї, а не телефона. Під час переведення
годинника виберіть перше чи друге входження повторюваного часу.

Виконавець приймає завдання, починає роботу, позначає кроки та здає звіт.
Батьки підтверджують виконання або повертають на доопрацювання із зауваженням.
Під час перевірки виконавець не змінює завдання. Батьки можуть підтвердити
виконання вручну. Інші редагують і скасовують лише власні створені завдання,
досі призначені їм. Гості нічого не змінюють.

Очищення строку скасовує очікуване нагадування. Зміна назви не скидає прогрес.
Перепризначення зберігає старий звіт у локальній історії та скасовує ненадіслані
сповіщення старому виконавцю. Нараховані бали скасовуються окремо в суді.
Завершені завдання залишаються в архіві. Регулярні обов’язки створюють окремі
завдання, зокрема по черзі. Зміна серії зберігає історію та невказані додаткові
налаштування. Автоштрафи за замовчуванням вимкнені. Текст не підміняє обов’язковий
фотозвіт.

Редактор регулярних завдань перед збереженням показує всю конфігурацію:
початкового автора, точні поточні версії виконавців, ротацію, розклад, час
створення і строк, чекліст, тип звіту, нагадування, пільговий період і
необов’язковий штраф. Початковий автор незмінний. Після зміни версії учасника вся
серія, зокрема ротація, призупиняється до явної перевірки й збереження батьками;
робота не переходить мовчки новій людині з тим самим ID. Старі серії без даних
про версії бачать батьки, але вони не виконуються до перевірки. Якщо автор більше
не є активним із батьківською роллю, серію не можна передати чи виправити, але
можна вимкнути.

Збереження запускає заново перевірений розклад із цього моменту: пропущені
завдання не створюються, уже створені не змінюються. Якщо строк раніше часу
створення, він настає наступного місцевого дня. Неіснуючий весняний час і
неіснуючі дати місяця пропускаються; при осінньому повторі береться перше
входження. Нульове вікно наздоганяння все одно дає приблизно одну хвилину. Серія
з фотозвітом створює звичайні приватні фотозавдання; завантаження й надсилання
залишаються окремими явними діями у картці завдань.

Для фотозвіту виберіть один JPEG, PNG або WebP до 10 МіБ, перевірте його й
підтвердьте завантаження. Воно ще не здає завдання: окремо підтвердьте
**Надіслати фотозвіт**. Після втрати відповіді повторюються той самий файл і запит;
зміна завдання чи учасника потребує нової перевірки. Фото зберігається приватно
в Home Assistant, без публічного посилання. Поточний виконавець та уповноважені
батьки відкривають звіт окремою кнопкою; попередні звіти бачать лише батьки.
Вбудовані метадані оригіналу, зокрема можлива геолокація, зберігаються.
Зображення не надсилаються до Telegram, пошуку, OCR або LLM. HEIC, анімація та PDF
не приймаються. Нездані завантаження спливають; здані звіти залишаються в історії.
Функція ще в розробці: перевірка резервного копіювання й політики зберігання
залишається обов’язковою перед релізом.
