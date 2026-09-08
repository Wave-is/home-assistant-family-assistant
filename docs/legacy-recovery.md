# Interrupted read-only copy: preserve and retry

Bounded recovery in the [legacy copy wizard](legacy-copy-wizard.md), not activation,
automatic cleanup or a source-export tool.

## English

If registration fails and the same unregistered copy contains recognizable
temporary photo uploads, a separate preservation screen shows the count, total
size and fingerprint. An unfinished attempt can show its original reviewed
totals. Reading this screen changes no files.

1. After a restart, upload the **same private ZIP, with the same copy name and
   unchanged destination members**. Repeat the association review. Do not rename
   or rebuild an archive to recover an uncertain result.
2. Review and explicitly confirm **preserve and retry this read-only copy**.
   The earlier copy confirmation is not cleanup consent.
3. Only pinned temporary names whose bytes exactly match an expected photo prefix
   are eligible. Existing completed blobs must remain exact. Foreign files,
   changed identities, external hardlinks and registered copies block recovery.
   An interrupted photo-publication hardlink is supported only when every link
   is accounted for inside the reviewed directory.
4. A private recovery journal is saved through Home Assistant Store. **All**
   selected temporary bytes are archived and verified before any temporary source
   name is removed. Completed photos and family Stores are not removed or reset.
   Retry rechecks the same journal, archive and candidate.
5. Registration retries the **same sealed read-only copy**. No alarms, Telegram,
   network changes or other workers start.

Recovery limits: 64 distinct candidate blobs / 96 MiB, 16 temporary names / 32 MiB,
10 MiB per file and 16 retained preservation attempts per candidate. These are
recovery limits; larger valid import packages are not guaranteed this recovery
path. Foreign or excessive residue requires separate manual review.

The private archive remains in local HA `family_assistant_recovery`, separate from
`family_assistant_data`. It can contain original image fragments: it is **not
anonymous**, public or automatically deleted. Protect it with the same local
access and backup policy as the source export. Cancel discards only the in-memory
review, not files, copies or journals.

For complete attempts indexed since alpha.31, the separate [saved-copy resume
screen](legacy-copy-resume.md) can avoid reuploading the bundle. Partial or older
unindexed attempts still need the original ZIP. There is no automatic startup
repair. Recovery does not prove coherent capture or authorize household cutover.

## Русский

После прерванного импорта мастер может предложить **сохранить остатки и повторить
создание проверочной копии**. Он показывает число временных файлов, размер и
отпечаток; незавершённая операция может показывать исходные проверенные количества.
Просмотр ничего не меняет. После перезапуска загрузите **тот же ZIP, с тем же
названием копии и неизменёнными участниками**, проверьте соответствия и отдельно
подтвердите сохранение. Согласие на создание копии не заменяет это подтверждение.

Сначала все выбранные временные файлы копируются и проверяются в приватном архиве.
Лишь затем удаляются их временные имена и повторяется регистрация той же защищённой
копии. Готовые фото и хранилище семьи не удаляются и не обнуляются. Чужие файлы,
изменённые данные, внешние жёсткие ссылки и уже зарегистрированная копия блокируют
операцию. Поддерживается проверенная временная жёсткая ссылка от публикации фото.

Пределы: 64 уникальных файла-кандидата / 96 МиБ, 16 временных файлов / 32 МиБ,
по 10 МиБ на файл и 16 сохранённых попыток. Большие или неизвестные остатки требуют
отдельного разбора. Приватные фрагменты фото остаются в локальном каталоге HA
`family_assistant_recovery`; они не анонимизируются и не удаляются автоматически.
Отмена закрывает только проверку, сохраняя файлы и журнал. Будильники, бот и сетевые
команды в копии не запускаются.

Полностью сохранённые попытки из журнала alpha.31 можно продолжить через отдельный
[экран сохранённых копий](legacy-copy-resume.md), без повторной загрузки ZIP.
Неполным и старым попыткам вне журнала по-прежнему нужен исходный архив. Ремонта
при старте нет; это не доказывает согласованность экспорта и не разрешает
переключение работающей домашней системы.

## Українська

Після перерваного імпорту майстер може запропонувати **зберегти залишки та повторити
створення перевірочної копії**. Він показує кількість тимчасових файлів, розмір і
відбиток; незавершена операція може показувати початкові перевірені підсумки.
Перегляд нічого не змінює. Після перезапуску завантажте **той самий ZIP, з тією самою
назвою копії та незміненими учасниками**, перевірте відповідності й окремо підтвердьте
збереження. Згода на створення копії не замінює цього підтвердження.

Спочатку всі вибрані тимчасові файли копіюються та перевіряються у приватному архіві.
Лише потім видаляються їхні тимчасові імена й повторюється реєстрація тієї самої
захищеної копії. Готові фото та сховище сім’ї не видаляються й не обнуляються.
Сторонні файли, змінені дані, зовнішні жорсткі посилання та вже зареєстрована копія
блокують операцію. Підтримується перевірене тимчасове жорстке посилання від публікації фото.

Межі: 64 унікальні файли-кандидати / 96 МіБ, 16 тимчасових файлів / 32 МіБ,
по 10 МіБ на файл і 16 збережених спроб. Більші або невідомі залишки потребують
окремого розгляду. Приватні фрагменти фото залишаються в локальному каталозі HA
`family_assistant_recovery`; вони не анонімізуються й не видаляються автоматично.
Скасування закриває лише перевірку, зберігаючи файли та журнал. Будильники, бот і
мережеві команди у копії не запускаються.

Повністю збережені спроби з журналу alpha.31 можна продовжити через окремий
[екран збережених копій](legacy-copy-resume.md), без повторного завантаження ZIP.
Неповним і старим спробам поза журналом і далі потрібен вихідний архів. Відновлення
під час запуску немає; це не доводить узгодженість експорту й не дозволяє
перемикання робочої домашньої системи.
