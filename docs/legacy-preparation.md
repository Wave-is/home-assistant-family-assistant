# Prepare a read-only copy from source files

## English

The native Options wizard can prepare the private copy package without writing
JSON mappings or assembling a ZIP yourself. It is still an **advanced migration
review**, not a live exporter, automatic identity discovery or activation.

Use a separate public-integration instance; do not replace the running legacy
domain merely to obtain this menu. First obtain a coherent private pair of schema-1
Assistant/Court Store exports and a rollback copy through a supported source
procedure. Independently copied live files do not establish coherence. Never
upload credentials, provider configuration or these exports to a model or issue.

1. Configure the destination family and HA-account bindings. Sign in as its
   original owner, also an active HA administrator.
2. Choose **Configure → Prepare a read-only copy from exports**. Enter a distinct
   copy name and select both `.json` files (at most 8 MiB each). If an effective
   old reviewer is absent from all source records, add their exact old ID in the
   additional-ID field, one per line. These are source IDs, not new display names.
3. For every old identity, explicitly select a destination participant. No name
   guessing or many-to-one merges occur. Optional archive-only identities gain
   no role. If a required participant is missing, discard and configure them first.
4. For each report-required task, select its **complete effective old reviewer
   set**, including the designated reviewer. Obtain this from the old configuration,
   not just a historical action. The wizard cannot prove a supplied policy is true.
   A difference from the destination parents blocks copying, not silently grants
   access. Do not omit a reviewer to make the check pass.
5. For each historical photo submission, select the original image after checking
   it locally. The task ID, sequence, timestamp and original report reference are
   shown privately. Supply every submission, not only the latest task image.
6. Review the combined associations, then the final counts/fingerprint, and
   explicitly confirm creation. Only then may a separate sealed, owner-only
   read-only entry be written. No copied alarms, bots, penalties or network jobs run.

There is one private in-memory review for 15 minutes, shared with direct ZIP
upload, and at most 1,000 association pages/rows combined. Files are consumed by
HA's authenticated temporary-upload helper; no arbitrary file path or URL is
accepted. Photographs are limited to 512, 10 MiB each and 64 MiB total; JPEG/PNG/WebP
content is independently decoded before final confirmation. Expiry, changed members,
language/zone/runtime or revoked authority invalidate the review.

Each page offers **Discard only this review**. This releases preparation memory,
never deletes an already-created copy or saved retry intent. After an uncertain
creation result, repeat the **same exact source files, selected photos, copy name
and member/reviewer associations with unchanged destination members**. The internal
deterministic packager retains the same package fingerprint and retry identity.
Different source/image bytes are a different package; do not use them to recover
an uncertain previous operation. There is no package download or automatic source
repair. Final source capture, staging-residue recovery, activation and controlled
cutover remain separate engineering/acceptance gates.

The [direct ZIP review](legacy-copy-wizard.md) remains available to advanced
operators. Both paths use the same final checks and sealed registration.

## Русский

Мастер **Настроить → Подготовить проверочную копию из экспортов** сам собирает
приватный пакет: писать JSON-сопоставления и вручную создавать ZIP больше не нужно.
Это проверочная копия, а не экспорт работающей системы и не включение автоматизаций.
Используйте отдельный экземпляр публичной интеграции: не заменяйте рабочий старый
домен ради появления меню.

Сначала получите согласованные экспорты Assistant и Court версии 1 штатной
процедурой источника и сохраните точку возврата. Два независимо скопированных
рабочих файла этого не доказывают. Настройте участников новой семьи и их HA-аккаунты.
Мастер доступен первоначальному владельцу семьи, также администратору HA.

Укажите название копии и два `.json`-файла (до 8 МиБ каждый). Дополнительное поле
позволяет указать старые ID проверяющих, отсутствующие в записях, по одному на строку.
Затем явно выберите нового участника для каждого старого ID. Имена не угадываются,
двух старых людей нельзя объединить в одного. Только допустимые исторические ID
можно оставить архивными, без выдачи роли. Если нужного участника нет, отмените
проверку и сначала настройте его.

Для каждой задачи с отчётом подтвердите **всех прежних проверяющих по настройкам**,
включая назначенного, а не только последнего принявшего задачу. Истинность указанного
списка мастер доказать не может. Отличие от родителей новой семьи блокирует копию:
нельзя исключать людей из списка ради обхода проверки.

