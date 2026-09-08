# Voice shopping with Home Assistant Assist

Uses your chosen Home Assistant speech-to-text provider. Family Assistant does
not install a speech engine, record the household microphone or contact a model
server until you configure the relevant providers. This is **Assist audio**, not
Telegram voice-message transcription or speaker recognition.

## English

1. Enable **Shopping** and **Conversation** in Family Assistant. For free-form
   shopping phrases, configure your own direct Ollama or the reviewed
   [existing HA provider](ha-conversation-agent.md).
2. Link each participant to their own active HA account in member settings.
3. Create a separate assistant in **Settings → Voice assistants**. Select this
   household's **Family Assistant conversation entity** as its conversation
   agent, not the default HA agent or the raw Ollama agent. Choose your installed
   speech-to-text provider and matching language. Speech output is optional.
4. Disable **Prefer handling commands locally** for that assistant. Otherwise
   Core can intercept a shopping phrase for its separate shopping-list feature.
5. Open Assist while signed in to your own HA account, select this assistant
   and use its microphone. For example: “Add milk to the shopping list.”
6. Read/listen to the proposed interpretation. Nothing is added by the model
   alone. In the **same Assist conversation**, use the microphone again and say
   **“Confirm the proposal”** or **“Cancel the proposal.”** Do not dictate the
   internal proposal ID. The preview expires after five minutes.

These exact review phrases work without another model call. “Yes” alone is not
a confirmation. Another question/action, an unfinished newer turn, a new
conversation, an expired proposal or a changed member identity requires a fresh
review; the system never guesses another conversation's proposal. Pending review
context survives a Family Assistant reload. A child's confirmed item still needs
parental shopping approval. `/confirm ID` and dashboard review remain available.

The **signed-in account**, not the sound of a voice, determines permissions.
Someone speaking into a parent's unlocked phone acts as that parent. Anonymous
voice satellites are not silently mapped to an owner. Use individual accounts;
do not expose a privileged microphone as a shared child-controlled endpoint.
Your STT/TTS/model providers and Core Assist traces may retain audio or text;
review their own privacy and storage settings. Local STT is an option, not an
automatic guarantee of this integration.

## Русский

Включите модули **Покупки** и **Разговор**, настройте свою Ollama или проверенного
[готового агента HA](ha-conversation-agent.md). Каждому участнику привяжите его
собственную активную учётную запись Home Assistant.

В **Настройки → Голосовые помощники** создайте отдельного помощника. Разговорным
агентом выберите **сущность Family Assistant нужной семьи**, а не стандартный HA
или саму Ollama. Укажите установленное распознавание речи и русский язык;
озвучивание ответа необязательно. Отключите предпочтительную локальную обработку
команд, иначе HA может направить покупку в свой отдельный список.

Откройте Assist под своей учётной записью и скажите, например: «Добавь молоко в
список покупок». Проверьте предложенное действие. В **той же беседе** снова нажмите
микрофон и скажите **«Подтверждаю предложение»** либо **«Отмени предложение»**.
Длинный внутренний ID диктовать не нужно. Предложение действует пять минут.
Подтверждение не вызывает модель повторно; простого «да» недостаточно.

Новый вопрос, действие, ещё выполняющийся новый запрос, новая беседа, истечение
срока или изменение участника требуют новой проверки. Перезапуск интеграции
сохраняет ожидающее подтверждение. Покупка ребёнка всё равно ждёт согласования
родителей. Можно подтвердить и на дашборде или командой `/confirm ID`.

Права определяются **учётной записью**, а не голосом. Ребёнок у разблокированного
телефона родителя действует от имени родителя. Анонимной колонке права владельца
не назначаются. Используйте отдельные аккаунты. Это голос через Assist, не
расшифровка голосовых сообщений Telegram. Проверьте хранение аудио и текста у
своих провайдеров распознавания, озвучивания, модели и в трассировках Assist.

## Українська

Увімкніть модулі **Покупки** та **Розмова**, налаштуйте свою Ollama або перевіреного
[готового агента HA](ha-conversation-agent.md). Кожному учаснику прив'яжіть його
власний активний обліковий запис Home Assistant.

У **Налаштування → Голосові помічники** створіть окремого помічника. Розмовним
агентом виберіть **сутність Family Assistant потрібної сім'ї**, не стандартний HA
і не саму Ollama. Виберіть установлене розпізнавання мовлення та українську мову;
озвучування відповіді необов'язкове. Вимкніть переважну локальну обробку команд,
інакше HA може спрямувати покупку до свого окремого списку.

Відкрийте Assist під власним обліковим записом і скажіть: «Додай молоко до списку
покупок». Перевірте запропоновану дію. У **тій самій розмові** знову натисніть
мікрофон і скажіть **«Підтверджую пропозицію»** або **«Скасуй пропозицію»**. Довгий
внутрішній ID диктувати не потрібно. Пропозиція діє п'ять хвилин. Підтвердження
не викликає модель повторно; самого «так» недостатньо.

Нове питання, дія, ще незавершений новий запит, нова розмова, завершення строку
або зміна учасника потребують нової перевірки. Перезапуск інтеграції зберігає
очікуване підтвердження. Покупка дитини все одно чекає батьківського погодження.
Також доступні дашборд і команда `/confirm ID`.

Права визначає **обліковий запис**, не голос. Дитина біля розблокованого телефона
батьків діє від їхнього імені. Анонімній колонці права власника не надаються.
Використовуйте окремі акаунти. Це голос через Assist, не розшифрування голосових
повідомлень Telegram. Перевірте зберігання аудіо/тексту в провайдерів розпізнавання,
озвучування, моделі та в трасуваннях Assist.

## Acceptance boundary

`tests/ha_voice_smoke.py` sends actual authenticated binary PCM WebSocket messages
through Core 2026.8.2's native Assist/STT/intent pipeline and the real family Store.
Only the speech recognizer and planner outputs are synthetic. This verifies
transport, identity and state transitions, **not transcription accuracy, physical
microphone quality, TTS audio or a live model**. No household recordings are used.

- [Official Assist audio protocol](https://developers.home-assistant.io/docs/voice/pipelines/)
- [Pinned pipeline and intent dispatch](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/assist_pipeline/pipeline.py)
