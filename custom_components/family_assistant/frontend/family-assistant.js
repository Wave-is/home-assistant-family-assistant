/* Family Assistant cards. User data is inserted only through textContent. */
import {ERRORS} from "./errors.js";
import {renderKids} from "./network-kids.js";
import {renderShoppingSeries} from "./shopping-series.js";
import {renderShoppingItem,renderShoppingArchive,renderShoppingEditor,reconcileShoppingEditorRefresh,disposeShoppingEditor} from "./shopping-items.js";
import {renderTaskItem,renderTaskArchive} from "./task-items.js";
import {renderTaskForm} from "./task-form.js";
import {reconcileTaskMediaRefresh,disposeTaskMedia} from "./task-media-view.js";
import {reconcileFaultPhotos,disposeFaultPhotos} from "./fault-photo-view.js";
import {renderCourt} from "./court-view.js";
import {renderRewards} from "./rewards-view.js";
import {renderCalendar} from "./calendar-view.js";
import {renderRoutines, ROUTINES_COPY, reconcileRoutineRefresh} from "./routines-view.js";
import {renderPantry} from "./pantry-view.js";
import {renderMeals} from "./meals-view.js";
import {renderDietaryProfiles,reconcileDietaryRefresh} from "./dietary-view.js";
import {renderRecipes,reconcileRecipesRefresh} from "./recipes-view.js";
import {renderSchool,reconcileSchoolRefresh} from "./school-view.js";
import {renderSchoolWork,reconcileSchoolWorkRefresh} from "./school-work-view.js";
import {renderSchoolReminders,reconcileSchoolRemindersRefresh} from "./school-reminders-view.js";
import {renderMaintenance,reconcileMaintenanceRefresh} from "./maintenance-view.js";
import {renderPolls,reconcilePollsRefresh} from "./polls-view.js";
import {renderPresence,reconcilePresenceRefresh} from "./presence-view.js";
import {renderDigests,reconcileDigestsRefresh} from "./digests-view.js";
import {renderMealShopping} from "./meal-shopping-view.js";
import {renderAvailabilityShell} from "./availability-shell.js";
import {renderToday} from "./today-view.js";
import {renderHealth,reconcileHealthRefresh} from "./health-view.js";
import {captureFocusRefresh,renderWithFocusRefresh} from "./focus-refresh.js";
import {ALARM_EDITOR_COPY,openAlarmEditor,renderAlarmEditor,reconcileAlarmEditorRefresh} from "./alarm-editor.js";
import {renderTaskSeries,reconcileTaskSeriesRefresh} from "./task-series-view.js";
import {renderArticle,reconcileArticleRefresh,disposeArticle} from "./article-view.js";
import {renderConversation,reconcileConversationRefresh,disposeConversation} from "./conversation-view.js";
const COPY = {
  en: {
    networkWriteHint:"Only selected, reviewed plans can change the router. Inventory reading makes no changes.",
    networkLeaseOnly:"DHCP inventory. Reading makes no changes; Kid Control is configured separately.",networkLeaseWriteOff:"DHCP lease writes are disabled. This does not disable separately authorized Kid Control commands.",
    networkPrepare:"Preview selected leases",networkSelect:"Select lease",networkComment:"Proposed comment",networkReplace:"Replace existing comment",networkApply:"Apply reviewed plan",networkCancel:"Cancel plan",networkReview:"Review lease changes",networkConsent:"I understand: rollback of a conversion removes only its new reservation. Dynamic DHCP recovery requires renewal and is not an exact restoration.",networkWriteOff:"Writes are disabled. Enable reviewed changes and protect management devices in connection settings, then create a fresh plan.",networkToStatic:"Dynamic → static",networkNoChanges:"No change",networkExpired:"Preview expired — create a fresh one.",networkState_preview:"Preview only",networkState_queued:"Queued; not yet applied",networkState_applying:"Applying with read-back",networkState_rolling_back:"Compensating selected changes",networkState_applied:"Applied and verified",networkState_rolled_back:"Compensated — check DHCP recovery",networkState_review_required:"Needs your review",networkState_failed:"Not applied",networkState_cancelled:"Cancelled",networkSelectDynamic:"Select eligible dynamic leases",
    networkPhase_ready:"Not started",networkPhase_converting:"Converting reservation",networkPhase_converted:"Reservation converted",networkPhase_commenting:"Updating comment",networkPhase_verified:"Verified on router",networkPhase_unchanged:"Unchanged",networkPhase_removing:"Removing newly created reservation",networkPhase_restoring_comment:"Restoring previous comment",networkPhase_restored:"Original settings restored",networkPhase_dhcp_recovery:"Reservation removed; DHCP renewal may be needed",
    mikrotik:"Home network",networkRefresh:"Read router again",networkReadOnly:"Inventory only. Reading never changes leases or internet access.",networkParents:"Network inventory is available to parents only.",networkObserved:"Last successful observation",networkNoData:"Configure MikroTik in integration options and enable its module.",networkSources:"Sources",networkSuggestions:"Home Assistant matches",networkProtected:"Protected router or administration device",networkUnknown:"No HA match",networkPrivateMac:"Locally administered MAC: check that this Wi-Fi network uses a fixed address.",networkAmbiguous:"Several equal matches — choose manually.",networkFasttrack:"FastTrack is enabled: rate limits and filtering need topology checks.",networkIPv6:"IPv6 is enabled or its state is unknown; IPv4-only restrictions are not enough.",networkUnavailable:"Unavailable tables",exact_mac:"Exact MAC",current_tracker_ip:"Current tracker IP",hostname_only:"Hostname only",networkMultiple:"Multiple current IP addresses",
    conversation:"Family conversation",message:"Message",send:"Send",thinking:"Working on your request… Other cards remain available.",learnPhrase:"Teach a phrase",sourcePhrase:"Unrecognized phrase",canonicalPhrase:"Supported reusable command",learningHint:"Exact phrases are remembered for your account only. They never grant permissions or override built-in commands.",forgetPhrase:"Disable phrase",
    modelProposals:"Check my interpretation",confirmPlan:"Apply this plan",rejectPlan:"Cancel plan",proposalHint:"Nothing has changed yet. This plan expires at",
    advanced:"Advanced settings",
    addSeries:"Add recurring duty",
    recurring:"Recurring",
    rotation:"Take turns",
    eachPerson:"A task for each person",
    frequency:"Repeat",
    daily:"Daily",
    weekly:"Weekly",
    monthly:"Monthly",
    startDate:"Start date",
    untilDate:"End date (optional)",
    releaseTime:"Create tasks at",
    dueTime:"Task due time",
    interval:"Every N days / weeks / months",
    weeklyDays:"Days for weekly recurrence",
    exceptions:"Excluded dates (YYYY-MM-DD, comma-separated)",
    seriesHint:"Starts at the next scheduled creation time. Each person gets an independent task, or duties rotate. Late restarts do not create already overdue tasks. Monthly recurrence uses the start-date day and skips months without that day.",
    reminderMinutes:"Remind before deadline (minutes, 0 disables)",
    graceMinutes:"Grace after deadline (minutes)",
    taskPenalty:"Missed task points (0 disables)",
    health:"System health",parentsOnly:"Only parents can review system delivery.",noDeliveryIssues:"No unresolved delivery problems.",uncertain:"Delivery uncertain",failed:"Delivery failed",awaiting_channel:"Waiting for a linked chat",connected:"Connected",retryDelivery:"Review and resend",resolveDelivery:"Resolve without resending",retryWarning:"Telegram may already have accepted the message. Resending can create a duplicate.",resolveWarning:"This closes the warning without resending or claiming delivery.",retryConsent:"I accept the possible duplicate",channelHint:"Link the recipient's private chat in the Telegram options.",
    digests: "Personal digests", presence: "Family presence", polls: "Family polls", maintenance: "Home maintenance", meals: "Weekly menu", school: "School", pantry: "Pantry & household stock", routines: "Family routines", calendar: "Family calendar", today: "Family today", shopping: "Shopping", tasks: "Tasks", court: "Rules & rewards",
    alarms:"Wake-up alarms",alarmTime:"Wake-up time",timezone:"Time zone",days:"Days",weekdays:"Weekdays",weekends:"Weekends",everyday:"Every day",profile:"Wake-up style",gentle:"Messages only",strict:"Messages and dedicated siren",alarmPenalty:"Missed wake-up points (0 disables)",alarmDeviceHint:"Assign and test a dedicated siren in integration settings. Automatic penalties require separate opt-in.",moduleOff:"This module is disabled.",first:"First wake-up check",waiting_second:"Waiting for a second check",second:"Second wake-up check",testAlarm:"Test without penalties",soundRequested:"Sound requested — check the device status",soundPaused:"Sound paused",stopAlarm:"Stop this wake-up check",enabled:"Enabled",disabled:"Disabled",enable:"Enable",disable:"Disable",testAlarmWarning:"This test starts the selected siren in strict mode. No penalty will be issued.",startTest:"Start test",alarm_missed:"Wake-up was not confirmed in time",dayNames:["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
    empty: "All clear. Add something when you need it.", add: "Add", name: "Name",
    title: "What needs doing?", amount: "Amount", unit: "Unit", assignee: "Who?",
    due: "Due date", reason: "Reason", points: "Points", buy: "Bought", approve: "Approve",
    report: "Send report", complete: "Confirm done", reverse: "Reverse", pending: "Pending",
    loading: "Loading your family…", retry: "Try again", choose: "Choose a household",
    noHousehold: "No linked household. Add Family Assistant and link your HA account.",
    selectMember: "Choose a person", back: "Back", save: "Save", role: "Role",
    updated: "Saved", failure: "Could not complete this action.", open: "Open tasks",
    awaiting: "Awaiting approval", balance: "Balance", record: "Record", units: "units",
    refresh: "Refresh", entry: "Household", view: "View", reportLabel: "What did you do?",
    approved: "Ready to buy", purchased: "Bought", assigned: "Assigned", submitted: "In review",
    completed: "Completed", active: "Active", reversed: "Reversed", in_progress: "In progress",
    accepted: "Accepted", needs_changes: "Needs changes", rejected: "Rejected", archived: "Archived",
    cancelled: "Cancelled", unitPlaceholder: "kg, l, pcs", revision: "Revision",
  },
  ru: {
    networkWriteHint:"Роутер меняют только выбранные и подтверждённые планы. Чтение инвентаря ничего не меняет.",
    networkLeaseOnly:"Инвентарь DHCP. Чтение ничего не меняет; Kid Control настраивается отдельно.",networkLeaseWriteOff:"Изменение лизов DHCP выключено. Это не отключает отдельно разрешённые команды Kid Control.",
    networkPrepare:"Предпросмотр выбранных лизов",networkSelect:"Выбрать лиз",networkComment:"Предлагаемый комментарий",networkReplace:"Заменить существующий комментарий",networkApply:"Применить проверенный план",networkCancel:"Отменить план",networkReview:"Проверка изменений лизов",networkConsent:"Понимаю: откат преобразования удалит только новую резервацию. Для восстановления динамического DHCP нужно обновление лиза; это не точное восстановление.",networkWriteOff:"Запись выключена. В параметрах подключения разрешите проверенные изменения и защитите устройства управления, затем создайте свежий план.",networkToStatic:"Динамический → статический",networkNoChanges:"Без изменений",networkExpired:"Предпросмотр истёк — создайте новый.",networkState_preview:"Только предпросмотр",networkState_queued:"В очереди; ещё не применён",networkState_applying:"Применяется с повторной проверкой",networkState_rolling_back:"Откат выбранных изменений",networkState_applied:"Применён и проверен",networkState_rolled_back:"Выполнен откат — проверьте DHCP",networkState_review_required:"Нужна ваша проверка",networkState_failed:"Не применён",networkState_cancelled:"Отменён",networkSelectDynamic:"Выбрать подходящие динамические лизы",
    networkPhase_ready:"Не начато",networkPhase_converting:"Преобразование резервации",networkPhase_converted:"Резервация преобразована",networkPhase_commenting:"Обновление комментария",networkPhase_verified:"Проверено на роутере",networkPhase_unchanged:"Без изменений",networkPhase_removing:"Удаление новой резервации",networkPhase_restoring_comment:"Восстановление комментария",networkPhase_restored:"Исходные настройки восстановлены",networkPhase_dhcp_recovery:"Резервация удалена; может требоваться обновление DHCP",
    mikrotik:"Домашняя сеть",networkRefresh:"Перечитать роутер",networkReadOnly:"Только инвентарь. Чтение не меняет лизы и доступ в интернет.",networkParents:"Инвентарь сети доступен только родителям.",networkObserved:"Последнее успешное наблюдение",networkNoData:"Настройте MikroTik в параметрах интеграции и включите модуль.",networkSources:"Источники",networkSuggestions:"Совпадения в Home Assistant",networkProtected:"Защищённое устройство роутера или управления",networkUnknown:"Нет совпадения в HA",networkPrivateMac:"Локально назначенный MAC: проверьте, что для этой Wi-Fi-сети выбран постоянный адрес.",networkAmbiguous:"Несколько равных совпадений — нужен ручной выбор.",networkFasttrack:"FastTrack включён: ограничения скорости и фильтрацию нужно проверить с учётом топологии.",networkIPv6:"IPv6 включён или его состояние неизвестно; ограничений только IPv4 недостаточно.",networkUnavailable:"Недоступные таблицы",exact_mac:"Точное совпадение MAC",current_tracker_ip:"Текущий IP трекера",hostname_only:"Только hostname",networkMultiple:"Несколько текущих IP-адресов",
    conversation:"Семейный разговор",message:"Сообщение",send:"Отправить",thinking:"Разбираю обращение… Остальные карточки продолжают работать.",learnPhrase:"Обучить фразе",sourcePhrase:"Непонятная фраза",canonicalPhrase:"Поддерживаемая повторяемая команда",learningHint:"Точные фразы запоминаются только для вашего аккаунта. Они не дают прав и не заменяют встроенные команды.",forgetPhrase:"Отключить фразу",
    modelProposals:"Проверьте, правильно ли я понял",confirmPlan:"Выполнить план",rejectPlan:"Отменить план",proposalHint:"Пока ничего не изменено. Предложение действует до",
    advanced:"Дополнительные настройки",
    addSeries:"Добавить регулярную обязанность",
    recurring:"Регулярно",
    rotation:"По очереди",
    eachPerson:"Отдельная задача каждому",
    frequency:"Повторять",
    daily:"Ежедневно",
    weekly:"Еженедельно",
    monthly:"Ежемесячно",
    startDate:"Дата начала",
    untilDate:"Дата окончания (необязательно)",
    releaseTime:"Создавать задачи в",
    dueTime:"Срок выполнения",
    interval:"Каждые N дней / недель / месяцев",
    weeklyDays:"Дни еженедельного повторения",
    exceptions:"Исключения: даты ГГГГ-ММ-ДД через запятую",
    seriesHint:"Начнётся в следующий момент создания по расписанию. Каждому выдаётся отдельная задача либо участники чередуются. После долгого простоя уже просроченные задачи не создаются. Ежемесячно используется число даты начала; месяцы без этого числа пропускаются.",
    reminderMinutes:"Напомнить до срока (минут, 0 — выключено)",
    graceMinutes:"Пауза после срока (минут)",
    taskPenalty:"Баллы за пропуск задачи (0 — без штрафа)",
    health:"Состояние системы",parentsOnly:"Доставку уведомлений проверяют родители.",noDeliveryIssues:"Нет нерешённых проблем доставки.",uncertain:"Результат отправки неизвестен",failed:"Ошибка отправки",awaiting_channel:"Ожидается привязка чата",connected:"Подключён",retryDelivery:"Проверить и повторить",resolveDelivery:"Закрыть без повтора",retryWarning:"Telegram уже мог принять сообщение. Повторная отправка может создать дубликат.",resolveWarning:"Предупреждение будет закрыто без повтора и без утверждения о доставке.",retryConsent:"Понимаю, что возможен дубликат",channelHint:"Привяжите личный чат получателя в настройках Telegram.",
    digests: "Личные дайджесты", presence: "Семья дома", polls: "Семейные голосования", maintenance: "Обслуживание дома", meals: "Меню на неделю", school: "Школа", pantry: "Продукты и запасы", routines: "Семейные рутины", calendar: "Семейный календарь", today: "Семья сегодня", shopping: "Покупки", tasks: "Задачи", court: "Правила и поощрения",
    alarms:"Будильники",alarmTime:"Время подъёма",timezone:"Часовой пояс",days:"Дни",weekdays:"Будни",weekends:"Выходные",everyday:"Каждый день",profile:"Режим пробуждения",gentle:"Только сообщения",strict:"Сообщения и отдельная сирена",alarmPenalty:"Баллы за пропуск (0 — без штрафа)",alarmDeviceHint:"Назначьте и проверьте отдельную сирену в настройках интеграции. Автоштрафы включаются отдельно.",moduleOff:"Модуль выключен.",first:"Первая проверка подъёма",waiting_second:"Ожидается повторная проверка",second:"Повторная проверка подъёма",testAlarm:"Тест без штрафов",soundRequested:"Запрошен звук — проверьте состояние устройства",soundPaused:"Звук приостановлен",stopAlarm:"Остановить проверку подъёма",enabled:"Включён",disabled:"Выключен",enable:"Включить",disable:"Выключить",testAlarmWarning:"В строгом режиме тест включит назначенную сирену. Штрафов не будет.",startTest:"Начать тест",alarm_missed:"Подъём не подтверждён вовремя",dayNames:["Пн","Вт","Ср","Чт","Пт","Сб","Вс"],
    empty: "Всё спокойно. Добавьте запись, когда понадобится.", add: "Добавить", name: "Название",
    title: "Что нужно сделать?", amount: "Количество", unit: "Единица", assignee: "Кому?",
    due: "Срок", reason: "Причина", points: "Баллы", buy: "Куплено", approve: "Одобрить",
    report: "Сдать отчёт", complete: "Подтвердить", reverse: "Отменить балл", pending: "Ожидает",
    loading: "Загружаю семью…", retry: "Повторить", choose: "Выберите семью",
    noHousehold: "Нет привязанной семьи. Добавьте Family Assistant и свяжите пользователя HA.",
    selectMember: "Выберите участника", back: "Назад", save: "Сохранить", role: "Роль",
    updated: "Сохранено", failure: "Не удалось выполнить действие.", open: "Открытые задачи",
    awaiting: "Ждут решения", balance: "Баланс", record: "Записать", units: "позиций",
    refresh: "Обновить", entry: "Семья", view: "Раздел", reportLabel: "Что сделано?",
    approved: "Можно покупать", purchased: "Куплено", assigned: "Назначена", submitted: "На проверке",
    completed: "Выполнена", active: "Действует", reversed: "Отменён", in_progress: "В работе",
    accepted: "Принята", needs_changes: "На доработке", rejected: "Отклонено", archived: "В архиве",
    cancelled: "Отменена", unitPlaceholder: "кг, л, шт", revision: "Версия",
  },
  uk: {
    networkWriteHint:"Роутер змінюють лише вибрані й підтверджені плани. Читання інвентарю нічого не змінює.",
    networkLeaseOnly:"Інвентар DHCP. Читання нічого не змінює; Kid Control налаштовується окремо.",networkLeaseWriteOff:"Зміну лізів DHCP вимкнено. Це не вимикає окремо дозволені команди Kid Control.",
    networkPrepare:"Попередній перегляд вибраних лізів",networkSelect:"Вибрати ліз",networkComment:"Пропонований коментар",networkReplace:"Замінити чинний коментар",networkApply:"Застосувати перевірений план",networkCancel:"Скасувати план",networkReview:"Перевірка змін лізів",networkConsent:"Розумію: відкат перетворення видалить лише нову резервацію. Для відновлення динамічного DHCP потрібне оновлення ліза; це не точне відновлення.",networkWriteOff:"Запис вимкнено. У параметрах підключення дозвольте перевірені зміни й захистіть пристрої керування, потім створіть свіжий план.",networkToStatic:"Динамічний → статичний",networkNoChanges:"Без змін",networkExpired:"Попередній перегляд застарів — створіть новий.",networkState_preview:"Лише попередній перегляд",networkState_queued:"У черзі; ще не застосовано",networkState_applying:"Застосовується з повторною перевіркою",networkState_rolling_back:"Відкат вибраних змін",networkState_applied:"Застосовано й перевірено",networkState_rolled_back:"Виконано відкат — перевірте DHCP",networkState_review_required:"Потрібна ваша перевірка",networkState_failed:"Не застосовано",networkState_cancelled:"Скасовано",networkSelectDynamic:"Вибрати придатні динамічні лізи",
    networkPhase_ready:"Не розпочато",networkPhase_converting:"Перетворення резервації",networkPhase_converted:"Резервацію перетворено",networkPhase_commenting:"Оновлення коментаря",networkPhase_verified:"Перевірено на роутері",networkPhase_unchanged:"Без змін",networkPhase_removing:"Видалення нової резервації",networkPhase_restoring_comment:"Відновлення коментаря",networkPhase_restored:"Початкові налаштування відновлено",networkPhase_dhcp_recovery:"Резервацію видалено; може бути потрібне оновлення DHCP",
    mikrotik:"Домашня мережа",networkRefresh:"Перечитати роутер",networkReadOnly:"Лише інвентар. Читання не змінює лізи й доступ до інтернету.",networkParents:"Інвентар мережі доступний лише батькам.",networkObserved:"Останнє успішне спостереження",networkNoData:"Налаштуйте MikroTik у параметрах інтеграції та увімкніть модуль.",networkSources:"Джерела",networkSuggestions:"Збіги в Home Assistant",networkProtected:"Захищений пристрій роутера або керування",networkUnknown:"Немає збігу в HA",networkPrivateMac:"Локально призначений MAC: перевірте, що для цієї Wi-Fi-мережі вибрано постійну адресу.",networkAmbiguous:"Кілька рівних збігів — потрібен ручний вибір.",networkFasttrack:"FastTrack увімкнено: обмеження швидкості й фільтрацію слід перевірити з урахуванням топології.",networkIPv6:"IPv6 увімкнено або його стан невідомий; обмежень лише IPv4 недостатньо.",networkUnavailable:"Недоступні таблиці",exact_mac:"Точний збіг MAC",current_tracker_ip:"Поточний IP трекера",hostname_only:"Лише hostname",networkMultiple:"Кілька поточних IP-адрес",
    conversation:"Сімейна розмова",message:"Повідомлення",send:"Надіслати",thinking:"Опрацьовую звернення… Інші картки працюють далі.",learnPhrase:"Навчити фразі",sourcePhrase:"Незрозуміла фраза",canonicalPhrase:"Підтримувана повторювана команда",learningHint:"Точні фрази запам’ятовуються лише для вашого акаунта. Вони не надають прав і не замінюють вбудовані команди.",forgetPhrase:"Вимкнути фразу",
    modelProposals:"Перевірте, чи правильно я зрозумів",confirmPlan:"Виконати план",rejectPlan:"Скасувати план",proposalHint:"Поки нічого не змінено. Пропозиція діє до",
    advanced:"Додаткові налаштування",
    addSeries:"Додати регулярний обов’язок",
    recurring:"Регулярно",
    rotation:"По черзі",
    eachPerson:"Окреме завдання кожному",
    frequency:"Повторювати",
    daily:"Щодня",
    weekly:"Щотижня",
    monthly:"Щомісяця",
    startDate:"Дата початку",
    untilDate:"Дата завершення (необов’язково)",
    releaseTime:"Створювати завдання о",
    dueTime:"Термін виконання",
    interval:"Кожні N днів / тижнів / місяців",
    weeklyDays:"Дні щотижневого повторення",
    exceptions:"Винятки: дати РРРР-ММ-ДД через кому",
    seriesHint:"Почнеться в наступний час створення за розкладом. Кожен отримує окреме завдання або учасники чергуються. Після тривалого простою прострочені завдання не створюються. Щомісяця використовується число дати початку; місяці без цього числа пропускаються.",
    reminderMinutes:"Нагадати до терміну (хвилини, 0 — вимкнено)",
    graceMinutes:"Пауза після терміну (хвилини)",
    taskPenalty:"Бали за пропуск завдання (0 — без штрафу)",
    health:"Стан системи",parentsOnly:"Доставку сповіщень перевіряють батьки.",noDeliveryIssues:"Немає невирішених проблем доставки.",uncertain:"Результат надсилання невідомий",failed:"Помилка надсилання",awaiting_channel:"Очікується прив’язка чату",connected:"Підключено",retryDelivery:"Перевірити та повторити",resolveDelivery:"Закрити без повтору",retryWarning:"Telegram уже міг прийняти повідомлення. Повторне надсилання може створити дублікат.",resolveWarning:"Попередження буде закрито без повтору й без твердження про доставку.",retryConsent:"Розумію, що можливий дублікат",channelHint:"Прив’яжіть особистий чат отримувача в налаштуваннях Telegram.",
    digests: "Особисті дайджести", presence: "Родина вдома", polls: "Родинні голосування", maintenance: "Обслуговування дому", meals: "Меню на тиждень", school: "Школа", pantry: "Продукти й запаси", routines: "Сімейні рутини", calendar: "Сімейний календар", today: "Родина сьогодні", shopping: "Покупки", tasks: "Завдання", court: "Правила та заохочення",
    alarms:"Будильники",alarmTime:"Час підйому",timezone:"Часовий пояс",days:"Дні",weekdays:"Будні",weekends:"Вихідні",everyday:"Щодня",profile:"Режим пробудження",gentle:"Лише повідомлення",strict:"Повідомлення та окрема сирена",alarmPenalty:"Бали за пропуск (0 — без штрафу)",alarmDeviceHint:"Призначте й перевірте окрему сирену в налаштуваннях інтеграції. Автоштрафи вмикаються окремо.",moduleOff:"Модуль вимкнено.",first:"Перша перевірка підйому",waiting_second:"Очікується повторна перевірка",second:"Повторна перевірка підйому",testAlarm:"Тест без штрафів",soundRequested:"Запитано звук — перевірте стан пристрою",soundPaused:"Звук призупинено",stopAlarm:"Зупинити перевірку підйому",enabled:"Увімкнено",disabled:"Вимкнено",enable:"Увімкнути",disable:"Вимкнути",testAlarmWarning:"У суворому режимі тест увімкне призначену сирену. Штрафів не буде.",startTest:"Почати тест",alarm_missed:"Підйом не підтверджено вчасно",dayNames:["Пн","Вт","Ср","Чт","Пт","Сб","Нд"],
    empty: "Усе спокійно. Додайте запис, коли знадобиться.", add: "Додати", name: "Назва",
    title: "Що потрібно зробити?", amount: "Кількість", unit: "Одиниця", assignee: "Кому?",
    due: "Термін", reason: "Причина", points: "Бали", buy: "Куплено", approve: "Схвалити",
    report: "Здати звіт", complete: "Підтвердити", reverse: "Скасувати бал", pending: "Очікує",
    loading: "Завантажую родину…", retry: "Повторити", choose: "Виберіть родину",
    noHousehold: "Немає прив’язаної родини. Додайте Family Assistant і зв’яжіть користувача HA.",
    selectMember: "Виберіть учасника", back: "Назад", save: "Зберегти", role: "Роль",
    updated: "Збережено", failure: "Не вдалося виконати дію.", open: "Відкриті завдання",
    awaiting: "Чекають рішення", balance: "Баланс", record: "Записати", units: "позицій",
    refresh: "Оновити", entry: "Родина", view: "Розділ", reportLabel: "Що зроблено?",
    approved: "Можна купувати", purchased: "Куплено", assigned: "Призначено", submitted: "На перевірці",
    completed: "Виконано", active: "Діє", reversed: "Скасовано", in_progress: "У роботі",
    accepted: "Прийнято", needs_changes: "На доопрацюванні", rejected: "Відхилено", archived: "В архіві",
    cancelled: "Скасовано", unitPlaceholder: "кг, л, шт", revision: "Версія",
  },
};
const STYLES = `
  :host {display:block;color:var(--primary-text-color,#182c32);font-family:var(--paper-font-body1_-_font-family,system-ui)}
  *{box-sizing:border-box} ha-card{display:block;overflow:hidden;border-radius:22px;background:var(--ha-card-background,var(--card-background-color,#fff));border:1px solid var(--divider-color,#dfe9e7)}
  header{padding:24px 24px 18px;background:linear-gradient(135deg,rgba(19,146,127,.13),rgba(76,167,222,.04))}
  .eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--secondary-text-color,#657d80)}
  h2{font-size:24px;line-height:1.2;margin:8px 0 0;font-weight:650;letter-spacing:-.03em}
  .body{padding:18px 24px 24px}.row{display:flex;align-items:center;gap:10px}.grow{flex:1;min-width:0}.sub{font-size:12px;color:var(--secondary-text-color,#657d80);margin-top:6px}
  .list{display:grid;gap:10px;margin:0;padding:0;list-style:none}.item{padding:14px;border:1px solid var(--divider-color,#e3ebe9);border-radius:14px;overflow-wrap:anywhere}
  .item strong{font-size:15px}.badge{display:inline-block;border-radius:8px;background:rgba(19,146,127,.09);padding:3px 6px;margin:5px 4px 0 0;font-size:11px}
  button,input,select,textarea{font:inherit} button{border:1px solid var(--divider-color,#dfe9e7);border-radius:10px;padding:9px 12px;cursor:pointer;background:var(--ha-card-background,#fff);color:inherit;min-height:40px}
  button:hover{background:rgba(19,146,127,.1)}button.primary{background:#087f70;color:white;border-color:#087f70}button:disabled{opacity:.5;cursor:wait}
  button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #55bcba;outline-offset:2px}
  .actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.empty{padding:28px 8px;text-align:center;color:var(--secondary-text-color,#657d80)}
  form{display:grid;gap:12px;margin:0 0 18px}label{display:grid;gap:5px;font-size:12px;color:var(--secondary-text-color,#657d80)}
  input,select,textarea{width:100%;min-width:0;border:1px solid var(--divider-color,#d3dfdd);border-radius:10px;padding:10px;background:var(--ha-card-background,#fff);color:var(--primary-text-color,#182c32);font-size:14px}textarea{resize:vertical}
  .fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px}
  .metric{background:rgba(19,146,127,.07);padding:14px 8px;border-radius:14px;text-align:center}.metric b{display:block;font-size:25px}.metric span{font-size:11px}
  .notice{padding:12px;border-radius:12px;margin-bottom:12px;background:rgba(238,150,60,.14);font-size:13px}
  .toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:16px}.editor{padding:16px;display:grid;gap:12px}
  fieldset{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:6px;border:1px solid var(--divider-color,#dfe9e7);border-radius:12px;padding:10px;margin:0;min-width:0}
  legend{font-size:12px;color:var(--secondary-text-color,#657d80);padding:0 5px}
  label:has(input[type=checkbox]){display:flex;flex-direction:row-reverse;justify-content:flex-end;align-items:center;gap:8px;min-height:36px}
  label.check:has(input[type=checkbox]){flex-direction:row;justify-content:flex-start;align-items:flex-start;padding-top:8px}
  input[type=checkbox]{width:20px;height:20px;min-width:20px;min-height:0;padding:0;margin:0;accent-color:#087f70}
  details{border:1px solid var(--divider-color,#dfe9e7);border-radius:12px;padding:12px}summary{cursor:pointer;font-size:13px}.advanced{display:grid;gap:12px;padding-top:12px}
  .item>details{margin-top:12px}.shopping-archive,.tasks-archive{margin-top:16px}.shopping-archive>ul,.tasks-archive>ul{margin-top:12px}.item>form{margin-top:14px}
  .recurrence-fieldset,.calendar-task-links{display:block}
  .condition-editor{display:block}.condition-body,.condition-node{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;min-width:0}
  .condition-node .condition-node{border-inline-start:2px solid var(--divider-color,#dfe9e7);padding-inline-start:10px}
  .condition-editor select,.condition-editor input{max-width:100%;min-width:0;box-sizing:border-box}
  .recurrence-body{display:grid;gap:12px;margin-top:12px}
  .recurrence-fieldset label:has(input[type=checkbox]){flex-direction:row;justify-content:flex-start}
  .recurrence-hints p{font-size:12px;line-height:1.5;color:var(--secondary-text-color,#657d80)}
  .calendar-task-links p{font-size:12px;line-height:1.5}
  .meals-form-host:empty{display:none}.meal-plan-form,.meal-entries{display:grid;gap:14px}
  .meal-entry-editor{min-width:0}.meal-ingredients{grid-column:1/-1;display:grid;gap:10px;min-width:0}
  .ingredient-row{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr) minmax(0,1fr);gap:8px;min-width:0}
  .ingredient-row>button,.meal-entry-editor>button{grid-column:1/-1;align-self:start;justify-self:start}
  .meal-entry-editor input,.meal-entry-editor select{min-width:0;max-width:100%;box-sizing:border-box}
  .meal-plan{border-top:1px solid var(--divider-color,#dfe9e7);padding-top:14px;margin-top:14px}.meal-plan>.actions{margin-top:12px}
  .meal-entry{margin:12px 0;line-height:1.6}.meal-plan>details{margin-top:12px}
  @media(max-width:520px){.ingredient-row{grid-template-columns:minmax(0,1fr)}.meal-entry-editor{grid-template-columns:minmax(0,1fr)}}
  [hidden]{display:none!important}
  @media(max-width:400px){header{padding:20px 16px 16px}.body{padding:16px}.fields{grid-template-columns:1fr}h2{font-size:21px}}
`;

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

export class FamilyCard extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this._view = "today"; }
  setConfig(config) {
    disposeTaskMedia(this);
    disposeFaultPhotos(this);
    this._config = {...config};
    this._view = config.view || this.constructor.defaultView || "today";
    if (!["today","shopping","tasks","court","alarms","health","conversation","mikrotik","calendar","routines","pantry","meals","school","maintenance","polls","presence","digests"].includes(this._view)) throw new Error("Unknown Family Assistant view");
    this._generation = (this._generation || 0) + 1;
    this._entry = config.entry_id;
    this._data = null;
    this._shoppingSeriesFormOpen=false;this._shoppingSeriesEditingItem=null;this._shoppingSeriesDraft=null;
    this._shoppingItemAction=null;this._shoppingEditorDraft=null;this._pending=null;this._actionError=null;this._form=null;this._seriesForm=null;
    this._taskItemAction=null;this._taskCreateDraft=null;this._taskSeriesDraft=null;this._alarmEditorDraft=null;
    this._courtAction=null;this._courtDraft=null;this._courtConfigOpen=false;
    this._rewardDraft=null;this._calendarDraft=null;this._routineDraft=null;this._pantryDraft=null;this._mealsDraft=null;this._mealShoppingDraft=null;
    this._dietaryDraft=null;this._recipesDraft=null;this._schoolDraft=null;this._maintenanceDraft=null;this._schoolWorkDraft=null;this._schoolReminderDraft=null;this._pollsDraft=null;this._presenceDraft=null;this._digestsDraft=null;
    this._conversationDraft=null;this._articleDraft=null;
    this.render();
    if (this._hass) this.refresh();
  }
  set hass(hass) {
    const userChanged = this._hass && this._hass.user?.id !== hass?.user?.id;
    this._hass = hass;
    if (userChanged && this._config) {
      this._loading=false;this._writing=false;
      this.setConfig(this._config);
      return;
    }
    if (!this._data && !this._loading) this.refresh();
  }
  get t() { return COPY[this._config?.language || this._hass?.language?.split("-")[0]] || COPY.en; }
  get parent() { return ["owner","parent"].includes(this._data?.role); }
  getCardSize() { return 5; }
  getGridOptions() { return {columns:12, rows:"auto", min_columns:6}; }
  static getConfigElement() { return document.createElement("family-assistant-card-editor"); }
  static getStubConfig() { return {view:this.defaultView || "today"}; }
  connectedCallback() { this._timer = setInterval(()=>this.refresh(),10000); }
  disconnectedCallback() { clearInterval(this._timer); disposeTaskMedia(this); disposeFaultPhotos(this); disposeArticle(this); disposeConversation(this); disposeShoppingEditor(this); }
  async refresh() {
    if (!this._hass || !this._config || this._loading || this._writing) return;
    this._loading = true;
    const generation = this._generation;
    const focusSnapshot = captureFocusRefresh(this);
    try {
      if (!this._entry) {
        const entries = await this._hass.callWS({type:"family_assistant/households"});
        if (generation !== this._generation) return;
        this._entries = entries;
        if (entries.length === 1) this._entry = entries[0].entry_id;
        else { this.render(); return; }
      }
      const data = await this._hass.callWS({type:"family_assistant/view",entry_id:this._entry});
      if (generation !== this._generation) return;
      const previousData = this._data;
      this._data = data; this._error = null;
      const dietaryForce = reconcileDietaryRefresh(this,previousData);
      const recipesForce = reconcileRecipesRefresh(this,previousData);
      const schoolForce = reconcileSchoolRefresh(this,previousData);
      const schoolWorkForce = reconcileSchoolWorkRefresh(this,previousData);
      const schoolReminderForce = reconcileSchoolRemindersRefresh(this,previousData);
      const maintenanceForce = reconcileMaintenanceRefresh(this,previousData);
      const pollsForce = reconcilePollsRefresh(this,previousData);
      const presenceForce = reconcilePresenceRefresh(this,previousData);
      const digestsForce = reconcileDigestsRefresh(this,previousData);
      const healthForce = reconcileHealthRefresh(this,previousData);
      const alarmEditorForce = reconcileAlarmEditorRefresh(this,previousData);
      const taskSeriesForce = reconcileTaskSeriesRefresh(this,previousData);
      const articleForce = reconcileArticleRefresh(this,previousData);
      const conversationForce = reconcileConversationRefresh(this,previousData);
      const shoppingEditorForce = reconcileShoppingEditorRefresh(this,previousData);
      const routineForce = reconcileRoutineRefresh(this,previousData);
      const mediaForce = reconcileTaskMediaRefresh(this);
      const faultPhotoForce = reconcileFaultPhotos(this);
      // Avoid destroying a form that the user is currently filling out.
      if (dietaryForce || recipesForce || schoolForce || schoolWorkForce || schoolReminderForce || maintenanceForce || pollsForce || presenceForce || digestsForce || healthForce || alarmEditorForce || taskSeriesForce || articleForce || conversationForce || shoppingEditorForce || routineForce || mediaForce || faultPhotoForce || !this.shadowRoot.activeElement?.closest("form")) renderWithFocusRefresh(this,focusSnapshot,()=>this.render());
    } catch(error) { if (generation === this._generation) { disposeTaskMedia(this,{keepDraft:true}); disposeFaultPhotos(this,{keepDraft:true}); this._error=error.code || this.t.failure; this.render(); } }
    finally { if (generation === this._generation) this._loading = false; }
  }
  button(text, action, primary=false) {
    const button=el("button",text,primary?"primary":""); button.type="button";
    button.disabled=!!this._writing;
    button.addEventListener("click",action); return button;
  }
  input(form,name,label,type="text",value="",required=true) {
    const wrap=el("label",label); const input=el("input");
    Object.assign(input,{name,type,value,required});
    wrap.append(input); form.append(wrap); return input;
  }
  memberSelect(form) {
    const wrap=el("label",this.t.assignee); const select=el("select"); select.name="assignee";
    select.setAttribute("aria-label",this.t.assignee);
    const members=this._data.members.filter(m=>m.active && m.role!=="guest" && (this.parent || m.id===this._data.actor));
    for(const member of members) { const option=el("option",member.name);option.value=member.id;select.append(option); }
    wrap.append(select);form.append(wrap);return select;
  }
  async command(action,payload,operationId) {
    if (this._writing) return;
    const generation=this._generation;
    const fingerprint=JSON.stringify([this._entry,action,payload]);
    if(operationId || this._pending?.fingerprint!==fingerprint) this._pending={fingerprint,id:operationId || crypto.randomUUID()};
    this._writing=true;
    for(const b of this.shadowRoot.querySelectorAll("button")) b.disabled=true;
    try {
      const result=await this._hass.callWS({type:"family_assistant/execute",entry_id:this._entry,
        action,payload,operation_id:this._pending.id});
      if(generation===this._generation){this._pending=null;this._actionError=result?.accepted===false?"wrong_answer":null;this._form=null;this._seriesForm=null;}
    } catch(error) {if(generation===this._generation)this._actionError=error.code || this.t.failure;}
    finally {this._writing=false;await this.refresh();this.render();}
  }
  form() {
    if(this._view==="tasks")return renderTaskForm(this);
    const form=el("form");
    if(this._view==="shopping") {
      this.input(form,"name",this.t.name);
      const fields=el("div",null,"fields");form.append(fields);
      const amount=this.input(fields,"quantity",this.t.amount,"number","1");amount.min="0.001";amount.step="any";
      this.input(fields,"unit",this.t.unit,"text","",false).placeholder=this.t.unitPlaceholder;
    } else if(this._view==="court") {
      this.memberSelect(form);
      const points=this.input(form,"points",this.t.points,"number","1");points.min="-100";points.max="100";points.step="1";
      this.input(form,"reason",this.t.reason);
    }
    const submit=el("button",this.t.save,"primary");submit.type="submit";form.append(submit);
    form.addEventListener("submit",event=>{
      event.preventDefault();const values=Object.fromEntries(new FormData(form));
      if(this._view==="shopping") this.command("shopping.add",{...values,quantity:Number(values.quantity)});
      if(this._view==="court") this.command("court.award",{member:values.assignee,points:Number(values.points),reason:values.reason});
    });return form;
  }
  deadlinePolicy(form){
    for(const [key,label,value,min,max] of [["reminder_minutes",this.t.reminderMinutes,60,0,10080],["grace_minutes",this.t.graceMinutes,30,0,1440],...(this.parent?[["penalty",this.t.taskPenalty,0,-10,0]]:[])]){
      const input=this.input(form,key,label,"number",String(value));input.min=String(min);input.max=String(max);input.step="1";
    }
  }
  render() {
    const root=this.shadowRoot;root.replaceChildren(el("style",STYLES));
    const card=el("ha-card");root.append(card);
    const header=el("header");header.append(el("div",(!this._error && this._data?.settings.name) || "Family Assistant","eyebrow"),el("h2",this._config?.title || this.t[this._view]));card.append(header);
    const body=el("div",null,"body");card.append(body);
    if(this._actionError || this._error) {const language=this._config?.language || this._hass?.language?.split("-")[0],errors=ERRORS[language] || ERRORS.en,code=this._actionError || this._error;const routineText=this._view==="routines" && Object.values(ROUTINES_COPY[language] || ROUTINES_COPY.en).includes(code)?code:null;const notice=el("div",errors[code] || routineText || this.t.failure,"notice");notice.setAttribute("role","alert");body.append(notice);}
    if(!this._data) {
      body.append(el("div",this._entries?.length===0 ? this.t.noHousehold : this._entries?.length>1 ? this.t.choose : this.t.loading,"empty"));
      for(const entry of this._entries || []) body.append(this.button(entry.title,()=>{this._entry=entry.entry_id;this.refresh();}));
      if(this._error)body.append(this.button(this.t.retry,()=>this.refresh()));return;
    }
    if(this._error){body.append(this.button(this.t.retry,()=>this.refresh()));return;}
    if(this._view==="today") {renderToday(this,body);return;}
    this.renderProposals(body);
    if(this._view==="health") {renderHealth(this,body);return;}
    if(this._view==="routines"){renderRoutines(this,body);if(!this._data.settings.modules?.includes("routines"))body.append(el("div",this.t.moduleOff,"empty"));return;}
    if(this._view==="school"){
      if(renderAvailabilityShell(this,body,{module:"school",projection:this._data.school,state:this._data.role==="guest"?"role_unavailable":undefined})){
        this._schoolDraft=null;this._schoolWorkDraft=null;this._schoolReminderDraft=null;return;
      }
      if(!this._schoolDraft && !this._schoolWorkDraft)renderSchoolReminders(this,body);
      if(!this._schoolDraft && !this._schoolReminderDraft)renderSchoolWork(this,body);
      if(!this._schoolWorkDraft && !this._schoolReminderDraft)renderSchool(this,body);
      return;
    }
    if(this._view==="maintenance"){
      if(renderAvailabilityShell(this,body,{module:"maintenance",projection:this._data.maintenance,state:this._data.role==="guest"?"role_unavailable":undefined})){this._maintenanceDraft=null;return;}
      renderMaintenance(this,body);return;
    }
    if(this._view==="polls"){
      if(renderAvailabilityShell(this,body,{module:"polls",projection:this._data.polls,state:this._data.role==="guest"?"role_unavailable":undefined})){this._pollsDraft=null;return;}
      renderPolls(this,body);return;
    }
    if(this._view==="presence"){
      if(renderAvailabilityShell(this,body,{module:"presence",projection:this._data.presence,state:this._data.role==="guest"?"role_unavailable":undefined})){this._presenceDraft=null;return;}
      renderPresence(this,body);return;
    }
    if(this._view==="digests"){
      if(renderAvailabilityShell(this,body,{module:"digests",projection:this._data.digests,state:this._data.role==="guest"?"role_unavailable":undefined})){this._digestsDraft=null;return;}
      renderDigests(this,body);return;
    }
    if(this._view==="meals"){
      if(!this._recipesDraft){renderMeals(this,body);renderMealShopping(this,body);renderDietaryProfiles(this,body);}
      renderRecipes(this,body);return;
    }
    if(!this._data.settings.modules?.includes(this._view)){body.append(el("div",this.t.moduleOff,"empty"));return;}
    if(this._view==="conversation"){this.renderConversation(body);return;}
    if(this._view==="mikrotik"){this.renderNetwork(body);return;}
    if(this._view==="court"){renderCourt(this,body);renderRewards(this,body);return;}
    if(this._view==="calendar"){renderCalendar(this,body);return;}
    if(this._view==="pantry"){renderPantry(this,body);return;}
    if(this._view==="alarms"){
      this.renderAlarmRuns(body);
      if(renderAlarmEditor(this,body))return;
    }
    if(this._view==="tasks" && !this._form && !this._taskMediaDraft){
      renderTaskSeries(this,body);
      if(this._taskSeriesDraft)return;
    }
    if(this._view==="shopping"){renderShoppingSeries(this,body);renderShoppingEditor(this,body);}
    const toolbar=this._view==="shopping"?null:el("div",null,"toolbar");if(toolbar)toolbar.append(el("span",`${this._data[this._view]?.length || 0} ${this.t.units}`,"sub"));
    if(this._view==="alarms" && this.parent){
      const copy=ALARM_EDITOR_COPY[this._config?.language || this._hass?.language?.split("-")[0]] || ALARM_EDITOR_COPY.en;
      toolbar.append(this.button(copy.add,()=>openAlarmEditor(this),true));
    } else if(toolbar && this._view!=="alarms" && this._data.role!=="guest" && (this._view!=="court" || this.parent)) toolbar.append(this.button(this._form?this.t.back:this.t.add,()=>{this._form=!this._form;this._seriesForm=false;this._shoppingSeriesFormOpen=false;this._shoppingSeriesEditingItem=null;this._shoppingSeriesDraft=null;this.render();},true));
    if(toolbar)body.append(toolbar);if(this._form && this._view!=="shopping")body.append(this.form());
    const items=this._data[this._view] || [];
    const list=el("ul",null,"list");body.append(list);
    for(const item of items.filter(i=>this._view==="shopping"?["approved","pending"].includes(i.status):this._view==="tasks"?!["completed","cancelled","archived"].includes(i.status):i.status!=="archived").slice().reverse())this.renderItem(list,item);
    if(!list.children.length)body.append(el("div",this.t.empty,"empty"));
    if(this._view==="shopping")renderShoppingArchive(this,body);
    if(this._view==="tasks")renderTaskArchive(this,body);
  }
  renderNetwork(body) {
    renderKids(this,body);
    if(!this.parent){body.append(el("p",this.t.networkParents,"notice"));return;}
    body.append(el("p",this._data.network?.writable?this.t.networkWriteHint:this.t.networkLeaseOnly,"sub"));
    const health=this._data.health?.mikrotik;if(health && health!=="network_connected"){const lang=this._config?.language || this._hass.language?.split("-")[0];body.append(el("p",(ERRORS[lang] || ERRORS.en)[health] || this.t.failure,"notice"));}
    body.append(this.button(this.t.networkRefresh,async()=>{
      if(this._writing)return;const generation=this._generation;this._writing=true;
      try{await this._hass.callWS({type:"family_assistant/network_refresh",entry_id:this._entry});if(generation===this._generation)this._actionError=null;}
      catch(error){if(generation===this._generation)this._actionError=error.code || this.t.failure;}
      finally{this._writing=false;await this.refresh();this.render();}
    }));
    const inventory=this._data.network?.inventory;
    if(!inventory){body.append(el("p",this.t.networkNoData,"empty"));return;}
    this.renderNetworkPlans(body);
    const form=el("form");
    if(this._data.role==="owner"){
      if(!this._data.network?.writable)body.append(el("p",this.t.networkLeaseWriteOff,"notice"));
      form.append(this.button(this.t.networkSelectDynamic,()=>{for(const box of form.querySelectorAll('input[name="leases"][data-dynamic="true"]'))if(!box.disabled)box.checked=true;}));
      form.addEventListener("submit",event=>{event.preventDefault();const data=new FormData(form);const leases=data.getAll("leases").map(id=>({id,comment:data.get("comment:"+id),replace_comment:data.get("replace:"+id)==="on"}));this.command("mikrotik.lease_plan",{leases});});
    }
    body.append(el("p",`${this.t.networkObserved}: ${new Date(inventory.observed_at).toLocaleString(this._hass.language)}`,"sub"));
    if(inventory.fasttrack)body.append(el("p",this.t.networkFasttrack,"notice"));
    if(inventory.ipv6!=="disabled")body.append(el("p",this.t.networkIPv6,"notice"));
    const missing=Object.entries(inventory.capabilities || {}).filter(([,v])=>v!=="available").map(([k])=>k);
    if(missing.length)body.append(el("p",`${this.t.networkUnavailable}: ${missing.join(", ")}`,"sub"));
    if(this._data.role==="owner")body.append(form);
    for(const device of inventory.devices){
      const item=el("section",null,"item");item.append(el("strong",device.suggested_name || device.comments[0] || device.hostnames[0] || this.t.networkUnknown));
      item.append(el("p",`${device.mac} · ${device.addresses.join(", ")}`,"sub"));
      if(device.comments.length)item.append(el("p",device.comments.join(" · ")));
      item.append(el("p",`${this.t.networkSources}: ${device.sources.join(", ")}`,"sub"));
      if(device.protected)item.append(el("p",this.t.networkProtected,"notice"));
      for(const warning of device.warnings){const key={locally_administered:"networkPrivateMac",ambiguous_identity:"networkAmbiguous",multiple_addresses:"networkMultiple"}[warning];if(key)item.append(el("p",this.t[key],"sub"));}
      if(device.suggestions.length){const details=el("details");details.append(el("summary",this.t.networkSuggestions));for(const match of device.suggestions)details.append(el("p",`${match.name}${match.area?" · "+match.area:""} — ${match.evidence.map(e=>this.t[e] || e).join(", ")}`,"sub"));item.append(details);}
      if(this._data.role==="owner"){
        for(const lease of device.leases || []){
          const details=el("details");details.append(el("summary",`${this.t.networkSelect} · ${lease.address} · ${lease.server}`));
          const label=el("label",null,"check"),check=el("input");check.type="checkbox";check.name="leases";check.value=lease[".id"];check.dataset.dynamic=lease.dynamic;check.disabled=!!device.protected || lease.disabled==="true" || (lease.dynamic==="true" && lease.status!=="bound");label.append(check,el("span",this.t.networkSelect));details.append(label);
          const input=this.input(details,"comment:"+lease[".id"],this.t.networkComment,"text",device.suggested_name || lease.comment || "");input.maxLength=255;input.required=false;
          const replace=el("label",null,"check"),box=el("input");box.type="checkbox";box.name="replace:"+lease[".id"];replace.append(box,el("span",this.t.networkReplace));details.append(replace);item.append(details);
        }
        form.append(item);
      }else body.append(item);
    }
    if(this._data.role==="owner"){const button=el("button",this.t.networkPrepare,"primary");button.type="submit";form.append(button);}
  }
  renderNetworkPlans(body){
    const language=this._config?.language || this._hass.language?.split("-")[0],errors=ERRORS[language] || ERRORS.en;
    for(const plan of (this._data.network?.plans || []).slice().reverse()){
      const section=el("section",null,"item");section.append(el("strong",`${plan.id} · ${this.t["networkState_"+plan.status] || plan.status}`));
      const details=el("details");details.open=plan.status==="preview";details.append(el("summary",this.t.networkReview));
      for(const [index,target] of plan.targets.entries()){
        const line=el("p",`${target.address} · ${target.mac}\n${target.convert?this.t.networkToStatic:target.changed?this.t.networkComment:this.t.networkNoChanges}\n${target.old_comment || "—"} → ${target.comment || "—"}`,"sub");
        line.style.whiteSpace="pre-line";details.append(line);
        const progress=plan.progress?.targets?.[index];
        if(progress?.phase)details.append(el("p",this.t["networkPhase_"+progress.phase] || this.t.failure,"sub"));
        if(progress?.error)details.append(el("p",errors[progress.error] || this.t.failure,"notice"));
      }
      section.append(details);
      if(plan.progress?.failure)section.append(el("p",errors[plan.progress.failure] || this.t.failure,"notice"));
      if(plan.status==="preview" && this._data.role==="owner"){
        const expired=Date.parse(plan.expires_at)<=Date.now();
        if(expired)section.append(el("p",this.t.networkExpired,"notice"));
        if(!expired && this._data.network.writable){
          const form=el("form");
          if(plan.requires_dhcp_recovery_consent){const label=el("label",null,"check"),check=el("input");check.type="checkbox";check.name="dhcp_recovery";check.required=true;label.append(check,el("span",this.t.networkConsent));form.append(label);}
          const apply=el("button",this.t.networkApply,"primary");apply.type="submit";form.append(apply);
          form.addEventListener("submit",event=>{event.preventDefault();this.command("mikrotik.lease_apply",{id:plan.id,confirmed:true,dhcp_recovery:new FormData(form).get("dhcp_recovery")==="on"});});section.append(form);
        }
        section.append(this.button(this.t.networkCancel,()=>this.command("mikrotik.lease_cancel",{id:plan.id})));
      }
      body.append(section);
    }
  }
  renderConversation(body) {
    renderArticle(this,body);
    renderConversation(this,body);
  }
  renderProposals(body) {
    if(!this._data.settings.modules?.includes("conversation"))return;
    const proposals=(this._data.proposals || []).filter(p=>p.status==="pending" && Date.parse(p.expires_at)>Date.now());
    if(!proposals.length)return;
    const section=el("section");section.append(el("h3",this.t.modelProposals));body.append(section);
    for(const plan of proposals){
      const item=el("div",null,"item");item.append(el("div",plan.preview));
      item.append(el("div",`${this.t.proposalHint} ${new Date(plan.expires_at).toLocaleTimeString(this._hass?.language)}`,"sub"));
      const actions=el("div",null,"actions");
      actions.append(this.button(this.t.confirmPlan,()=>this.command("conversation.confirm",{id:plan.id}),true),this.button(this.t.rejectPlan,()=>this.command("conversation.reject",{id:plan.id})));
      item.append(actions);section.append(item);
    }
  }
  renderAlarmRuns(body) {
    for(const run of this._data.alarm_runs || []){
      if(!["first","waiting_second","second"].includes(run.stage))continue;
      const item=el("div",null,"item"),member=this._data.members.find(m=>m.id===run.member);
      item.append(el("strong",`${member?.name || ""} · ${this.t[run.stage]}`));
      if(run.test)item.append(el("div",this.t.testAlarm,"badge"));
      item.append(el("div",run.siren_desired?this.t.soundRequested:this.t.soundPaused,"sub"));
      if(run.challenge && run.member===this._data.actor){
        item.append(el("h3",run.challenge.question));
        const choices=el("div",null,"actions");
        for(const answer of run.challenge.choices)choices.append(this.button(String(answer),()=>this.command("alarms.answer",{id:run.id,nonce:run.challenge.nonce,answer}),true));
        item.append(choices);
      }
      if(this.parent)item.append(this.button(this.t.stopAlarm,()=>{
        const form=el("form");this.input(form,"reason",this.t.reason);
        const submit=el("button",this.t.stopAlarm);submit.type="submit";form.append(submit);
        form.addEventListener("submit",e=>{e.preventDefault();this.command("alarms.cancel",{id:run.id,...Object.fromEntries(new FormData(form))});});item.append(form);
      }));
      body.append(item);
    }
  }
  renderItem(list,item) {
    if(this._view==="tasks")return renderTaskItem(this,list,item);
    if(this._view==="shopping"){renderShoppingItem(this,list,item);return;}
    const row=el("li",null,"item");list.append(row);
    row.append(el("strong",item.name || item.title || item.reason || this.t[item.reason_key] || (this._view==="alarms"?item.time:"")));
    const meta=el("div",null,"sub");
    const member=this._data.members.find(m=>m.id===(item.assignee || item.member));
    const detail=this._view==="shopping"?`${item.purchased} / ${item.quantity} ${item.unit}`:
      this._view==="court"?`${member?.name || ""} · ${item.points>0?"+":""}${item.points}`:
      this._view==="alarms"?`${member?.name || ""} · ${item.time} · ${item.timezone}`:member?.name || "";
    meta.append(el("span",detail),el("span",this._view==="alarms"?this.t[item.enabled?"enabled":"disabled"]:this.t[item.status] || item.status,"badge"));
    if(this._view==="alarms")meta.append(el("div",item.days.map(day=>this.t.dayNames[day]).join(", ")));
    if(item.due_at)meta.append(el("div",new Date(item.due_at).toLocaleString(this._hass?.language)));
    row.append(meta);const actions=el("div",null,"actions");row.append(actions);
    const command=(action,extra={})=>this.command(action,{id:item.id,revision:item.revision,...extra});
    if(this._view==="alarms" && this.parent){
      const copy=ALARM_EDITOR_COPY[this._config?.language || this._hass?.language?.split("-")[0]] || ALARM_EDITOR_COPY.en;
      actions.append(this.button(copy.edit,()=>openAlarmEditor(this,item)));
      actions.append(this.button(item.enabled?this.t.disable:this.t.enable,()=>command("alarms.enable",{enabled:!item.enabled})));
      actions.append(this.button(this.t.testAlarm,()=>{
        const confirm=el("div",this.t.testAlarmWarning,"notice");
        confirm.append(this.button(this.t.startTest,()=>this.command("alarms.test",{id:item.id}),true));actions.replaceChildren(confirm);
      }));
    }
    if(this._view==="court" && this.parent && item.status==="active")actions.append(this.button(this.t.reverse,()=>{
      const form=el("form");this.input(form,"reason",this.t.reason);const submit=el("button",this.t.save,"primary");submit.type="submit";form.append(submit);
      form.addEventListener("submit",event=>{event.preventDefault();command("court.reverse",Object.fromEntries(new FormData(form)));});actions.replaceChildren(form);
    }));
  }
}

