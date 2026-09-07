# Set up your family

[Русский](setup.ru.md) · [Українська](setup.uk.md)

Development guide. There is **no production release yet**. Use an isolated Home
Assistant instance for evaluation; do not replace a working family system.
See [implemented and pending features](implementation-status.md).

## Installation and data

The release installation path is HACS → Custom repositories → this repository
(`Wave-is/home-assistant-family-assistant`), category Integration. Select a tested
release, install, restart HA when requested, then open Settings → Devices &
services → Add integration → Family Assistant. HACS default-catalog inclusion
is a separate review process; no inclusion is claimed here.

One configuration entry is one household. Only an HA administrator can create
it. Choose a name, your display name, language, IANA time zone (for example
`Europe/Berlin`) and template. The additional people in templates have no
linked accounts and cannot access anything until the owner links them.

Select the modules you need. Options → Members lets the owner rename people,
change roles/language, link HA users and add aliases, one per line. Use aliases
for grammatical forms or nicknames; ambiguous names require clarification.
Owner and parent roles may approve tasks; adults do not automatically receive
parental powers. Children see their own tasks, alarms and points.

Family records and credentials are stored in HA configuration-entry/Store data,
not in `custom_components`. Updating code must not erase them. Include HA data
in your private backups. Never publish `.storage`, tokens or diagnostic logs
without reviewing them. Do not manually edit Store files.

## Your own Telegram bot

1. Open the verified `@BotFather` in Telegram and send `/newbot`. Choose a name
   and unique username ending in `bot`. Keep its token private.
2. Open Family Assistant → Configure → Connect your own Telegram bot. Enable
   it and paste the token into the protected field. A blank field on later
   edits preserves the saved token. Disabling does not delete family records.
3. Add this bot to your family group. Open Link the family group in HA. Send the
   exact generated `/family_setup@your_bot CODE` command to that group.
4. Submit the waiting form, check the detected group name and ID, then confirm
   in HA. Receiving the code alone does not grant access.
5. For each person, choose Link a member's private chat. Let that person open
   the generated link and press Start. Check the detected account and confirm
   in HA. Parents also need linked personal chats for private review messages.
6. In the family group send `@your_bot тут?` or `/ping@your_bot`. Use your actual
   bot username. No LLM is needed for this check.

You do not need a third-party ID bot. A bot cannot start a private conversation
with someone who has not started it. Codes expire in 15 minutes and require
owner confirmation. Generate a new code if it expires; do not share invite
links publicly.

Keep Telegram Privacy Mode enabled for commands, mentions and replies. You can
address the bot by replying to its message. In BotFather, `/setprivacy` changes
which group messages Telegram delivers; disabling privacy may require removing
and adding the bot again. **Receiving all messages does not mean this version
answers unaddressed chatter.** It still responds only to direct addresses.

One bot token must have only one consumer. Do not use it simultaneously in
HA's Telegram Bot integration or another program. If a webhook/poller conflict
is reported, stop the owning consumer yourself before switching. Family
Assistant never deletes another application's webhook.

## Commands without AI

| Command | Result |
| --- | --- |
| `/help`, `/ping` | Help and immediate availability check |
| `/shopping` | Separate shopping list |
| `/buy Milk \| 2 \| l` | Add a purchase (child requests need parent approval) |
| `/bought S000001` | Mark the remaining quantity bought |
| `/tasks` | Authorized task list |
| `/task Child 1 \| Pack a bag` | Assign a task using an exact name or alias |
| `/done T000001 \| Packed everything` | Submit a text report |
| `/approve T000001` | Parent confirms completion |
| `/stats` | Point events and their reasons |
| `/alarms` | Wake-up schedules |

Selected natural phrases also work: `Child 1 task Pack a bag, deadline tomorrow`,
or reply to the task confirmation with `set deadline end of week`. End of week
means Sunday; a date without a time means 20:00 in the household time zone.
Past, invalid or ambiguous daylight-saving times are rejected. A reply must
refer to one actual bot message with a recorded delivery receipt. Pasted text
is not trusted as an object reference.

This is a bounded grammar, not a claim to understand every sentence. Unsupported
requests do not change state. There is no hidden developer provider or automatic cloud access.

## Optional model, fallback and search

1. Enable Conversation in Household preferences. In Language model and fallback,
   enter your own Ollama base URL and exact installed model name (`ollama list`
   or `/api/tags`). Configure an independent fallback URL/model if needed.