Для каждого исторического фотоотчёта выберите его оригинал, проверив содержание
локально. Показаны ID задачи, номер события, время и исходная ссылка/заметка отчёта.
Нужны все сдачи, не только последнее фото. Проверьте итоговые связи, количества и
отпечаток, затем явно подтвердите создание отдельной копии только для чтения.
Исходная семья не меняется; сообщения, сирены, штрафы и сетевые операции не запускаются.

Общий с ZIP-мастером лимит — одна проверка на 15 минут и до 1 000 связей. До 512 фото,
по 10 МиБ и 64 МиБ всего; JPEG/PNG/WebP проверяются декодером до подтверждения.
Файлы принимает штатная временная загрузка HA, произвольных путей и URL нет.
Изменение прав, участников, языка, зоны или рабочего модуля отменяет проверку.
Кнопка отмены освобождает только подготовку: созданная копия и план повтора сохраняются.
После неопределённого результата повторите те же файлы, фото, название и сопоставления
при неизменённых участниках — ID и пакет сохранятся. Изменённые байты означают другой
пакет, а не восстановление прежней операции. Экспорты и пароли нельзя отправлять
модели или публиковать. Окончательный захват источника и рабочее переключение пока
требуют отдельной проверки.

## Українська

Майстер **Налаштувати → Підготувати перевірочну копію з експортів** сам збирає
приватний пакет: писати JSON-зіставлення й вручну створювати ZIP більше не потрібно.
Це перевірочна копія, а не експорт робочої системи чи ввімкнення автоматизацій.
Використовуйте окремий екземпляр публічної інтеграції: не замінюйте робочий старий
домен заради появи меню.

Спершу отримайте узгоджені експорти Assistant і Court версії 1 штатною процедурою
джерела та збережіть точку повернення. Два незалежно скопійовані робочі файли цього
не доводять. Налаштуйте учасників нової родини та їхні HA-акаунти. Майстер доступний
початковому власнику родини, який також є адміністратором HA.

Укажіть назву копії та два `.json`-файли (до 8 МіБ кожен). Додаткове поле дозволяє
зазначити старі ID перевіряльників, відсутні в записах, по одному на рядок. Далі явно
виберіть нового учасника для кожного старого ID. Імена не вгадуються, двох старих
людей не можна об'єднати в одну. Лише дозволені історичні ID можна залишити архівними,
без надання ролі. Якщо потрібного учасника немає, скасуйте перевірку й налаштуйте його.

Для кожного завдання зі звітом підтвердьте **всіх попередніх перевіряльників за
налаштуваннями**, включно з призначеним, а не лише останнього, хто прийняв завдання.
Правдивість цього переліку майстер довести не може. Різниця з батьками нової родини
блокує копію: не вилучайте людей заради обходу перевірки.

Для кожного історичного фотозвіту виберіть його оригінал після локальної перевірки.
Показано ID завдання, номер події, час і вихідне посилання/нотатка звіту. Потрібні всі
здачі, не лише останнє фото. Перевірте підсумкові зв'язки, кількості й відбиток, потім
явно підтвердьте окрему копію лише для читання. Вихідна родина не змінюється;
повідомлення, сирени, штрафи й мережеві операції не запускаються.

Спільний із ZIP-майстром ліміт — одна перевірка на 15 хвилин і до 1 000 зв'язків.
До 512 фото, по 10 МіБ і 64 МіБ загалом; JPEG/PNG/WebP перевіряються декодером до
підтвердження. Файли приймає штатне тимчасове завантаження HA, довільних шляхів і URL
немає. Зміна прав, учасників, мови, зони чи робочого модуля скасовує перевірку.
Скасування звільняє лише підготовку: створена копія та план повтору зберігаються.
Після невизначеного результату повторіть ті самі файли, фото, назву й зіставлення
за незмінних учасників — ID і пакет збережуться. Змінені байти означають інший пакет,
а не відновлення попередньої операції. Експорти й паролі не можна надсилати моделі
чи публікувати. Остаточне отримання джерела та робоче перемикання ще потребують
окремої перевірки.
