# Academy — development increment

Separate opt-in module, independent of School. Local practice for Ukrainian
grade 6/7 mathematics, with original Ukrainian and English lesson explanations.
The initial catalog is a **sample**, not a certified or complete school curriculum.
No external model or additional service is needed for grading. Parents may
explicitly opt into an existing conversation provider for hints on one assignment.
The provider sees only generated exercise text, lesson rule and language; no
submitted answers or family history. Local hints remain available without AI.

Enable Academy in household modules. Add `custom:family-assistant-academy-card`
to Lovelace. Parents assign a grade, language and topic subset, review per-topic
accuracy, mastery and next review dates, and archive assignments. A linked child
opens their own card, reads a short explanation and enters a numeric answer.
Three consecutive correct answers establish initial mastery. Review is due after
1, 3, 7, 14 and then every 30 days; a wrong answer resets mastery for that topic.
A profile revision change revokes child access until a new assignment is reviewed.

Private Telegram commands: /academy and /academyanswer ID | REVISION | TOPIC | ANSWER.
Never use them in the family group. YouTube links in the HA card are topic searches,
not curated or verified video recommendations. They open only when clicked.

State resides in the canonical family engine and uses its atomic persistence,
revision checks and operation idempotency. Lesson answer keys are not returned by
the API. No automatic LLM export, rewards, penalties, device control or public
student identifiers. The initial interface does not implement Telegram Mini App,
multi-turn AI tutoring, diagnostics, custom curricula, reminders, reports by schedule,
retention policy, or visual learning content. The 12-topic sample needs educational
review and expansion. Do not treat this development increment as a release.

Acceptance before release: pure domain and engine tests, identity revocation,
replay/backup/migration, late Telegram delivery, HA options/WS/store, three-language
mobile browser acceptance and privacy/packaging gates. No live household testing
or release is implied by this branch.
