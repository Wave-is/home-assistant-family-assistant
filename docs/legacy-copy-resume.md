# Resume a saved read-only copy / Продолжить копию / Продовжити копію

## English

**Configure → Resume a saved read-only copy** lists attempts explicitly confirmed
from this household since alpha.31. Listing is owner-private and reads a bounded
native HA Store index; it does not search directories or discover older unindexed
attempts. It performs no startup/background repair and does not export source data.

Select an attempt to verify its saved state, original conversion evidence and
photo blobs again. The original owner must still be an active HA administrator,
the original prototype must exist, and member identities, language and time zone
must match their original review. Changed permissions invalidate a pending screen.

If staging finished but registration was interrupted, a fresh review shows the
same copy name, preparation time, counts and fingerprint. Explicit confirmation
registers the **same sealed copy with the same internal ID**, without reuploading
the ZIP. An already registered matching copy is an exact retry, not a duplicate;
registered-but-unloaded status is not misrepresented as running.

If the Store, evidence or photos are incomplete, changed or accompanied by
unreviewed temporary files, direct resume is refused. Keep the original ZIP and
copy name for the [reviewed upload recovery path](legacy-recovery.md). A checksum
or seal alone is not accepted as proof that conversion was correct.

The index is written only after final copy confirmation, before staging begins.
It retains up to **16 immutable attempts per HA instance**, including completed
ones, with no automatic eviction. Closing a review removes neither index records
nor source files, staged Stores, photos or existing entries. An absent/corrupt/full
index is not reset. Earlier attempts require the original bundle; this is not a
filesystem recovery tool or a general retention/cleanup interface.

All resumed copies remain owner-private and read-only. Telegram, alarms, penalties
and network workers remain off. This does not prove coherent live source capture
or authorize activation/cutover. Original household state and credentials stay
outside the public repository and HACS-managed runtime files.

## Русский

В настройках семьи выберите **Продолжить создание сохранённой копии**. Журнал
показывает только попытки, явно подтверждённые в этой семье начиная с alpha.31.
Каталоги не сканируются; старые попытки без записи в журнале требуют исходного ZIP.

Выбор повторно проверяет хранилище, исходные данные преобразования и фото. Нужны
тот же владелец с активными правами администратора HA, существующая исходная семья
и неизменённые участники, язык и часовой пояс. Если данные сохранены полностью,
отдельное подтверждение регистрирует **ту же защищённую копию с тем же ID**, без
повторной загрузки ZIP. Повтор не создаёт дубликат. Незагруженная запись не считается
работающей. Неполные или изменённые данные требуют проверенного восстановления
через исходный архив; одна контрольная сумма не заменяет проверку преобразования.

Журнал создаётся только после финального согласия, до записи копии. В нём до
**16 неизменяемых попыток на HA**, включая завершённые, без автоматического удаления.
Отмена закрывает лишь экран: журнал, файлы и готовые копии сохраняются. Повреждённый
или заполненный журнал не обнуляется. Это не инструмент очистки хранилища.

Копия остаётся приватной для владельца и только для чтения. Бот, будильники,
штрафы и сетевые команды не запускаются. Согласованность исходного экспорта и
переключение рабочей системы требуют отдельной проверки.

## Українська

У налаштуваннях сім’ї виберіть **Продовжити створення збереженої копії**. Журнал
показує лише спроби, явно підтверджені в цій сім’ї починаючи з alpha.31. Каталоги
не скануються; попередні спроби без запису в журналі потребують вихідного ZIP.

Вибір повторно перевіряє сховище, вихідні дані перетворення та фото. Потрібні
той самий власник з активними правами адміністратора HA, наявна вихідна сім’я
та незмінені учасники, мова й часовий пояс. Якщо дані збережено повністю, окреме
підтвердження реєструє **ту саму захищену копію з тим самим ID**, без повторного
завантаження ZIP. Повтор не створює дублікат. Незавантажений запис не вважається
працюючим. Неповні або змінені дані потребують перевіреного відновлення через
вихідний архів; одна контрольна сума не замінює перевірку перетворення.

Журнал створюється лише після фінальної згоди, до запису копії. У ньому до
**16 незмінних спроб на HA**, включно із завершеними, без автоматичного видалення.
Скасування закриває лише екран: журнал, файли та готові копії зберігаються.
Пошкоджений або заповнений журнал не обнуляється. Це не засіб очищення сховища.

Копія залишається приватною для власника й лише для читання. Бот, будильники,
штрафи та мережеві команди не запускаються. Узгодженість вихідного експорту й
перемикання робочої системи потребують окремої перевірки.
