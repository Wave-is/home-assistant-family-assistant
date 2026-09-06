# Family Assistant

A local-first family workspace for Home Assistant. Shopping, tasks, wake-up
checks, rewards, routines and family networking, using your own Telegram bot.

**Development in progress. No production release yet.** The accepted product
scope is in [the vision](docs/vision.md). The current implementation and test
evidence are tracked in [implementation status](docs/implementation-status.md).
Do not replace an existing installation with this development branch.

The integration is designed for English, Russian and Ukrainian, configurable
households, and independent modules. Family data and credentials are kept in
Home Assistant storage, outside the HACS-managed code directory.

Setup guides: [English](docs/setup.en.md) · [Русский](docs/setup.ru.md) ·
[Українська](docs/setup.uk.md). The guides distinguish working features from
pending implementation and explain how to create and link your own bot.

Module guides: [Shopping / Покупки / Покупки](docs/shopping.md) ·
[Tasks / Задачи / Завдання](docs/tasks.md) ·
[Court / Семейный суд / Сімейний суд](docs/court.md) ·
[Privileges / Привилегии / Привілеї](docs/rewards.md) ·
[Calendar / Календарь / Календар](docs/calendar.md),
[Routines / Распорядки / Розпорядки](docs/routines.md) ·
[Pantry / Запасы / Запаси](docs/pantry.md) ·
[Weekly menu / Меню на неделю / Меню на тиждень](docs/meals.md) ·
[Menu shopping / Покупки по меню / Покупки за меню](docs/meal-shopping.md).

## Development

Python 3.14.2+ is the Home Assistant test target. Pure domain tests also run on
Python 3.11 without Home Assistant. Create a virtual environment, install
`requirements-dev.txt`, then run `pytest` and `ruff check .`.

Runtime code is under `custom_components/family_assistant`. Tests use synthetic
households only and never connect to a real Telegram bot or router.
