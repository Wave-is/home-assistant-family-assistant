# Passive refresh keyboard context

## English

Family Assistant refreshes a visible card in the background. A passive refresh
may replace the card DOM, but it must not make a keyboard workflow depend on
the refresh timer.

The shared helper records only an in-memory scope fingerprint: household entry,
card generation and view, HA user, actor and role, household and actor revisions,
and enabled modules. Immediately before a permitted rerender it records the
latest focused control and uniquely identifiable disclosure states. It invokes
one synchronous render, restores matching `<details>` states, and focuses a
replacement only when the same control key is unique.

IDs or explicit focus keys take priority. Named form controls use their type,
name, and radio/checkbox value. Buttons and disclosure summaries use their
accessible label only when it is unique in the card. Repeated ambiguous controls
are deliberately not restored. Restoring focus never clicks a control, changes a
radio choice, submits a form, or sends a request.

Changing a disclosure's `open` property normally queues a native `toggle`
event. The helper intercepts only the exact events caused by passive state
restoration, so they cannot be mistaken for user intent or start a lazy private
content load. It does not suppress a person's own disclosure interactions.
Pointer, keyboard, or click interaction cancels suppression before the browser
changes the disclosure, and the person's resulting open state wins.

The helper restores nothing after an entry, generation, HA user, actor, role,
revision, or module change. It also does not move focus back when the user moved
outside the card while refresh was pending, or when the new renderer intentionally
focused another control. The existing focused-form refresh suppression remains
the first line of protection for text being entered.

## Русский

Family Assistant обновляет открытую карточку в фоне. Пассивное обновление может
заменить DOM карточки, но работа с клавиатурой не должна зависеть от момента
срабатывания таймера.

Общий помощник хранит только оперативный отпечаток области: запись семьи,
поколение и вид карточки, пользователя HA, участника и роль, ревизии семьи и
участника и список включённых модулей. Непосредственно перед разрешённой
перерисовкой он запоминает текущий элемент фокуса и состояния однозначно
определяемых раскрывающихся секций. После одной синхронной перерисовки он
восстанавливает состояния `<details>` и фокусирует замену только при одном
точном совпадении ключа.

Сначала используются ID и явные ключи фокуса. Для именованных полей учитываются
тип, имя и значение переключателя или флажка. Кнопки и заголовки раскрывающихся
секций распознаются по доступной подписи только тогда, когда она уникальна в
карточке. Неоднозначные повторяющиеся элементы намеренно не восстанавливаются.
Помощник не нажимает кнопки, не меняет выбор, не отправляет формы и не выполняет
запросы.

Изменение свойства `open` у раскрывающейся секции обычно ставит нативное событие
`toggle` в очередь. Помощник перехватывает только точные события пассивного
восстановления, чтобы их нельзя было принять за действие пользователя или
начало отложенной загрузки приватных данных. Обычные действия пользователя с
секцией не подавляются.
Событие указателя, клавиатуры или нажатия заранее отменяет такое подавление, и
сохраняется итоговое состояние секции, выбранное пользователем.

После смены записи, поколения, пользователя HA, участника, роли, ревизии или
модулей ничего не восстанавливается. Фокус также не возвращается, если за время
ожидания пользователь перешёл за пределы карточки или новый интерфейс сам
сфокусировал другой элемент. Действующее правило не перерисовывать форму с
активным полем остаётся основной защитой вводимого текста.

## Українська

Family Assistant оновлює відкриту картку у фоновому режимі. Пасивне оновлення
може замінити DOM картки, але робота з клавіатурою не повинна залежати від
моменту спрацювання таймера.

Спільний помічник зберігає лише оперативний відбиток області: запис родини,
покоління й подання картки, користувача HA, учасника та роль, ревізії родини й
учасника та перелік увімкнених модулів. Безпосередньо перед дозволеним
перемальовуванням він запам’ятовує поточний елемент фокуса й стани однозначно
визначених розкривних секцій. Після одного синхронного перемальовування він
відновлює стани `<details>` і фокусує заміну лише за одного точного збігу ключа.

Спочатку використовуються ID та явні ключі фокуса. Для іменованих полів
враховуються тип, ім’я та значення перемикача або прапорця. Кнопки й заголовки
розкривних секцій розпізнаються за доступною назвою лише тоді, коли вона
унікальна в картці. Неоднозначні повторювані елементи навмисно не
відновлюються. Помічник не натискає кнопки, не змінює вибір, не надсилає форми й
не виконує запити.

Зміна властивості `open` розкривної секції зазвичай ставить нативну подію
`toggle` в чергу. Помічник перехоплює лише точні події пасивного відновлення,
щоб їх не можна було сприйняти як дію користувача чи початок відкладеного
завантаження приватних даних. Звичайні дії користувача із секцією не
пригнічуються.
Подія вказівника, клавіатури або натискання завчасно скасовує таке пригнічення,
і зберігається підсумковий стан секції, обраний користувачем.

Після зміни запису, покоління, користувача HA, учасника, ролі, ревізії або
модулів нічого не відновлюється. Фокус також не повертається, якщо під час
очікування користувач перейшов за межі картки або новий інтерфейс сам сфокусував
інший елемент. Чинне правило не перемальовувати форму з активним полем
залишається основним захистом тексту, який вводиться.
