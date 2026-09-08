# Existing Home Assistant conversation agent

Evaluation feature, not general support for every HA agent. Direct Ollama and
its fallback remain independent options.

## English

1. Enable the Conversation module in Family Assistant's household preferences.
2. In the **official Ollama integration**, create/select a conversation agent
   with **Control Home Assistant disabled**, **no LLM API**, and the **default
   instructions**. A separate no-control agent keeps another Assist agent's
   existing control settings intact. This adapter currently supports **Core
   2026.8.2 only**; other versions, default HA intents and third-party agents are
   rejected until their execution path is verified.
3. Family Assistant → Configure → **Existing Home Assistant agent**. Select the
   entity and timeout, then review and explicitly confirm. Inspection sends no
   model request and does not prove the model server is reachable. A new agent's
   `unknown` state is its empty last-activity timestamp, not a failed connection.
4. Link each participant's own active HA user in member settings. Calls use that
   identity and require read permission for the chosen conversation entity.
   Telegram-only members without an HA binding can use the separately configured
   direct Ollama providers; they never borrow an owner's identity.
5. Ask a question through the Family Assistant conversation card, its own Assist
   entity or your linked bot. Proposed family changes still need the normal
   explicit confirmation and pass the domain's authorization checks.

Provider order: **selected HA agent → direct primary Ollama → direct fallback
Ollama**, for the slots you configured. A missing HA-account binding does not
disable the provider for other members. Revoked permissions, changed identity
or changed in-flight agent selection fail the request instead of bypassing the
decision through another provider. Ordinary timeouts/bad responses may fall back.

Every native call starts a fresh conversation; quoted context comes only from
Family Assistant's scoped request. The model receives only that request's allowed
projection, not a general tool catalog or the whole household state. The native
agent also adds Core's standard date/time prompt. Core conversation traces and
your configured Ollama server may retain prompts: treat their storage and logs
as private. No native provider credentials are copied into Family Assistant.

Disabling this selection removes only its binding. Your direct primary/fallback
addresses and keys, search policy, members and records are preserved. If there
is no direct primary, conversation inference is disabled; deterministic commands
still work. Changing the native agent's tools/instructions can make it unsupported.
After a Core upgrade, use a verified direct Ollama configuration until this
adapter's native compatibility gate is extended. No automatic downgrade or
reconfiguration of your other integrations is performed.

## Русский

Включите модуль «Разговор». В **штатной интеграции Ollama** выберите или создайте
отдельного разговорного агента: **управление Home Assistant выключено**, **LLM API
не выбран**, **инструкции стандартные**. Так настройки другого Assist-агента с
управлением домом останутся нетронутыми. Пока проверен только **Core 2026.8.2**;
другие версии и сторонние агенты не принимаются.

Откройте Family Assistant → Настроить → **Готовый агент Home Assistant**, выберите
сущность и время ожидания. Проверьте выбор и отдельно подтвердите. Это проверка
настроек без запроса к модели, а не тест её доступности. `unknown` у нового
разговорного агента означает отсутствие времени последнего обращения.

Для каждого участника свяжите его собственную активную учётную запись HA с правом
чтения выбранной сущности. Участник только с Telegram может использовать прямую
основную/резервную Ollama; права владельца ему не подставляются. Порядок обращений:
**агент HA → основная Ollama → резервная Ollama**, если они настроены. Тайм-аут или
неправильный ответ допускают резерв; отзыв прав или смена участника/агента во время
запроса останавливают запрос без обхода через резерв.

Каждый вызов начинает новую беседу. В модель поступает разрешённый участнику
контекст Family Assistant, а не каталог устройств или инструменты управления
домом. Предложенное изменение семейных данных всё равно требует подтверждения.
Штатный агент добавляет дату/время Core. Трассировки HA и ваш сервер модели могут
сохранять текст — храните их как личные данные. Ключи штатной Ollama не копируются.

Выключение опции убирает только выбор агента, сохраняя прямую Ollama, её резерв,
ключи и семейные данные. Без прямого основного провайдера отключаются ответы
модели, но обычные команды продолжают работать. После обновления Core используйте
проверенное прямое подключение, пока совместимость адаптера не расширена. Другие
интеграции автоматически не перенастраиваются.

## Українська

Увімкніть модуль «Розмова». У **штатній інтеграції Ollama** виберіть або створіть
окремого розмовного агента: **керування Home Assistant вимкнене**, **LLM API не
вибрано**, **інструкції стандартні**. Налаштування іншого Assist-агента з керуванням
домом залишаться недоторканими. Поки перевірено лише **Core 2026.8.2**; інші версії
та сторонні агенти не приймаються.

Family Assistant → Налаштувати → **Готовий агент Home Assistant**: виберіть сутність
і час очікування, перевірте вибір та окремо підтвердьте. Перевірка налаштувань не
надсилає запит моделі й не підтверджує її доступність. `unknown` у нового агента
означає відсутність часу останнього звернення.

Кожному учаснику потрібен власний пов'язаний активний обліковий запис HA з правом
читання вибраної сутності. Учасник лише з Telegram може використовувати пряму
основну/резервну Ollama, але не права власника. Порядок: **агент HA → основна
Ollama → резервна Ollama**, якщо вони налаштовані. Тайм-аут або хибний формат
відповіді допускають резерв; відкликання прав або зміна учасника/агента під час
запиту зупиняють його без обходу через резерв.

Кожен виклик починає нову бесіду. Модель отримує дозволений учаснику контекст
Family Assistant, а не каталог пристроїв чи інструменти керування домом. Зміни
сімейних даних, запропоновані моделлю, потребують підтвердження. Штатний агент
додає дату/час Core. Трасування HA й ваш сервер моделі можуть зберігати текст —
захищайте їх як особисті дані. Ключі штатної Ollama не копіюються.

Вимкнення опції прибирає лише вибір агента, зберігаючи пряму Ollama, резерв, ключі
та сімейні дані. Без прямого основного провайдера відповіді моделі вимикаються,
але звичайні команди працюють. Після оновлення Core користуйтеся перевіреним
прямим підключенням, доки сумісність адаптера не розширено. Інші інтеграції
автоматично не переналаштовуються.

## Native contract references

- [Core 2026.8.2 conversation dispatch](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/conversation/agent_manager.py)
- [Official Ollama execution](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/ollama/conversation.py)
- [Native tool execution and prompt construction](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/conversation/chat_log.py)
- [Last-activity state](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/conversation/entity.py)
