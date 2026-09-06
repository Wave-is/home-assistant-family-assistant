# Dietary preferences / Пищевые предпочтения / Харчові вподобання

## English

Enable **Pantry** in the integration settings, then open **Dietary preferences**
in the Meals dashboard card. No external provider is needed. Each profile has
manual likes, dislikes, things to avoid and an optional allergy note. Enter one
label per line, review the named person's complete profile and confirm saving.

Adults manage their own profiles. They are private by default. **Share with other
parents** is a separate reviewed action, allowing active owners/parents to read,
not edit, that adult's profile. **Revoke sharing** removes it from subsequent
authorized views. Any change to the subject's member record invalidates existing
sharing consent, including a name or role change; the adult must explicitly share
again. Editing a profile otherwise preserves currently valid consent.

Parents can manage children's profiles created under parental management; a child
can read their own notes but not edit them. Changing a child into an adult removes
parental access until that person explicitly shares. Changing an adult into a child
does not expose their previously self-managed notes to parents. The adult can take
over a previously parent-managed profile by reviewing and saving or setting access.

These are **manual notes, not a food-safety assessment**. No ingredient matching,
allergen detection, medical advice or safe/unsafe verdict is performed. Preparing
a meal still requires the person's own checks. Publishing menus or transferring
ingredients to shopping neither consults nor copies these profiles.

The integration does not automatically send profile contents to AI, search,
Telegram, HA entity attributes, diagnostics or shopping records. Command receipts
contain only a member identifier, revision and status. This is application-level
privacy, not encryption against your HA administrator: the local HA storage and
backups may contain the notes. Do not put credentials in a profile.

**Clear profile** requires a separate review. It removes current content but keeps
an empty revisioned record to reject stale edits. It does not erase backups,
screenshots or information already read by an authorized person. After a failed
network response, retry the same reviewed action; do not create a new operation
to repeat an uncertain save. New edits require the currently displayed revision.

## Русский

Включите **Продукты и запасы** в настройках интеграции и откройте раздел
**Пищевые предпочтения** в карточке меню. Внешние сервисы не нужны. Можно вручную
записать любимые и нелюбимые продукты, чего человек избегает, и заметку об аллергии.
Одна запись — одна строка. Перед сохранением проверьте имя и весь профиль.

Взрослый сам управляет своим профилем; по умолчанию другие его не видят.
**Поделиться с другими родителями** — отдельное подтверждаемое действие. Активные
владельцы и родители получают только чтение. **Отозвать доступ** убирает профиль
из последующих доступных им представлений. Любое изменение карточки участника,
даже имени, отменяет прежнее согласие: взрослый должен предоставить доступ снова.
Обычное редактирование самого профиля сохраняет действующее согласие.

Родители ведут детские профили, созданные под родительским управлением; ребёнок
видит свой профиль без права редактирования. Смена роли ребёнка на взрослого
закрывает родителям доступ. Обратная смена роли не раскрывает личные заметки
взрослого. Новый взрослый может принять управление прежним детским профилем,
проверив и сохранив его либо явно изменив доступ.

Это **ручные заметки, а не оценка безопасности еды**. Система не ищет аллергены,
не сравнивает заметки с ингредиентами и не даёт медицинских рекомендаций. Проверять
состав нужно самостоятельно. Публикация меню и перенос в покупки не используют
и не копируют эти данные.

Содержимое автоматически не передаётся в ИИ, поиск, Telegram, атрибуты сущностей
HA, диагностику или покупки. В квитанции команды остаются только идентификатор,
версия и статус. Администратор HA и резервные копии могут иметь доступ к локальному
хранилищу — это разграничение прав приложения, не шифрование от администратора.

**Очистить профиль** требует отдельного подтверждения. Текущее содержимое удаляется,
но пустая запись с версией остаётся для защиты от устаревших команд. Резервные копии,
скриншоты и уже прочитанные сведения не стираются. После потери сетевого ответа
повторите то же проверенное действие, а не создавайте новую команду вслепую.

## Українська

Увімкніть **Продукти та запаси** в налаштуваннях інтеграції й відкрийте розділ
**Харчові вподобання** в картці меню. Зовнішні сервіси не потрібні. Можна вручну
записати, що подобається, не подобається, чого людина уникає, та нотатку про алергію.
Один запис — один рядок. Перед збереженням перевірте ім'я та весь профіль.

Дорослий керує власним профілем; початково інші його не бачать. **Поділитися з
іншими батьками** — окрема дія з підтвердженням: активні власники й батьки отримують
лише читання. **Відкликати доступ** прибирає профіль із наступних дозволених їм
переглядів. Будь-яка зміна картки учасника, навіть імені, скасовує попередню згоду;
дорослий має надати доступ знову. Звичайне редагування профілю зберігає чинну згоду.

Батьки ведуть дитячі профілі, створені під батьківським керуванням. Дитина може
читати власні нотатки, але не змінювати їх. Перехід до дорослої ролі закриває доступ
батькам; зворотна зміна ролі не розкриває приватні нотатки дорослого. Новий дорослий
може перебрати керування колишнім дитячим профілем, перевіривши й зберігши його
або явно змінивши доступ.

Це **ручні нотатки, а не оцінка безпечності їжі**. Система не виявляє алергени,
не зіставляє нотатки з інгредієнтами й не дає медичних порад. Склад потрібно
перевіряти самостійно. Публікація меню та перенесення до покупок не використовують
і не копіюють ці дані.

Вміст автоматично не надсилається до ШІ, пошуку, Telegram, атрибутів сутностей HA,
діагностики чи покупок. Квитанції команд містять лише ідентифікатор, версію та
статус. Адміністратор HA і резервні копії можуть мати доступ до локального сховища:
це права застосунку, а не шифрування від адміністратора.

**Очистити профіль** потребує окремого підтвердження. Поточний вміст видаляється,
але порожній запис із версією залишається для захисту від застарілих команд.
Резервні копії, знімки екрана й уже прочитані відомості не стираються. Після втрати
мережевої відповіді повторіть ту саму перевірену дію, не створюючи нову навмання.

## Command contracts

- `pantry.dietary_save`: `member_id`, `likes`, `dislikes`, `avoid`, `allergy_note`;
  omit `revision` only when no record exists, otherwise supply its strict revision.
- `pantry.dietary_access_set`: `member_id`, `revision`, `member_revision`,
  `share_with_parents` (boolean). Both profile and member versions are frozen by
  review; a member change before execution requires a fresh review, not rebasing.
- `pantry.dietary_clear`: `member_id`, `revision`.

Lists allow at most 30 nonempty trimmed labels of up to 80 characters each;
case-insensitive duplicates within or across lists are rejected. Notes allow up
to 1000 characters and can be empty. Roles, management, status and consent binding
are server-derived, never accepted from a client. No Telegram or LLM mutation
command is provided for these profiles.
