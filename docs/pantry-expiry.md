# Pantry expiry reminders / Напоминания о сроках / Нагадування про строки

## English

The household owner can enable **Remind parents about recorded pantry expiry
dates** in the integration's **Configure → Household preferences**. Enable the
Pantry module too. Reminders are off by default; the lead window defaults to
3 days and accepts whole numbers from 0 to 30. Zero means the recorded date only.
The pantry card shows this policy to parents; it does not change the policy.

At or after 09:00 in the household time zone, the integration creates one reminder
for an active stock record with positive quantity and a recorded date from today
through the lead window. Dates and quantities are manual records. Expired dates
are not backfilled after downtime. Separate lots need separate stock records.

Delivery is private to currently active, linked parents/owners. It never falls
back to the family group or to an adult without a parent role, child or guest.
Connect your own Telegram bot and the parents' private chats first. Without a
channel, an eligible reminder waits only until its recorded expiry day ends.
Quiet hours may defer actual delivery; 09:00 is a creation threshold, not a
delivery guarantee. An ambiguous Telegram timeout is held for review, not blindly
resent. Already handed-off requests cannot be recalled.

Deduplication is **once per stock-record revision**, persisted across restart.
An edit creates a new revision and may produce a new reminder. An archived,
zeroed or edited source, removed date, disabled module/policy, shortened lead
window or elapsed expiry day invalidates an obsolete unsent message. Re-enabling
the policy or later entering the window does not recreate a reminder already
marked for that same revision, including a superseded one. Review the record
manually after changing policy; this is not a recurring daily alarm.

Only the item identifier/version, name and recorded date enter the reminder.
Parent notes, location and history are not copied. Nothing is bought or deducted
from stock. This is a prompt to check the item yourself, **not a determination
that food is safe, fresh or suitable for an allergy**.

## Русский

Владелец семьи включает **«Напоминать родителям о записанных сроках годности»**
в **настройках интеграции → параметры семьи**. Также должен быть включён модуль
запасов. По умолчанию напоминания отключены, срок — 3 дня. Допустимы целые числа
от 0 до 30; 0 означает только указанную дату. Карточка запасов показывает
родителям это правило, но не изменяет его.

После 09:00 по часовому поясу семьи создаётся напоминание об активной позиции
с положительным остатком, если её записанная дата — сегодня или в пределах
выбранного срока. Остатки и даты внесены вручную; разные партии учитывайте
отдельно. После простоя старые просроченные даты не рассылаются.

Сообщения идут только в личные чаты активных привязанных родителей/владельцев.
Сначала подключите своего Telegram-бота и личные чаты. В семейную группу,
детям, гостям и взрослым без роли родителя такие сообщения не отправляются.
Без канала сообщение ждёт до конца указанной даты. Тихие часы могут задержать
доставку: 09:00 — порог создания, а не обещанное время получения. Неопределённый
результат отправки требует проверки и не запускает слепой повтор. Уже переданный
на отправку запрос отозвать нельзя.

Напоминание создаётся **один раз на версию записи**, включая после перезапуска.
Правка записи создаёт новую версию и может вызвать новое напоминание. Архив,
нулевой остаток, правка или удаление даты, отключение правила/модуля, сокращение
срока предупреждения или окончание указанной даты отменяют неотправленное
неактуальное сообщение. Повторное включение или наступление нового срока не
создаёт заново уже отмеченное напоминание той же версии, даже если оно было
отменено. После изменения правила проверьте записи вручную; это не ежедневный
будильник.

В сообщение попадают только идентификатор/версия, название и записанная дата.
Заметки родителей, место и история не копируются. Покупки не оформляются,
остатки не списываются. Это просьба проверить продукт, **а не заключение о его
безопасности, свежести или пригодности при аллергии**.

## Українська

Власник сім'ї вмикає **«Нагадувати батькам про записані строки придатності»**
у **налаштуваннях інтеграції → параметри сім'ї**. Модуль запасів також має бути
ввімкнений. Типово нагадування вимкнено, строк — 3 дні. Дозволено цілі числа
від 0 до 30; 0 означає лише зазначену дату. Картка запасів показує батькам
це правило, але не змінює його.

Після 09:00 за часовим поясом сім'ї створюється нагадування про активну позицію
з додатним залишком, якщо її записана дата — сьогодні або в межах вибраного
строку. Залишки й дати введено вручну; різні партії обліковуйте окремо. Після
простою старі прострочені дати не розсилаються.

Повідомлення надходять лише у приватні чати активних прив'язаних батьків/власників.
Спочатку підключіть власного Telegram-бота й приватні чати. Повідомлення не
перенаправляються до сімейної групи, дітей, гостей чи дорослих без батьківської
ролі. Без каналу вони чекають до кінця зазначеної дати. Тихі години можуть
відкласти доставку: 09:00 — поріг створення, а не гарантований час отримання.
Невизначений результат надсилання потребує перевірки, а не сліпого повтору.
Уже переданий на надсилання запит неможливо відкликати.

Нагадування створюється **один раз на версію запису**, також після перезапуску.
Зміна запису створює нову версію й може спричинити нове нагадування. Архівування,
нульовий залишок, зміна чи видалення дати, вимкнення правила/модуля, скорочення
строку попередження або завершення зазначеної дати скасовують неактуальне
ненадіслане повідомлення. Повторне ввімкнення чи настання нового строку не
створює знову вже позначене нагадування тієї самої версії, навіть скасоване.
Після зміни правила перевірте записи вручну; це не щоденний будильник.

До повідомлення потрапляють лише ідентифікатор/версія, назва й записана дата.
Примітки батьків, місце та історія не копіюються. Покупки не оформлюються,
залишки не списуються. Це прохання перевірити продукт, **а не висновок про його
безпечність, свіжість чи придатність за наявності алергії**.

## API

Owner-only `settings.save` accepts optional `pantry_expiry_reminders` (boolean)
and `pantry_expiry_days` (integer 0–30). Existing required name/language/modules
fields are unchanged; omitted expiry settings remain unchanged. Missing persisted
values read as disabled and 3 days. No migration rewrites household records.
Reminder intents and minimal per-item dedup markers use the ordinary local Store.
