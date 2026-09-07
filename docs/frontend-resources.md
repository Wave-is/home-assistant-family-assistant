# Frontend resources / Ресурсы frontend / Ресурси frontend

## English

Family Assistant serves its cards only from the integration installed in Home Assistant. It does
not download JavaScript from a CDN or another server.

In Lovelace **storage resource mode**, the integration creates one `module` resource for the whole
Home Assistant installation, even when several Family Assistant entries exist. Its URL contains a
content fingerprint in the path. Relative imports use that same versioned path, so an upgrade does
not mix a new entry module with month-old cached helper modules.

The query `family_assistant_resource=1` is the integration's ownership marker. Family Assistant
updates only a record with that exact marker and path shape. It never adopts, rewrites, or deletes a
manual resource. If a manual Family Assistant resource or several marked records exist, automatic
registration stops without changing the resource list. Remove the duplicate manually in
**Settings → Dashboards → Resources**, then reload the integration. Keep only the automatically
marked resource.

Lovelace YAML resource mode is intentionally read-only to integrations. Family Assistant does not
edit `.storage` or YAML files. Keep the non-cached compatibility path in `configuration.yaml`:

```yaml
lovelace:
  resource_mode: yaml
  resources:
    - url: /family_assistant/frontend/family-assistant.js
      type: module
```

Restart Home Assistant after changing YAML. If the resource is absent or differs, the integration
logs the manual-mode requirement but does not attempt a hidden migration. This registration
mechanism does not create cards on a dashboard; add the desired Family Assistant card through the
dashboard editor.

## Русский

Family Assistant отдаёт код карточек только из установленной в Home Assistant интеграции. Код не
загружается из CDN или с внешнего сервера.

В режиме хранения ресурсов Lovelace **storage** интеграция создаёт один ресурс типа `module` на всю
установку Home Assistant, даже если семейных пространств несколько. В пути есть отпечаток всего
набора JavaScript-модулей. Поэтому после обновления новый основной модуль не смешивается со старыми
закешированными вспомогательными модулями.

Параметр `family_assistant_resource=1` — точная метка принадлежности интеграции. Family Assistant
обновляет только запись с такой меткой и ожидаемой формой пути. Ручные ресурсы не присваиваются, не
перезаписываются и не удаляются. Если уже есть ручной ресурс Family Assistant или несколько
помеченных записей, автоматическая регистрация ничего не меняет. Удалите дубликат вручную в
**Настройки → Панели управления → Ресурсы**, затем перезагрузите интеграцию. Оставьте только ресурс
с автоматической меткой.

В YAML-режиме ресурсов Lovelace интеграция намеренно не записывает ни YAML, ни `.storage`. Добавьте
стабильный путь без длительного кеширования в `configuration.yaml`:

```yaml
lovelace:
  resource_mode: yaml
  resources:
    - url: /family_assistant/frontend/family-assistant.js
      type: module
```

После изменения YAML перезапустите Home Assistant. Если ресурс отсутствует или отличается, в
журнале появится требование ручной настройки, но скрытой миграции не будет. Регистрация ресурса не
добавляет карточки на панели автоматически: нужную карточку следует добавить через редактор панели.

## Українська

Family Assistant віддає код карток лише з інтеграції, установленої в Home Assistant. Код не
завантажується з CDN або іншого зовнішнього сервера.

У режимі зберігання ресурсів Lovelace **storage** інтеграція створює один ресурс типу `module` на всю
інсталяцію Home Assistant, навіть якщо сімейних просторів кілька. Шлях містить відбиток усього
набору JavaScript-модулів. Тому після оновлення новий головний модуль не змішується зі старими
кешованими допоміжними модулями.

Параметр `family_assistant_resource=1` — точна позначка належності інтеграції. Family Assistant
оновлює лише запис із цією позначкою та очікуваною формою шляху. Ручні ресурси не привласнюються, не
перезаписуються й не видаляються. Якщо вже є ручний ресурс Family Assistant або кілька позначених
записів, автоматична реєстрація нічого не змінює. Видаліть дублікат вручну в
**Налаштування → Панелі керування → Ресурси**, потім перезавантажте інтеграцію. Залиште лише ресурс
з автоматичною позначкою.

У YAML-режимі ресурсів Lovelace інтеграція навмисно не записує ані YAML, ані `.storage`. Додайте
стабільний шлях без тривалого кешування до `configuration.yaml`:

```yaml
lovelace:
  resource_mode: yaml
  resources:
    - url: /family_assistant/frontend/family-assistant.js
      type: module
```

Після зміни YAML перезапустіть Home Assistant. Якщо ресурс відсутній або відрізняється, у журналі
з'явиться вимога ручного налаштування, але прихованої міграції не буде. Реєстрація ресурсу не додає
картки на панель автоматично: потрібну картку слід додати через редактор панелі.
