# Reading public articles

Family Assistant can read one public web article that you explicitly choose and
summarize it with your configured Conversation model. Article reading is off by
default.

## English

### 1. Configure Conversation first

Open **Settings → Devices & services → Family Assistant → Configure → Language
model and fallback** and set up your own primary model. Enable the Conversation
module under **Household preferences** too. You may also configure a
fallback model there. Article reading uses those existing model settings; it
does not have a separate model or provider configuration.

The Conversation module and a model must be configured before article reading
can be enabled.

### 2. Enable article reading

In **Configure**, open **Public article reading**, enable it, review the policy,
and confirm. Access for children is a separate switch and remains off unless an
owner explicitly enables it.

### 3. Read an article

In the **Family conversation** card:

1. Select **Read a public article**.
2. Enter the exact public HTTPS URL.
3. Review the URL and the privacy disclosure.
4. Confirm the request.

Home Assistant downloads that page, extracts bounded readable text, and sends
only the page title and extracted article text to the configured primary model.
If the already-configured Conversation fallback is needed, the same restricted
input may be sent to it. The answer appears in the card with a citation to the
verified source page.

Article requests are always explicit. Links merely mentioned in a family chat
are not fetched automatically, and family state, private tasks, earlier chat
messages, credentials, and other household context are not added to the article
model request.

### Limits and privacy

- Only public HTTPS pages on the standard HTTPS port are supported.
- Private and local network addresses are blocked.
- Login-protected pages, credentials, PDFs, and page JavaScript are not
  supported.
- The destination website sees the outbound IP address of the Home Assistant
  server.
- The result is transient in the Conversation card; this feature does not add
  an article-reading route to Telegram.

## Русский

### 1. Сначала настройте разговорный модуль

Откройте **Настройки → Устройства и службы → Family Assistant → Настроить →
Языковая модель и резерв** и задайте свою основную модель. В **Параметрах семьи**
также включите модуль **Разговор**. Там же в настройках модели можно заранее
настроить резервную модель. Для статей используются уже заданные настройки
моделей; отдельной настройки модели или провайдера для них нет.

Чтобы включить чтение статей, разговорный модуль и модель должны быть настроены.

### 2. Включите чтение статей

В разделе **Настроить** откройте **Чтение публичных статей**, включите функцию,
проверьте политику и подтвердите её. Доступ для детей включается отдельным
переключателем и остаётся выключенным, пока владелец явно его не разрешит.

### 3. Прочитайте статью

В карточке **Семейный разговор**:

1. Выберите **Прочитать публичную статью**.
2. Введите точный публичный HTTPS-адрес.
3. Проверьте адрес и уведомление о передаче данных.
4. Подтвердите запрос.

Home Assistant загружает эту страницу, извлекает ограниченный объём читаемого
текста и отправляет основной модели только заголовок и извлечённый текст статьи.
Если потребуется уже настроенная резервная модель, ей может быть
отправлен тот же ограниченный набор данных. Ответ отображается в карточке со
ссылкой на проверенную исходную страницу.

Запрос статьи всегда выполняется явно. Ссылки, просто упомянутые в семейном
чате, автоматически не загружаются. Семейное состояние, личные задачи,
предыдущие сообщения, учётные данные и другой контекст семьи в запрос модели
для статьи не добавляются.

### Ограничения и конфиденциальность

- Поддерживаются только публичные HTTPS-страницы на стандартном HTTPS-порту.
- Частные и локальные сетевые адреса заблокированы.
- Страницы с авторизацией, учётные данные, PDF и JavaScript страницы не
  поддерживаются.
- Сайт назначения видит исходящий IP-адрес сервера Home Assistant.
- Результат временно показывается в карточке «Семейный разговор»; отдельного маршрута
  чтения статей в Telegram нет.

## Українська

### 1. Спочатку налаштуйте «Розмову»

Відкрийте **Налаштування → Пристрої та служби → Family Assistant → Налаштувати →
Мовна модель і резерв** та задайте свою основну модель. У **Параметрах родини**
також увімкніть модуль **Розмова**. У налаштуваннях моделі можна
заздалегідь налаштувати резервну модель. Для статей використовуються вже задані
налаштування моделей; окремого налаштування моделі чи провайдера для них немає.

Щоб увімкнути читання статей, модуль «Розмова» та модель мають бути налаштовані.

### 2. Увімкніть читання статей

У розділі **Налаштувати** відкрийте **Читання публічних статей**, увімкніть
функцію, перевірте політику та підтвердьте її. Доступ для дітей вмикається
окремим перемикачем і залишається вимкненим, доки власник явно його не дозволить.

### 3. Прочитайте статтю

У картці **Сімейна розмова**:

1. Виберіть **Прочитати публічну статтю**.
2. Введіть точну публічну HTTPS-адресу.
3. Перевірте адресу та повідомлення про передавання даних.
4. Підтвердьте запит.

Home Assistant завантажує цю сторінку, витягує обмежений обсяг читабельного
тексту та надсилає основній моделі лише заголовок і витягнутий текст статті.
Якщо знадобиться вже налаштована для «Розмови» резервна модель, їй може бути
надіслано той самий обмежений набір даних. Відповідь відображається в картці з
посиланням на перевірену вихідну сторінку.

Запит статті завжди виконується явно. Посилання, лише згадані в сімейному чаті,
автоматично не завантажуються. Сімейний стан, приватні завдання, попередні
повідомлення, облікові дані та інший сімейний контекст до запиту моделі для
статті не додаються.

### Обмеження та конфіденційність

- Підтримуються лише публічні HTTPS-сторінки на стандартному HTTPS-порту.
- Приватні та локальні мережеві адреси заблоковані.
- Сторінки з авторизацією, облікові дані, PDF і JavaScript сторінки не
  підтримуються.
- Сайт призначення бачить вихідну IP-адресу сервера Home Assistant.
- Результат тимчасово відображається в картці «Сімейна розмова»; окремого маршруту
  читання статей у Telegram немає.

## Technical contract

The owner Options flow uses steps `articles` and `article_policy_review`. The
policy is stored at `entry.options["articles"]` with the exact fields
`enabled`, `allow_children`, and a fresh 32-character lowercase hexadecimal
`revision`. Enabling requires the Conversation module and a configured model;
disabling remains available if either is unavailable.

The card receives only the bounded source projection
`{enabled, configured, allowed, revision}`. An allowed request pins that source
revision, the current entry/runtime and Home Assistant user identity, the
family-member epoch, and the actor role. Changes revoke an in-flight or retained
result, while an exact uncertain request may be retried with its frozen
operation ID only while the same authority remains current.
