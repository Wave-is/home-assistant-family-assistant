# Shopping barcodes / Штрихкоды покупок / Штрихкоди покупок

## English

In **Add shopping item** or **Edit details**, the optional barcode field accepts
GTIN-8, UPC-A/GTIN-12, EAN-13/GTIN-13 and GTIN-14: 8, 12, 13 or 14 digits with a
valid GS1 Mod10 check digit. Leading zeros are significant. The stored value is
14 digits, zero-padded, so equivalent UPC-A/EAN forms compare equally. Empty means
no barcode. Invalid values do not save. This checks structure, not registration,
ownership, authenticity or a product's name.

Enter the digits manually or with a keyboard-style handheld scanner. **Scan
barcode** optionally uses the browser's local camera and native `BarcodeDetector`
in a secure context (normally HTTPS). Browser and operating-system support varies;
when unavailable, manual input still works. The browser must support at least one
of EAN-8, EAN-13, UPC-A or ITF; ITF is accepted only with 14 digits and a valid
check digit. UPC-E, QR and arbitrary Code128 text are not interpreted as GTINs.

Camera access requires your button click and browser permission. No audio is
requested; no image, video or product query is uploaded to HA or an external
service. The camera stops after the first unambiguous valid code, on cancellation,
when leaving/hiding the page, or after one minute. A rebuilt form stops scanning
and never restarts it automatically. Multiple products in view require you to
point at one. A late permission or detection response cannot fill a closed or
revoked draft. Errors show a generic message, not provider internals.

Scanning only fills the code. Enter and review the name, quantity and unit before
the separate save confirmation; there is no product database lookup or automatic
purchase. Children's additions still require parent approval. Barcode metadata
and purchase history are household-visible, like the shopping list itself.

You can also enter a barcode in a recurring item. Each generated occurrence keeps
the template's current code. Editing/clearing an occurrence's code does not change
the series; editing the series does not rewrite old occurrences. Editing metadata
never changes purchased amounts. Purchase history preserves the code used at that
time, and add/edit history records changes. Merge additionally requires equal
barcodes: coded and uncoded items are not silently merged. Existing uncoded items
need no migration. Barcode entry is a dashboard feature, not Telegram image
recognition. Voice/photo shopping input is not delivered by this feature.

Verification uses strict domain tests, authenticated HA commands/Store reload,
and browser-local synthetic video with a controlled detector. This is not a claim
of physical-camera or native-decoder compatibility on every phone.

## Русский

В **Добавить покупку** и **Изменить данные** есть необязательный штрихкод:
8, 12, 13 или 14 цифр с правильной контрольной цифрой GTIN. Нули в начале
сохраняются; код хранится как 14 цифр с дополнением нулями. Пустое поле означает
отсутствие кода. Проверяется формат, а не подлинность товара или регистрация номера.

Можно ввести цифры вручную, ручным сканером-клавиатурой или нажать **Сканировать
штрихкод**. Камера доступна только в поддерживаемом браузере и защищённом контексте
(обычно HTTPS); если поддержки нет, остаётся ручной ввод. Поддерживаются EAN-8,
EAN-13, UPC-A и ITF-14 с правильной контрольной цифрой, но не UPC-E, QR и произвольный
Code128. Звук не запрашивается, кадры и запросы о товаре никуда не отправляются.

Камера включается только кнопкой и с разрешения браузера. Она выключается после
однозначного считывания, отмены, ухода/скрытия страницы или через минуту.
Перестроение формы тоже останавливает камеру без автоматического повторного
запуска. Если видны несколько кодов, наведите на один товар. Поздний ответ камеры
не заполняет закрытую форму или форму пользователя, утратившего права.

Сканирование заполняет только код: название, количество и единицу нужно проверить
перед отдельным сохранением. Базы товаров и автоматической покупки нет. Предложение
ребёнка остаётся на подтверждении родителя. Код и история видны семье.

Код доступен и в регулярных покупках: новые позиции получают код шаблона. Изменение
позиции не меняет шаблон, а изменение шаблона не переписывает старые позиции.
Количество уже купленного не меняется. История покупки сохраняет тогдашний код;
объединение требует одинаковых кодов, включая отсутствие кода. Старые покупки
без кода продолжают работать. Это функция дашборда, не распознавание фотографий
из Telegram и не голосовой ввод покупок.

Проверены сервер, команды и перезагрузка тестового HA, интерфейс и синтетический
видеопоток в браузере. Реальная камера и встроенный декодер каждого телефона
отдельно не проверялись.

## Українська

У формах **Додати покупку** та **Змінити дані** доступний необов’язковий штрихкод:
8, 12, 13 або 14 цифр із правильною контрольною цифрою GTIN. Початкові нулі
зберігаються; номер доповнюється нулями до 14 цифр. Порожнє поле означає відсутність
коду. Перевіряється структура, а не справжність товару чи реєстрація номера.

Введіть цифри вручну, сканером-клавіатурою або натисніть **Сканувати штрихкод**.
Камера потребує підтримуваного браузера та захищеного контексту (зазвичай HTTPS).
Якщо підтримки немає, ручний ввід працює. Підтримуються EAN-8, EAN-13, UPC-A та
ITF-14 із правильною контрольною цифрою, але не UPC-E, QR чи довільний Code128.
Аудіо не запитується, кадри й запити про товар нікуди не завантажуються.

Камера запускається лише кнопкою та з дозволу браузера; зупиняється після
однозначного зчитування, скасування, виходу/приховування сторінки або за хвилину.
Перебудова форми теж зупиняє її без автоматичного повторного запуску. За кількох
кодів у кадрі наведіть на один товар. Пізній дозвіл або результат не потрапить
у закриту форму чи до користувача, який втратив права.

Сканування заповнює тільки код. Перевірте назву, кількість та одиницю перед окремим
збереженням. Пошуку в базі товарів та автоматичної покупки немає. Дитячі пропозиції
залишаються на схваленні батьків. Код та історія видимі родині.

Регулярні покупки також мають код; нові позиції отримують актуальний код шаблону.
Редагування позиції не змінює шаблон, а зміна шаблону не переписує старі позиції.
Куплена кількість не змінюється. Історія придбання зберігає тодішній код; об’єднання
потребує однакових кодів, зокрема їх відсутності. Старі покупки без коду працюють.
Це можливість дашборда, не розпізнавання фотографій у Telegram і не голосовий ввід.

Перевірено сервер, команди й перезавантаження тестового HA, інтерфейс і синтетичний
відеопотік браузера. Фізична камера й нативний декодер кожного телефона не перевірені.

## References

- [GS1: GTIN-14 representation](https://support.gs1.org/support/solutions/articles/43000734355-what-is-the-required-format-of-gtin-in-gs1-edi-standards-)
- [GS1 General Specifications: check-digit calculation](https://ref.gs1.org/standards/genspecs/24.0.0/)
- [Chrome: native shape/barcode detection and feature detection](https://developer.chrome.com/docs/capabilities/shape-detection)
