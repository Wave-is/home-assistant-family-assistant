# Family Assistant

A local-first family workspace for Home Assistant. Shopping, tasks, wake-up
checks, rewards, routines and family networking, using your own Telegram bot.

**Production release 0.1.0 (v1.0) is available.**
The stable [0.1.0 release](https://github.com/Wave-is/home-assistant-family-assistant/releases/tag/0.1.0)
provides a complete local-first family workspace for Home Assistant. The full product
scope is defined in [the vision](docs/vision.md). Implementation details and verification
evidence are tracked in [implementation status](docs/implementation-status.md).
For existing installations, a verified [safe migration contract](docs/legacy-migration.md) and
[rollback and recovery guide](docs/rollback.md) are provided across English, Russian, and Ukrainian.

The integration is designed for English, Russian and Ukrainian, configurable
households, and independent modules. Family data and credentials are kept in
Home Assistant storage, outside the HACS-managed code directory.

Setup guides: [English](docs/setup.en.md) · [Русский](docs/setup.ru.md) ·
[Українська](docs/setup.uk.md). The guides distinguish working features from
pending implementation and explain how to create and link your own bot.

Release policy and gating criteria are collected in
[release.md](docs/release.md). Migration contract and rollback procedures:
[Legacy migration / Миграция / Міграція](docs/legacy-migration.md) ·
[Rollback and recovery / Откат и восстановление / Відкат та відновлення](docs/rollback.md).

Module guides: [Shopping / Покупки / Покупки](docs/shopping.md) ·
[Voice shopping / Голосом / Голосом](docs/voice-shopping.md) ·
[Tasks / Задачи / Завдання](docs/tasks.md) ·
[Court / Семейный суд / Сімейний суд](docs/court.md) ·
[Privileges / Привилегии / Привілеї](docs/rewards.md) ·
[Calendar / Календарь / Календар](docs/calendar.md),
[Routines / Распорядки / Розпорядки](docs/routines.md) ·
[Pantry / Запасы / Запаси](docs/pantry.md) ·
[Expiry reminders / Напоминания о сроках / Нагадування про строки](docs/pantry-expiry.md) ·
[Weekly menu / Меню на неделю / Меню на тиждень](docs/meals.md) ·
[Dietary profiles / Пищевые предпочтения / Харчові вподобання](docs/dietary-profiles.md) ·
[Mealie recipes / Рецепты Mealie / Рецепти Mealie](docs/recipes.md) ·
[School / Школа / Школа](docs/school.md) ·
[Maintenance / Обслуживание / Обслуговування](docs/maintenance.md) ·
[Equipment documents / Документы / Документи](docs/equipment-documents.md) ·
[Menu shopping / Покупки по меню / Покупки за меню](docs/meal-shopping.md) ·
[Polls / Голосования / Голосування](docs/polls.md) ·
[Presence / Присутствие / Присутність](docs/presence.md) ·
[Digests / Дайджесты / Дайджести](docs/digests.md) ·
[Device review / Проверка устройств / Перевірка пристроїв](docs/network-admission.md) ·
[Discovery alerts / Новые устройства / Нові пристрої](docs/network-watch.md).

Optional explicit [article reading](docs/articles.md) uses your configured model
without sending family context. It is off by default and has a separate child
access opt-in.

Optional [existing HA conversation agent](docs/ha-conversation-agent.md): reviewed
official Ollama/no-control adapter for Core 2026.8.2, independent of direct
Ollama and fallback settings. Other agent integrations are not yet supported.

## Development

Optional technical reports: [English](docs/developer-diagnostics.md) ·
[Русский](docs/ru/developer-diagnostics.md) ·
[Українська](docs/uk/developer-diagnostics.md). Off by default, owner-reviewed,
with no automatic telemetry or code changes.

Private proposal correction notes: [English](docs/semantic-feedback.md) ·
[Русский](docs/ru/semantic-feedback.md) · [Українська](docs/uk/semantic-feedback.md).
These are private local notes, not anonymized bug reports or automatic fixes.

Python 3.14.2+ is the Home Assistant test target. Pure domain tests also run on
Python 3.11 without Home Assistant. Create a virtual environment, install
`requirements-dev.txt`, then run `pytest` and `ruff check .`.

Runtime code is under `custom_components/family_assistant`. Tests use synthetic
households only and never connect to a real Telegram bot or router.
