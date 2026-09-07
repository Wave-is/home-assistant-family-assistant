# Recurring task identity epochs

## English

Generic recurring task definitions pin the identity revision of their original
creator and every assignee. Creating or reviewing a series requires the current
parent's revision, the current privileged creator's revision, and an exact
revision for every selected active non-guest member. The creator remains
immutable; another parent cannot silently claim an old series.

This repository has no separate membership epoch. It therefore uses the member
record revision, as the other consent and source contracts do. This is
deliberately conservative: changing a member's name, language, aliases, role,
active state, or HA account suspends generation until a parent opens the current
definition and explicitly saves a new review. A rotating series also stops as a
whole when any reviewed assignee revision changes; it never silently skips to a
different person.

There is no destructive migration. A stored generic series without lineage is
kept but cannot generate work or be enabled. It can be disabled immediately. A
full save with current revisions establishes lineage and moves its effective
time forward, so missed work is not created as backlog. If the original creator
is no longer an active parent or owner, saving cannot repair the series; a future
explicit transfer action would be required.

Maintenance service series keep their existing asset, approver, and assignee
lineage under the maintenance contract. They are not converted to the generic
format. Generated tasks remain ordinary independently reviewed tasks, and an
identity change never retargets a future occurrence automatically.

## Русский

Обычная серия регулярных задач фиксирует ревизию личности первоначального
создателя и каждого исполнителя. Для создания или повторного подтверждения
нужны текущая ревизия действующего родителя, ревизия действующего создателя с
ролью родителя или владельца и точные ревизии всех выбранных активных
участников, кроме гостей. Создатель неизменяем: другой родитель не может
незаметно присвоить старую серию.

Отдельного номера эпохи участия пока нет, поэтому используется ревизия записи
участника, как и в других договорах согласия и источников. Это намеренно строгая
модель: изменение имени, языка, псевдонимов, роли, активности или учётной записи
HA приостанавливает создание задач до явного просмотра и сохранения серии
родителем. Серия с очередностью останавливается целиком при изменении ревизии
любого подтверждённого исполнителя и не перескакивает на другого человека.

Разрушающей миграции нет. Старая серия без lineage сохраняется, но не создаёт
задачи и не включается. Её можно сразу выключить. Полное сохранение с текущими
ревизиями устанавливает lineage и переносит effective time вперёд, поэтому
пропущенные задачи не появляются задним числом. Если первоначальный создатель
больше не активный родитель или владелец, сохранение не исправит серию: для
этого в будущем потребуется отдельная явная передача.

Серии технического обслуживания сохраняют собственную проверку оборудования,
утвердившего родителя и исполнителей из maintenance contract и не переводятся
в общий формат. Созданные экземпляры остаются обычными независимо проверяемыми
задачами; смена личности не переназначает будущую задачу автоматически.

## Українська

Звичайна серія регулярних завдань фіксує ревізію особи початкового автора та
кожного виконавця. Для створення або повторного підтвердження потрібні поточна
ревізія активних батьків, ревізія активного автора з роллю батьків або власника
й точні ревізії всіх вибраних активних учасників, крім гостей. Автор незмінний:
інші батьки не можуть непомітно привласнити стару серію.

Окремого номера епохи участі поки немає, тому використовується ревізія запису
учасника, як і в інших контрактах згоди та джерел. Це навмисно консервативно:
зміна імені, мови, псевдонімів, ролі, активності або облікового запису HA
призупиняє створення завдань до явного перегляду й збереження серії батьками.
Серія з чергуванням зупиняється повністю після зміни ревізії будь-якого
підтвердженого виконавця й не перескакує на іншу людину.

Руйнівної міграції немає. Стара серія без lineage зберігається, але не створює
роботу й не вмикається. Її можна одразу вимкнути. Повне збереження з поточними
ревізіями встановлює lineage і переносить effective time уперед, тому пропущена
робота не створюється заднім числом. Якщо початковий автор уже не активні батьки
або власник, збереження не виправить серію: надалі для цього знадобиться окрема
явна передача.

Серії технічного обслуговування зберігають власну перевірку обладнання,
батьків-погоджувачів і виконавців із maintenance contract та не переводяться до
загального формату. Створені екземпляри залишаються звичайними незалежно
перевірюваними завданнями; зміна особи не перепризначає майбутнє завдання
автоматично.
