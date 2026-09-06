# Family privileges / Семейные привилегии / Сімейні привілеї

Development build only. No production deployment or public release yet.
Версия в разработке. Это ещё не публичный релиз и не обновление рабочего дома.
Версія в розробці. Це ще не публічний реліз і не оновлення робочого дому.

## English

The **court** card includes a parent-defined privilege catalog. There are no
hard-coded rewards or automatic device actions: approval is a family agreement,
and fulfillment means a parent recorded that it was provided.

- Parents/owners create and edit name, description, price (1–10,000 integer
  points), availability, eligible members and request lifetime (1–720 hours;
  default 72). An empty eligibility selection means all non-guest members.
- A member requests a privilege for themselves; parents can also request for
  another active non-guest member through the card. The request snapshots the
  name, description and cost. Later catalog edits do not reprice it.
- Available points equal active score earnings minus reserved and spent points,
  with a minimum of zero. Requested/approved privileges reserve points. A parent
  approves and then separately marks fulfillment; fulfillment moves the same
  amount from reserved to spent. Concurrent requests cannot spend it twice.
- A member may cancel their own unapproved request. Parents can reject a pending
  request, cancel a pending/approved promise, or refund a fulfilled privilege.
  Every decision requires a reason. These actions retain the original history.
- An unapproved request expires and releases its reservation at its deadline.
  Approved promises do not expire automatically. Disabling the court still
  releases expired unapproved reservations, without sending new expiry messages.
- Reversing previously earned points does not erase already spent points. A
  negative net balance is shown as debt; new requests require sufficient funds.
  The score ledger and weekly score snapshots do not count purchases as penalties.

Children see their own requests and wallet. Parents see the household overview.
Existing approved promises remain reviewable even if the catalog is disabled or
edited. Closing an uncertain form does not undo a command already accepted by HA;
refresh the history before submitting a different request.

Telegram uses your own configured bot and confirmed member identities:

```text
/rewards
/wallet
/rewardadd Choose the family game | 5 | One evening
/reward R000001 | Saturday, please
/rewarddecide V000001 | approve | Agreed
/rewarddecide V000001 | fulfill | Provided
```

Decision keywords: `approve`, `reject`, `cancel`, `fulfill`, `refund`.
Only the appropriate family role can execute them. Detailed catalog editing is
in the card; no RouterOS, siren or arbitrary HA command is executed by a reward.

## Русский

В карточке **суда** родители создают свой каталог привилегий: название, описание,
стоимость (целое число 1–10 000), доступность, участников и срок заявки
(1–720 часов, по умолчанию 72). Если никого не отметить, привилегия доступна всем,
кроме гостей. В публичном коде нет конкретных семейных наград.

Заявка резервирует баллы. Родитель сначала одобряет её, затем отдельно отмечает,
что привилегия предоставлена. Только эта отметка переносит резерв в потраченные
баллы. Это запись договорённости, а не подтверждение физического действия устройства.

- Доступно = действующие начисления − резерв − потраченные баллы, не ниже нуля.
  Одновременные заявки не могут повторно потратить одни баллы.
- Ребёнок может отменить свою ещё не одобренную заявку. Родитель может отклонить
  заявку, отменить одобренную договорённость или вернуть баллы за предоставленную
  привилегию. Причина обязательна; история сохраняется.
- Неодобренная заявка освобождает резерв по истечении срока. Одобренная не
  отменяется автоматически. При выключенном модуле просроченный резерв также
  освобождается, но новые сообщения об истечении не отправляются.
- Цена и описание сохраняются в заявке: изменение каталога не меняет старую
  договорённость. Отмена ранее заработанных баллов не стирает уже потраченные;
  отрицательный остаток виден как долг. Покупка не превращается в штраф суда.

Дети видят только свои заявки и кошелёк, родители — общую картину. Родитель также
может оформить заявку для другого участника через карточку. Автоматического
управления интернетом или устройствами из магазина пока нет.

Команды собственного бота: `/rewards`, `/wallet`,
`/rewardadd Выбрать семейную игру | 5`, `/reward R000001 | На субботу`,
`/rewarddecide V000001 | approve | Согласовано`. Решения: `approve` — одобрить,
`reject` — отклонить, `cancel` — отменить, `fulfill` — отметить предоставление,
`refund` — вернуть баллы. Права проверяются интеграцией.

При ошибке сохранения повтор использует тот же запрос. Закрытие формы не
отменяет уже принятый HA запрос: перед новой заявкой проверьте историю.

## Українська

У картці **суду** батьки створюють власний каталог привілеїв: назва, опис,
ціна (ціле число 1–10 000), доступність, учасники та термін заявки
(1–720 годин, типово 72). Якщо нікого не позначити, доступ мають усі, крім гостей.
Конкретні сімейні винагороди не зашиті в публічний код.

Заявка резервує бали. Батьки спочатку схвалюють її, а потім окремо відзначають
надання привілею. Тільки ця позначка переносить резерв у витрачені бали.
Це запис домовленості, а не підтвердження фізичної дії пристрою.

- Доступно = чинні нарахування − резерв − витрачені бали, не нижче нуля.
  Одночасні заявки не можуть двічі витратити ті самі бали.
- Дитина може скасувати власну ще не схвалену заявку. Батьки можуть відхилити
  заявку, скасувати схвалену домовленість або повернути бали за наданий привілей.
  Причина обов'язкова; історія зберігається.
- Несхвалена заявка звільняє резерв після завершення терміну. Схвалена не
  скасовується автоматично. Вимкнений модуль також звільняє прострочений резерв,
  але не надсилає нових повідомлень про завершення терміну.
- Заявка зберігає початкові ціну й опис. Зміна каталогу не змінює старої
  домовленості. Скасування зароблених балів не стирає вже витрачені;
  від'ємний залишок відображається як борг. Купівля не є штрафом суду.

Діти бачать лише власні заявки та гаманець, батьки — загальну картину. Через
картку батьки можуть подати заявку за іншого учасника. Автоматичного керування
інтернетом або пристроями з магазину поки немає.

Команди власного бота: `/rewards`, `/wallet`,
`/rewardadd Обрати сімейну гру | 5`, `/reward R000001 | На суботу`,
`/rewarddecide V000001 | approve | Узгоджено`. Рішення: `approve` — схвалити,
`reject` — відхилити, `cancel` — скасувати, `fulfill` — відзначити надання,
`refund` — повернути бали. Інтеграція перевіряє права.

При помилці збереження повтор використовує той самий запит. Закриття форми не
скасовує вже прийнятий HA запит: перед новою заявкою перевірте історію.
