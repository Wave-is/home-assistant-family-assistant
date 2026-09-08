# Private correction notes

Available with the conversation module. A current, unexpired model proposal can
be rejected with an optional explanation: wrong action, target, time, or other.
Open **Reject and describe the problem**, describe what you meant, check consent,
then save. Rejection and note use one atomic Home Assistant Store transaction.
No shopping item, task, alarm or learned rule is created by saving a note.

The optional original request must match the exact text that created the proposal,
including whitespace. Its SHA-256 is compared locally. If omitted, the original
request is explicitly unknown; the model preview is not treated as original text.
Limits: expected intent 400 characters, optional original 4096, preview 2200.

Only the same member, role and member revision can see or purge their notes.
Parents and owners cannot read a child's private notes through this interface.
The conversation card shows the saved preview, expected intent and optional source.
Deletion requires an explicit checkbox and removes only the selected note. It does
not erase the original proposal, command receipts, Telegram messages, logs or backups.
Data in the Home Assistant Store remains accessible to the installation administrator;
this is application-level privacy, not encryption against the HA host administrator.

In a **private** chat with your own configured bot:

```text
/feedback P… | wrong_target | What I meant instead
```

The category codes are `wrong_action`, `wrong_target`, `wrong_time`, `other`.
This rejects that exact proposal and saves the note without an original request.
Group submissions do not alter the proposal; the bot asks you to use its private
chat. A message already posted to the group is still visible there. `/cancel P…`
continues to reject without a note. The pending proposal expires after five minutes.

There are at most 64 active notes per household; reaching capacity never evicts
older notes. Delete your own unwanted notes explicitly. Records from a previous
member revision remain quarantined and count toward capacity; automatic account
reassignment or old-identity cleanup is not implemented. Invalid storage is left
unchanged and rejected. Exact command retries cannot duplicate or resurrect notes.

These notes are **not anonymous**. They are excluded from model context and the
optional technical export, and are never submitted to developers automatically.
They do not teach the parser or execute the expected text. Explicit `/learn` and
the existing phrase-learning form are a separate reviewed workflow with fresh
permissions and target/date parsing each time. Completed commands, arbitrary chat
answers, anonymized semantic reproducers and developer patch review remain outside
this first proposal-rejection path. No production auto-update is implied.
