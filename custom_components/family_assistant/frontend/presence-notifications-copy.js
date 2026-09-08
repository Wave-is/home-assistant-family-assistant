/* Localized copy for consent-bound notification presence gating. */

export const PRESENCE_NOTIFICATIONS_COPY = {
  en: {
    title: "Reminders when you return home",
    guide: "How reminders wait for your return",
    help: "Selected personal nonurgent reminders (tasks, personal digests, pantry expiry, and school preparation) wait until you are reported home by a fresh source observation before sending.",
    urgent_unchanged:
      "This preference does not delay wake-up alarms, direct replies or family group messages. Their ordinary delivery rules still apply.",
    unknown_and_cap:
      "While status is unknown or away, notifications wait up to your configured maximum wait cap. When that cap expires, stale held reminders are discarded rather than delivered late.",
    catchup:
      "Upon returning home, held messages catch up smoothly at a rate of at most 1 message per 2 minutes to avoid notification bursts.",
    revocation_and_safety:
      "Disabling this preference resumes ordinary delivery, including held reminders still current for the same recipient. Missing HA read permission or an inactive approving HA account means unknown: reminders wait until the cap. Presence is not proof anyone is safe or awake.",
    your_preference: "Your notification delivery",
    managed_children: "Children's notification delivery",
    guardian_help:
      "Owners and parents can configure notification presence gating for current children. Adults configure only their own notifications. Replacing the source, child profile, or approving parent revokes gating.",
    guardian_review: "Review notification gating for a child",
    review_title: "Review notification presence gating",
    status: "Gating status",
    source_status: "Presence source",
    source_available: "Configured; freshness and read permission are checked before delivery",
    source_unavailable: "No active source configured",
    effective_active: "Active (holding nonurgent reminders when away)",
    effective_suspended: "Consent needs renewal; ordinary delivery applies",
    effective_disabled: "Disabled (ordinary delivery rules apply)",
    max_wait: "Maximum wait cap",
    max_wait_input: "Maximum wait time (minutes)",
    max_wait_help:
      "Between 15 and 1440 minutes. Default is 720 minutes (12 hours). Stale held reminders are discarded after this limit.",
    minutes: "min",
    approved_by: "Approved by",
    enable: "Configure & enable",
    disable: "Disable gating",
    edit: "Change wait time",
    unavailable_action:
      "An active presence source must be configured in integration Settings before enabling notification presence gating.",
    person: "Family member",
    choice: "Choice",
    enable_choice: "Hold nonurgent notifications until fresh home",
    disable_choice: "Disable waiting — resume ordinary delivery rules",
    edit_choice: "Update maximum wait cap",
    member_version: "Member version",
    binding_version: "Source binding version",
    preference_version: "Delivery preference version",
    absent: "not created",
    confirm:
      "I checked the named family member. I understand nonurgent personal reminders will be held until fresh home status is reported, stale reminders are discarded after the wait cap, and this does not prove anyone is safe or awake.",
    save: "Save choice",
    retry: "Retry exact request",
    cancel: "Cancel",
    unavailable_member: "Current family member",
  },
  ru: {
    title: "Задержка уведомлений до возвращения домой",
    guide: "Как работает задержка уведомлений",
    help: "Выбранные личные несрочные напоминания (задачи, дайджесты, сроки продуктов и подготовка к школе) ждут свежего показания «дома» перед отправкой. Это отдельное согласие, не связанное с показом присутствия на карточке.",
    urgent_unchanged:
      "Эта настройка не задерживает будильники, прямые ответы и сообщения семейного чата. Их обычные правила доставки сохраняются.",
    unknown_and_cap:
      "Пока статус «неизвестно» или «не дома», уведомления ожидают до настроенного лимита времени. По истечении лимита устаревшие напоминания отменяются, а не приходят с опозданием.",
    catchup:
      "При возвращении домой накопленные сообщения доставляются постепенно — не чаще 1 сообщения за 2 минуты, чтобы не перегружать уведомлениями.",
    revocation_and_safety:
      "Выключение возвращает обычную доставку, включая ещё актуальные сообщения тому же получателю. Нет права чтения HA или отключён аккаунт давшего согласие — статус неизвестен, ожидание до лимита. Присутствие не доказывает безопасность или пробуждение.",
    your_preference: "Ваша доставка уведомлений",
    managed_children: "Доставка уведомлений детям",
    guardian_help:
      "Владелец и родители могут настроить задержку уведомлений для детей. Взрослые настраивают доставку только для себя. Замена источника, профиля ребёнка или давшего согласие родителя отменяет действие настройки.",
    guardian_review: "Проверка задержки уведомлений ребёнка",
    review_title: "Проверка задержки уведомлений",
    status: "Состояние задержки",
    source_status: "Источник присутствия",
    source_available: "Настроен; свежесть и права чтения проверяются перед отправкой",
    source_unavailable: "Актуальный источник не настроен",
    effective_active:
      "Включено (несрочные напоминания ждут возвращения домой)",
    effective_suspended:
      "Согласие требует обновления; действует обычная доставка",
    effective_disabled: "Выключено (обычные правила доставки)",
    max_wait: "Лимит ожидания",
    max_wait_input: "Максимальное время ожидания (минут)",
    max_wait_help:
      "От 15 до 1440 минут. По умолчанию 720 минут (12 часов). Устаревшие напоминания отменяются после этого лимита.",
    minutes: "мин",
    approved_by: "Кто настроил",
    enable: "Настроить и включить",
    disable: "Выключить задержку",
    edit: "Изменить время ожидания",
    unavailable_action:
      "Перед включением задержки уведомлений необходимо настроить активный источник в настройках интеграции.",
    person: "Участник семьи",
    choice: "Выбор",
    enable_choice:
      "Задерживать несрочные уведомления до свежего показания «дома»",
    disable_choice:
      "Выключить задержку — вернуть обычные правила доставки",
    edit_choice: "Обновить лимит ожидания",
    member_version: "Версия участника",
    binding_version: "Версия привязки источника",
    preference_version: "Версия настройки доставки",
    absent: "ещё не создана",
    confirm:
      "Я проверил(а) участника семьи и отдельно разрешаю проверять его присутствие для этих напоминаний. Они будут ждать свежего показания «дома», а после лимита будут отменены. Это не подтверждение безопасности или пробуждения.",
    save: "Сохранить выбор",
    retry: "Повторить точный запрос",
    cancel: "Отмена",
    unavailable_member: "Текущий участник семьи",
  },
  uk: {
    title: "Затримка сповіщень до повернення додому",
    guide: "Як працює затримка сповіщень",
    help: "Вибрані особисті нетермінові нагадування (завдання, особисті дайджести, терміни продуктів і підготовка до школи) чекають свіжого підтвердження статусу «удома» перед надсиланням.",
    urgent_unchanged:
      "Це налаштування не затримує будильники, прямі відповіді й повідомлення сімейного чату. Їхні звичайні правила доставки зберігаються.",
    unknown_and_cap:
      "Доки статус «невідомо» або «не вдома», сповіщення очікують до налаштованого ліміту часу. Після вичерпання ліміту застарілі нагадування скасовуються, а не надходять із запізненням.",
    catchup:
      "Після повернення додому накопичені повідомлення доставляються поступово — не частіше 1 повідомлення за 2 хвилини, щоб не перевантажувати сповіщеннями.",
    revocation_and_safety:
      "Вимкнення відновлює звичайну доставку, зокрема ще актуальних повідомлень тому самому одержувачу. Немає права читання HA або вимкнено обліковий запис того, хто дав згоду — статус невідомий, очікування до ліміту. Присутність не доводить безпеку чи пробудження.",
    your_preference: "Ваша доставка сповіщень",
    managed_children: "Доставка сповіщень дітям",
    guardian_help:
      "Власник і батьки можуть налаштувати затримку сповіщень для дітей. Дорослі налаштовують доставку лише для себе. Заміна джерела, профілю дитини чи того з батьків, хто дав згоду, скасовує дію налаштування.",
    guardian_review: "Перевірка затримки сповіщень дитини",
    review_title: "Перевірка затримки сповіщень",
    status: "Стан затримки",
    source_status: "Джерело присутності",
    source_available: "Налаштоване; свіжість і права читання перевіряються перед надсиланням",
    source_unavailable: "Чинне джерело не налаштоване",
    effective_active:
      "Діє (нетермінові нагадування затримуються поза домом)",
    effective_suspended:
      "Згода потребує оновлення; діє звичайна доставка",
    effective_disabled: "Вимкнено (звичайні правила доставки)",
    max_wait: "Ліміт очікування",
    max_wait_input: "Максимальний час очікування (хвилин)",
    max_wait_help:
      "Від 15 до 1440 хвилин. За замовчуванням 720 хвилин (12 годин). Застарілі нагадування скасовуються після цього ліміту.",
    minutes: "хв",
    approved_by: "Хто налаштував",
    enable: "Налаштувати й увімкнути",
    disable: "Вимкнути затримку",
    edit: "Змінити час очікування",
    unavailable_action:
      "Перед увімкненням затримки сповіщень потрібно налаштувати активне джерело в налаштуваннях інтеграції.",
    person: "Член родини",
    choice: "Вибір",
    enable_choice:
      "Затримувати нетермінові сповіщення до підтвердження «удома»",
    disable_choice:
      "Вимкнути затримку — повернути звичайні правила доставки",
    edit_choice: "Оновити ліміт очікування",
    member_version: "Версія учасника",
    binding_version: "Версія прив’язки джерела",
    preference_version: "Версія налаштування доставки",
    absent: "ще не створена",
    confirm:
      "Я перевірив(-ла) вказаного члена родини. Я розумію, що нетермінові особисті нагадування затримуються до підтвердження статусу «удома», застарілі сповіщення скасовуються після ліміту, і це не гарантує безпеку чи неспання.",
    save: "Зберегти вибір",
    retry: "Повторити точний запит",
    cancel: "Скасувати",
    unavailable_member: "Поточний член родини",
  },
};
