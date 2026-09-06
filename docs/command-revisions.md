# Record versions and safe retries

## English

Every edit to an existing shopping item, task, score, alarm schedule or family
member requires its `id` and `revision`. Read the version from the authenticated
view **when displaying the form or interpreting the request**, not after an
uncertain response. Revisions are integers from 1 to 9,007,199,254,740,991.
Omission, `null`, booleans, fractions and strings are not wildcard versions.

The dashboard supplies versions automatically. Telegram binds an interpreted
command to its visible record and persists that exact plan before execution.
Model commands bind to the view supplied to the model; a record changed while
the model was answering causes a conflict, not a silent update to the new
version. Member options capture the version displayed in that form.

```json
{
  "type": "family_assistant/execute",
  "entry_id": "synthetic-household",
  "operation_id": "unique-reviewed-operation",
  "action": "shopping.purchase",
  "payload": {"id": "S000001", "revision": 2, "quantity": 1}
}
```

On a lost response, retry the **same operation ID and exact payload**. Do not
replace its revision with the latest value: that would be a different operation.
On `conflict`, review the current record before issuing a new command. Roles,
active membership and module permissions are still checked on receipt replay.
Creation has no prior revision. `alarms.test` creates a separate test run; wake-up
answers use the current nonce instead of an editable schedule revision.

No stored household data or historical receipts are rewritten by this change.
Any old pending interpretation without a valid required revision must be reviewed,
not silently upgraded or executed against the newest record.

## Русский

Для изменения существующей покупки, задачи, балла, расписания будильника или
участника нужны `id` и `revision` — версия, показанная при открытии формы или
разборе команды. Карточки и бот передают её автоматически. Только целое число
от 1 до 9 007 199 254 740 991; отсутствие, `null`, логическое значение, дробь
или строка не разрешают менять любую версию.

Если запись изменилась, пока модель отвечала, команда получает конфликт.
Старая форма участника также не может молча заменить более новые настройки.
При потере ответа повторяются тот же `operation_id` и тот же набор данных.
Нельзя подменить версию свежей и назвать это повтором. При конфликте сначала
проверьте текущую запись, затем подтвердите новую команду. Права и активность
участника продолжают проверяться. Новая запись не требует прежней версии;
подтверждение пробуждения использует свежую проверку с nonce.

Старые данные и квитанции не переписываются. Незавершённая старая команда без
нужной версии требует проверки, а не автоматического выполнения заново.

## Українська

Для зміни наявної покупки, завдання, бала, розкладу будильника або учасника
потрібні `id` та `revision` — версія, показана під час відкриття форми чи
розбору команди. Картки й бот передають її автоматично. Дозволено лише ціле
число від 1 до 9 007 199 254 740 991; відсутність, `null`, логічне значення,
дріб чи рядок не дозволяють змінювати будь-яку версію.

Зміна запису під час відповіді моделі спричиняє конфлікт. Стара форма учасника
також не може непомітно замінити нові налаштування. Якщо відповідь втрачено,
повторюються той самий `operation_id` і точні дані. Не підміняйте версію
поточною під виглядом повтору. Після конфлікту перевірте актуальний запис і
підтвердьте нову команду. Права та активність учасника перевіряються повторно.
Новий запис не має попередньої версії; підтвердження пробудження використовує
свіжу перевірку з nonce.

Історичні дані та квитанції не переписуються. Незавершена стара команда без
потрібної версії потребує перевірки, а не автоматичного повторного виконання.