2. Saving verifies that each selected model exists. Requests have a configurable
   per-server timeout; a failed or malformed response falls back. Both URLs
   receive your messages and a limited, role-filtered family context. Do not use
   an untrusted server. No bot token, HA identity or siren challenge is included.
3. Prefer HTTPS or a trusted LAN/VPN. HTTP requires explicit consent and does
   not encrypt data. Never expose Ollama directly to the public internet. Blank
   API-key fields preserve the key; changing a URL requires a new key or clearing it.
4. For web questions configure your SearXNG URL and enable `json` in its
   `search.formats`. A language model alone does not have internet access. This
   version summarizes search snippets with filtered public source links; full
   article reading and alternative search adapters remain pending.
5. Unknown addressed messages enter a durable worker queue. Ping, task commands
   and wake-up buttons do not wait for inference. Quoted text is untrusted
   context, never authorization. Model mutations are previewed first; confirm
   with the Telegram button, `/confirm P…` or the dashboard. `/cancel P…` rejects.
   A proposal lasts five minutes, belongs to its requester, and is revalidated
   against current roles and record revisions. No inferred change happens silently.
6. The module creates a standard conversation entity for Assist. Select it in
   your pipeline. An unlinked/anonymous voice endpoint does not inherit a parent
   role. Existing external conversation-agent delegation is not implemented yet.

Calendar computations stay deterministic. Search results cannot execute commands.
Provider outages do not disable the core lists, tasks or alarms. The developer
agent/patch loop remains a separate pending gate.

To teach your own phrase explicitly, send `/learn my groceries | /shopping`.
Only your account can use it. The Conversation card also has a teaching form
and a list of your saved phrases. `/forget L…` disables a rule. Rules do not
grant permissions; relative dates and reply targets are resolved on each use.

An existing HA agent that supports selectable LLM APIs can select the household's
Family Assistant API. It provides role-filtered reads and confirmed plan previews,
not arbitrary HA services. Anonymous calls are rejected. This is tool access for
that agent, not automatic delegation of Telegram messages to it.

## Dashboard cards

With the normal Lovelace storage resource mode, Family Assistant registers one
local JavaScript module for the whole HA installation. Multiple household
entries share it. Its content fingerprint versions the complete relative module
graph, so a release cannot combine new card code with helper modules retained by
the browser's long cache. No external download is involved. After installing the
integration or applying a HACS update, restart Home Assistant so the new
fingerprint and static paths are registered, then refresh the browser and add a
card from the picker. The visual editor lists only households linked to your HA
account; no entry ID needs to be copied.

The 17 available card types are:

- `custom:family-assistant-card` — Today;
- `custom:family-shopping-card` — Shopping;
- `custom:family-tasks-card` — Tasks;
- `custom:family-court-card` — Rules & rewards;
- `custom:family-alarms-card` — Alarms;
- `custom:family-health-card` — System health;
- `custom:family-conversation-card` — Conversation;
- `custom:family-network-card` — Home network;
- `custom:family-calendar-card` — Calendar;
- `custom:family-routines-card` — Routines;
- `custom:family-pantry-card` — Pantry;
- `custom:family-meals-card` — Meals;
- `custom:family-school-card` — School;
- `custom:family-maintenance-card` — Maintenance;
- `custom:family-polls-card` — Polls;
- `custom:family-presence-card` — Presence;
- `custom:family-digests-card` — Digests.

Family Assistant updates only the storage resource bearing its exact ownership
marker. An existing manual URL is never adopted or overwritten. If HA reports a
frontend resource Repair, follow [the resource guide](frontend-resources.md):
remove a duplicate manually before reloading, or keep the documented manual
entry when Lovelace uses YAML resource mode. Family Assistant never edits YAML
or `.storage` directly.

The card uses the HA interface language; each member can separately choose
their bot language. UI controls are not a substitute for server authorization.

## Optional MikroTik inventory

Enable MikroTik in Household preferences and open its connection settings. Use
your own RouterOS 7 HTTPS address and a dedicated `read,rest-api` account. The
built-in read group has extra powers. An optional CA certificate can establish
trust for your router; do not paste its private key or disable TLS verification.
Blank password preserves the saved value, except when changing server/user.

On RouterOS **7.20.1**, native tests found that REST additionally requires the
`api` login policy: use `read,api,rest-api` for that version. Keep management
services restricted to your HA host; `api` also permits binary API login if that
service is reachable. Do not add administrator rights or expose ports publicly.
The integration does not modify router users, services or firewall rules.

