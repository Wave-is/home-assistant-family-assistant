# Historical photo evidence / Старые фотоотчёты / Старі фотозвіти

## English

Engineering-stage migration support, not a live import or Telegram downloader.
Old photo submissions contain an opaque `details.report` string. A caption,
message reference or file identifier is not proof that a local image exists.
Without a complete explicitly matched image set, the whole shadow construction
still refuses the migration rather than silently omitting tasks or photographs.

The internal preparer requires current member mappings, the exact source-review
fingerprint and an owner's explicit match for every historical submission event.
Each choice binds a task ID, event sequence and original reference digest to
selected bytes. The existing bounded POSIX image helper validates each JPEG,
PNG or WebP; supplied metadata alone cannot authorize an attachment. Limits are
512 images, 10 MiB per image and 250 MiB combined. No URLs, paths or credentials
are accepted. This verifies bytes and the recorded match, **not** whether the
photograph actually depicts the historical work.

Current and earlier report rounds retain separate image references, notes and
assignee revisions. Reassignment does not transfer an old child's evidence to a
new child. Migration archive replay redecodes all bytes and checks the exact
source/mapping/metadata again. Missing, extra or substituted files reject replay.
The raw source remains unchanged and private.

The resulting `ShadowCandidate` returns private Store data and a separate private
blob set. A future installer must preserve both atomically; it must never write
only the JSON and claim the photographs were migrated. There is no public
installer, matching screen or activation endpoint yet. In an isolated loaded
shadow, only its current owner may read verified attachments; children, other
parents and unbound HA administrators have no shadow access. Commands, uploads,
providers and automatic cleanup remain disabled. Do not edit `.storage` or
remove the isolation marker manually.

## Русский

Это часть механизма миграции, а не готовый импорт или загрузчик Telegram.
В старой истории фотоотчёт хранится строкой: подписью либо ссылкой на сообщение.
Такая строка не заменяет файл. Пока каждой исторической сдаче не сопоставлена
фотография, перенос всей копии останавливается без пропуска задач или отчётов.

Владелец должен явно сопоставить файл с конкретной задачей, событием сдачи и
исходной ссылкой. Проверяются неизменность списка участников и снимка, формат
и содержимое изображения отдельным ограниченным процессом. Допускаются JPEG,
PNG и WebP: до 512 файлов, до 10 МиБ каждый, до 250 МиБ вместе. Адреса сайтов,
пути и пароли не принимаются. Проверка файла не доказывает, что на фото именно
нужная работа: это подтверждает человек при сопоставлении.

Повторные отчёты, комментарии и прежний исполнитель сохраняются отдельно.
Новый исполнитель не получает доступ к фотографии предыдущего. Восстановление
из архива заново проверяет все файлы; подмена или отсутствие файла отклоняются.

Копия содержит данные и отдельный набор приватных файлов. Будущий установщик
обязан сохранять их вместе. Публичного мастера сопоставления, импорта и включения
пока нет. В загруженной проверочной копии фотографии доступны только её владельцу;
запись, отправка сообщений и фоновые действия запрещены. Рабочая домашняя система
не менялась. Не редактируйте `.storage` и не снимайте защиту вручную.

## Українська

Це частина механізму міграції, а не готовий імпорт чи завантажувач Telegram.
Старий фотозвіт зберігається рядком: підписом або посиланням на повідомлення.
Рядок не замінює файл. Поки кожне історичне подання не зіставлено із зображенням,
побудова всієї копії зупиняється без пропуску завдань або звітів.

Власник має явно зіставити файл із завданням, подією подання та початковим
посиланням. Перевіряються незмінність учасників і знімка, формат та вміст файлу
окремим обмеженим процесом. Підтримуються JPEG, PNG і WebP: до 512 файлів,
до 10 МіБ кожен та до 250 МіБ разом. URL, шляхи та паролі не приймаються.
Перевірка байтів не доводить, що фото показує потрібну роботу: це підтверджує
людина під час зіставлення.

Повторні звіти, коментарі й попередній виконавець зберігаються окремо. Новий
виконавець не отримує чужих фотографій. Відновлення архіву повторно перевіряє
кожен файл; підміна чи відсутність зображення відхиляються.

Копія повертає дані та окремий набір приватних файлів. Майбутній установник має
зберігати їх разом. Публічного майстра зіставлення, імпорту та активації поки
немає. У завантаженій перевірочній копії файли доступні лише її власнику; запис,
повідомлення та фонові дії заборонені. Робочу домашню систему не змінено.
Не редагуйте `.storage` та не прибирайте захист вручну.