class FamilyEditor extends HTMLElement {
  constructor(){super();this.attachShadow({mode:"open"});}
  setConfig(config){this._config={...config};this.render();}
  set hass(hass){
    const identity=hass.connection || hass;
    this._hass=hass;
    if(identity!==this._identity){this._identity=identity;this._entries=null;this.loadHouseholds(identity);}
    if(!this.shadowRoot.activeElement)this.render();
  }
  async loadHouseholds(identity){
    try{
      const entries=await this._hass.callWS({type:"family_assistant/households"});
      if(identity!==this._identity)return;
      this._entries=entries;this._error=false;this.render();
    }catch{
      if(identity!==this._identity)return;
      this._error=true;this.render();
    }
  }
  render(){
    const t=COPY[this._hass?.language?.split("-")[0]] || COPY.en;this.shadowRoot.replaceChildren(el("style",STYLES));
    const form=el("div",null,"editor");this.shadowRoot.append(form);
    if(this._error){const notice=el("div",t.failure,"notice");notice.setAttribute("role","alert");form.append(notice);}
    for(const [name,label] of [["entry_id",t.entry],["title",t.name],["view",t.view]]){
      const wrap=el("label",label),input=el(name!=="title"?"select":"input");input.name=name;
      if(name==="entry_id"){
        const empty=el("option",this._entries?(this._entries.length?t.choose:t.noHousehold):t.loading);empty.value="";input.append(empty);
        for(const entry of this._entries || []){const option=el("option",entry.title);option.value=entry.entry_id;input.append(option);}
        input.disabled=!this._entries?.length;
      }
      if(name==="view")for(const view of ["today","shopping","tasks","court","alarms","health","conversation","mikrotik","calendar","routines","pantry","meals","school","maintenance","polls","presence","digests"]){const option=el("option",t[view]);option.value=view;input.append(option);}
      const defaultView={"custom:family-alarms-card":"alarms","custom:family-shopping-card":"shopping","custom:family-tasks-card":"tasks","custom:family-court-card":"court","custom:family-health-card":"health","custom:family-conversation-card":"conversation","custom:family-network-card":"mikrotik","custom:family-calendar-card":"calendar","custom:family-routines-card":"routines","custom:family-pantry-card":"pantry","custom:family-meals-card":"meals","custom:family-school-card":"school","custom:family-maintenance-card":"maintenance","custom:family-polls-card":"polls","custom:family-presence-card":"presence","custom:family-digests-card":"digests"}[this._config?.type] || "today";
      input.value=this._config?.[name] || (name==="view"?defaultView:"");wrap.append(input);form.append(wrap);
      input.addEventListener("change",()=>{this._config={...this._config,[name]:input.value};this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:this._config},bubbles:true,composed:true}));});
    }
  }
}
customElements.define("family-assistant-card-editor",FamilyEditor);
for(const [type,view] of [["family-assistant-card","today"],["family-shopping-card","shopping"],["family-tasks-card","tasks"],["family-court-card","court"],["family-alarms-card","alarms"],["family-health-card","health"],["family-conversation-card","conversation"],["family-network-card","mikrotik"],["family-calendar-card","calendar"],["family-routines-card","routines"],["family-pantry-card","pantry"],["family-meals-card","meals"],["family-school-card","school"],["family-maintenance-card","maintenance"],["family-polls-card","polls"],["family-presence-card","presence"],["family-digests-card","digests"]]){
  class Card extends FamilyCard {static defaultView=view;}
  customElements.define(type,Card);
  window.customCards=window.customCards || [];
  window.customCards.push({type,name:`Family Assistant · ${COPY.en[view]}`,description:COPY.en[view],preview:true});
}
export {COPY};