The Home network card shows devices, existing comments and HA match evidence.
Ambiguous names require a manual choice; locally administered MAC does not prove
an intruder. Read failures retain the last successful observation.

For selected lease changes, the owner must separately allow writes, provide the
protected HA-host and administration-device MACs and confirm them. The dedicated
RouterOS account then needs `write` too. Select leases in the card, check proposed
comments and create a preview. Existing comments stay unless replacement is
checked. Applying a five-minute preview is a separate action; conversion also
requires consent that compensation removes only the new reservation and DHCP
renewal must recover the dynamic lease. This is not an exact dynamic rollback.
The card distinguishes queued, verified, compensated and review-required results.
Kid Control is described below; allowlist enforcement and end-to-end filtering
remain separate gates. See the
[network boundaries and remaining gates](network-architecture.md).

## Wake-up checks and delivery problems

The Tasks card also has **Add recurring duty**. Choose one or more people, a
daily/weekly/monthly rule, creation time and due time. Each person receives an
independent task, or select Take turns for rotation. Advanced settings contain
exceptions, end date, recurrence interval, reminders, grace period and optional
penalty. Templates start at the next scheduled creation; late restarts do not
generate tasks whose deadline has already passed. Missing monthly days are
skipped, not silently moved. Disabling a duty stops new instances and preserves
existing tasks and history. A submitted report is not penalized while awaiting
parent review. An automatic penalty requires both household opt-in and a
negative per-task/duty value; completion does not silently erase that history.

Create separate weekday/weekend schedules on the Alarms card. Gentle mode uses
messages. Strict mode additionally uses an explicitly assigned **dedicated**
wake-up siren in integration options. Never select a fire/security siren.
Check physical volume yourself; an HA state is not proof of audible sound.
The card asks again before a test; tests never apply penalties.

The first fresh challenge pauses sound. A second challenge arrives after a
random 12–18 minutes by default; strict mode resumes sound if unanswered after
the configured grace period. Old buttons and another person's response cannot
confirm waking. Automatic penalties are off by default and separately capped.

System health shows failed/uncertain deliveries. A timeout may occur after
Telegram already accepted a message, so it is not blindly resent. Check the
chat, then either close the warning or explicitly retry with a reason and
duplicate consent. If delivery waits for a channel, link the recipient's chat.

## Parents' Kid Control

In connection options, enable Kid Control writes separately from lease writes.
The protected HA/management MAC list must be confirmed. In the network card,
the owner selects an existing native profile and a child, reviews **every device**
and confirms ownership. This adoption changes only local integration data.
Parents can then preview pause, normal schedule, temporary access/pause, allowed
hours and rate limits. Applying the preview is a separate confirmation.
An adult without the parent role needs an explicit owner-granted permission.
Children can read their own adopted profile, without MACs or control buttons.

From your own bot: `/internet Child`, `/netpause Child`, `/netresume Child`,
`/netgrant Child | 30`, `/netblock Child | 15`, `/netuntil Child | 21:30`,
`/netschedule Child | weekdays | 08:00-22:00`, `/netlimit Child | 5M`.
Use the child's configured name or alias. Review the plan, then its confirmation
button or `/netconfirm K000001`; `/netcancel K000001` cancels an unapplied preview.
The bot queues work and reports the verified outcome privately; accepting an API
command alone is never reported as internet connectivity.

Pause is indefinite; resume restores the configured schedule, not unrestricted
24-hour access. Temporary operations require RouterOS 7.16+, synchronized clocks
and matching household/router time zones. Two narrowly scoped router scheduler
guards must be read back before access changes. The expiry guard restores the
previous mode without HA; the startup guard ends an exception early after router
reboot. A manually changed or recreated profile is not overwritten. Keep the
integration connected until its final verification/incident closure.

Verify actual filtering with a nonessential test client: IPv6, FastTrack and
downstream NAT may affect enforcement. Rate-unlimited (`tur-*`) periods override
rate limits; changing a day's allowed hours clears its separate unlimited window
and shows that in the diff. Native synthetic-profile tests are not proof of your
network's end-to-end filtering. Profile creation, per-device selection, holidays
and unknown-client strict mode remain development gates.

## Acceptance before household use

Verify each member sees only the intended data, `/ping` and quoted commands
work, duplicates do not repeat mutations, and tasks survive a restart. Test
both wake-up stages with the intended device while awake. Keep automatic
penalties disabled until delivery and wake-up tests are satisfactory. A public
release, migration and hardware acceptance remain separate gates.
