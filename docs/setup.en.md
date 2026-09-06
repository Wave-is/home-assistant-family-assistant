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
requests do not change state. LLM/search setup is still pending; there is no
hidden developer provider or automatic cloud access.

## Dashboard cards

Until automatic resource registration is implemented, enable Advanced Mode in
your HA profile. Open dashboard Resources and add the JavaScript module:
`/family_assistant/frontend/family-assistant.js`. Refresh the browser, then add
a Family Assistant card through the card picker. Its visual editor lists only
households linked to your HA account; no configuration ID needs to be copied.

Available views: Today, Shopping, Tasks, Alarms, Rules & rewards, System health.
The card uses the HA interface language; each member can separately choose
their bot language. UI controls are not a substitute for server authorization.

## Wake-up checks and delivery problems

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

## Acceptance before household use

Verify each member sees only the intended data, `/ping` and quoted commands
work, duplicates do not repeat mutations, and tasks survive a restart. Test
both wake-up stages with the intended device while awake. Keep automatic
penalties disabled until delivery and wake-up tests are satisfactory. A public
release, migration and hardware acceptance remain separate gates.
