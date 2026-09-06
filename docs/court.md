# Family Assistant Court / Семейный суд / Сімейний суд

> [!WARNING]
> This documentation describes a development build and not a publicly released or production-deployed version.
> Документация описывает версию в разработке, не публичный релиз и не продакшн-развертывание.
> Документація описує версію в розробці, не публічний реліз і не продакшн-розгортання.

---

## English

Family Court provides auditable point awards and deductions with revision history, replayability, appeals, and optional weekly snapshots.

### Core Rules & Permissions

- **Parent Awards**: Privileged adults (parents/owners) award non-zero integer points from -100 to +100 with a mandatory reason.
- **Appeals & Reversals**: Children can appeal their own active records with a reason. Parents can reverse an active record directly or resolve an appeal (`uphold` or `reverse`) with a mandatory reason.
- **Independent Review**: Optional owner setting (`second_adult_review`) requires an independent adult who is neither the original record author nor the appellant. Requires at least 2 active privileged adults.
- **Immutable History**: Original records are never deleted. Status changes (reversals, appeal resolutions) append revision metadata and replay atomically.
- **Scope & Future Features**: No rewards store or configurable penalty consequences are implemented yet.

### Weekly Reports

- **Opt-in & Safe**: Disabled by default (`weekly_enabled: false`). Never resets member balances and never issues automatic punishments.
- **Schedule**: Household timezone, selected weekday and time (00:00–23:59). First summary triggers at the first boundary *after* activation.
- **Downtime & Archives**: After missed cycles, only the latest completed local period (half-open date interval) generates a report—no flood. Historical snapshot archives remain immutable even if past entries are reversed later; the live ledger reflects all updates.

### UI & Telegram

- **Card View**: `court` dashboard card displays current summary, score ledger, and reports. Children only see their own entries; privileged adults see all records. Task/alarm penalty records reference original task/wake-up triggers.
- **Conflict Handling**: Failed writes retain the submitted payload for an exact retry. After a configuration revision conflict, explicitly close and reopen settings to load the latest values; changes are never silently rebased.
- **Telegram Bot**: External messaging requires configuring your own bot token, chat/group IDs, and member links. By default, no external messages are dispatched.
- **Commands**:
  - `/stats` — show score balances
  - `/week` — view the current week's summary
  - `/award Member | -2 | Reason` — award or deduct points
  - `/appeal ID | Reason` — submit child appeal on active record
  - `/reverse ID | Reason` — reverse active record directly
  - `/courtresolve ID | uphold | Reason` or `/courtresolve ID | reverse | Reason` — resolve pending appeal

---

## Русский

Семейный суд обеспечивает прозрачный учет баллов с версионированием, защитой от удаления, апелляциями и еженедельными отчетами.

### Правила и доступ

- **Начисление баллов**: Родители/владельцы начисляют ненулевые целые баллы от -100 до +100 с обязательным указанием причины.
- **Апелляция и отмена**: Ребенок может подать апелляцию на свою активную запись с причиной. Родитель может напрямую отменить запись (`reverse`) или разрешить апелляцию (`uphold` или `reverse`) с обязательным обоснованием.
- **Независимая проверка**: Опция владельца требует независимого взрослого (не автора записи и не автора апелляции). Требуется минимум 2 активных родителя/владельца.
- **Неизменяемость**: Исходные записи не удаляются; история сохраняется через атомарные ревизии.
- **Ограничения**: Магазин наград и настраиваемые штрафные санкции еще не реализованы.

### Еженедельные отчеты

- **Выключены по умолчанию**: Отчеты опциональны, не сбрасывают баланс и не назначают штрафов.
- **Расписание**: Часовой пояс дома, выбранный день недели и время. Первый отчет формируется на ближайшей границе *после* включения.
- **Архивы и сбои**: При пропуске генерируется только последний завершенный период (полуоткрытый интервал дат) без лавины сообщений. Старые снапшоты неизменяемы даже при последующей отмене записей; актуальный баланс ведется в живом журнале.

### Интерфейс и Telegram

- **Карточка `court`**: Отображает сводку, журнал и архивы. Дети видят только свои записи, родители/владельцы — все. Автоштрафы содержат ID исходной задачи или проверки пробуждения.
- **Ошибки UI**: При сбое отправки данные сохраняются для точного повтора. При конфликте версий явно закройте и снова откройте настройки: загрузятся актуальные значения, чужие изменения не перезапишутся молча.
- **Telegram**: Требует собственного настроенного бота, группу и привязку участников; по умолчанию внешние сообщения отключены.
- **Команды**:
  - `/stats` — текущий баланс, `/week` — итоги текущей недели
  - `/award Участник | -2 | Причина`
  - `/appeal ID | Причина`
  - `/reverse ID | Причина`
  - `/courtresolve ID | uphold | Причина` или `/courtresolve ID | reverse | Причина`

---

## Українська

Сімейний суд забезпечує прозорий облік балів з історією ревізій, захистом від видалення, апеляціями та тижневими звітами.

### Правила та права

- **Нарахування балів**: Батьки/власники нараховують ненульові цілі бали від -100 до +100 з обов'язковою причиною.
- **Апеляція та скасування**: Дитина може подати апеляцію на свій активний запис із зазначенням причини. Батьки можуть скасувати запис (`reverse`) або вирішити апеляцію (`uphold` чи `reverse`) з обов'язковим обґрунтуванням.
- **Незалежний перегляд**: Опція власника вимагає незалежного дорослого (не автора запису і не автора апеляції). Потрібно щонайменше 2 активних дорослих із привілеями.
- **Незмінність**: Первинні записи ніколи не видаляються; зміни фіксуються через атомарне відтворення ревізій.
- **Межі функціоналу**: Магазин нагород та налаштовувані штрафні санкції ще не реалізовані.

### Щотижневі звіти

- **Вимкнено за замовчуванням**: Звіти опціональні, ніколи не скидають баланс і не призначають покарань.
- **Розклад**: Часовий пояс домогосподарства, вибраний день тижня та час. Перший звіт надсилається на найближчій межі *після* увімкнення.
- **Архіви та пропуски**: У разі простою створюється лише останній завершений період (напіввідкритий інтервал дат) без лавини сповіщень. Минулі знімки незмінні навіть після скасування старих записів; поточний журнал відображає всі зміни.

### Інтерфейс та Telegram

- **Картка `court`**: Відображає зведення, журнал і звіти. Діти бачать лише власні записи, батьки/власники — всі. Автоматичні штрафи містять ID завдання або перевірки пробудження.
- **Помилки UI**: При збоях збереження дані залишаються для точного повтору. При конфлікті версій явно закрийте та знову відкрийте налаштування: завантажаться актуальні значення без мовчазного перезапису чужих змін.
- **Telegram**: Потребує налаштування власного бота, групи та ідентифікаторів користувачів; за замовчуванням зовнішні повідомлення не надсилаються.
- **Команди**:
  - `/stats` — поточний баланс, `/week` — підсумки поточного тижня
  - `/award Учасник | -2 | Причина`
  - `/appeal ID | Причина`
  - `/reverse ID | Причина`
  - `/courtresolve ID | uphold | Причина` або `/courtresolve ID | reverse | Причина`
