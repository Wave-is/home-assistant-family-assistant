import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost" });
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData"]) {
  globalThis[key] = dom.window[key];
}

const {
  RECURRENCE_COPY,
  makeRecurrenceDraft,
  recurrencePayload,
  renderRecurrence,
} = await import("../custom_components/family_assistant/frontend/recurrence-form.js");

test("RECURRENCE_COPY has strict locale parity across en, ru, and uk", () => {
  const enKeys = Object.keys(RECURRENCE_COPY.en).sort();
  const ruKeys = Object.keys(RECURRENCE_COPY.ru).sort();
  const ukKeys = Object.keys(RECURRENCE_COPY.uk).sort();

  assert.deepEqual(ruKeys, enKeys, "RU keys must match EN keys exactly");
  assert.deepEqual(ukKeys, enKeys, "UK keys must match EN keys exactly");

  for (const lang of ["en", "ru", "uk"]) {
    assert.equal(RECURRENCE_COPY[lang].dayNames.length, 7, `${lang} dayNames must have 7 items`);
    assert.equal(RECURRENCE_COPY[lang].dayNamesFull.length, 7, `${lang} dayNamesFull must have 7 items`);
    assert.ok(RECURRENCE_COPY[lang].dstExplanation, `${lang} must have dstExplanation`);
    assert.ok(RECURRENCE_COPY[lang].monthMissingExplanation, `${lang} must have monthMissingExplanation`);
    assert.ok(RECURRENCE_COPY[lang].catchupZeroExplanation, `${lang} must have catchupZeroExplanation`);
    assert.ok(RECURRENCE_COPY[lang].timezoneExplanation, `${lang} must have timezoneExplanation`);
  }
});

test("makeRecurrenceDraft produces a deep independent editable object with strings for numeric fields and preserves unknown keys", () => {
  const serverRule = {
    frequency: "weekly",
    interval: 2,
    start_date: "2026-09-07",
    until: "2026-12-31",
    time: "09:30",
    timezone: "Europe/Kyiv",
    weekdays: [0, 4],
    month_day: 15,
    exceptions: ["2026-10-02", "2026-10-09"],
    catchup_hours: 12,
    extra_field: "preserve_me",
  };

  const draft = makeRecurrenceDraft(serverRule);
  assert.equal(draft.enabled, true);
  assert.equal(draft.frequency, "weekly");
  assert.equal(draft.interval, "2");
  assert.equal(draft.start_date, "2026-09-07");
  assert.equal(draft.until, "2026-12-31");
  assert.equal(draft.time, "09:30");
  assert.equal(draft.timezone, "Europe/Kyiv");
  assert.deepEqual(draft.weekdays, [0, 4]);
  assert.equal(draft.month_day, "15");
  assert.equal(draft.exceptions, "2026-10-02\n2026-10-09");
  assert.equal(draft.catchup_hours, "12");
  assert.equal(draft.extra_field, "preserve_me");

  // Mutating serverRule must not affect draft
  serverRule.interval = 5;
  serverRule.weekdays.push(1);
  assert.equal(draft.interval, "2");
  assert.deepEqual(draft.weekdays, [0, 4]);

  // When rule is null, draft is disabled and takes defaults
  const nullDraft = makeRecurrenceDraft(null, {
    start_date: "2026-09-01",
    timezone: "Europe/Kyiv",
    weekdays: [2],
  });
  assert.equal(nullDraft.enabled, false);
  assert.equal(nullDraft.start_date, "2026-09-01");
  assert.equal(nullDraft.timezone, "Europe/Kyiv");
  assert.deepEqual(nullDraft.weekdays, [2]);
  assert.equal(nullDraft.interval, "1");
  assert.equal(nullDraft.catchup_hours, "24");
});

test("makeRecurrenceDraft infers default weekdays and month_day from valid start_date (Monday=0)", () => {
  // 2026-09-09 is a Wednesday -> Monday=0, Tuesday=1, Wednesday=2. Day is 9.
  const draft = makeRecurrenceDraft(null, {
    start_date: "2026-09-09",
  });
  assert.deepEqual(draft.weekdays, [2]);
  assert.equal(draft.month_day, "9");

  // 2026-09-07 is a Monday -> 0
  const mondayDraft = makeRecurrenceDraft(null, {
    start_date: "2026-09-07",
  });
  assert.deepEqual(mondayDraft.weekdays, [0]);
  assert.equal(mondayDraft.month_day, "7");

  // 2026-09-13 is a Sunday -> 6
  const sundayDraft = makeRecurrenceDraft(null, {
    start_date: "2026-09-13",
  });
  assert.deepEqual(sundayDraft.weekdays, [6]);
  assert.equal(sundayDraft.month_day, "13");
});

test("recurrencePayload returns null when enabled is strictly false", () => {
  const draft = makeRecurrenceDraft(null);
  assert.equal(draft.enabled, false);
  assert.equal(recurrencePayload(draft), null);
});

test("recurrencePayload requires enabled to be strict boolean and rejects malformed values", () => {
  const draft = makeRecurrenceDraft(null);
  for (const badEnabled of ["true", "false", 0, 1, [], {}, null, undefined]) {
    draft.enabled = badEnabled;
    assert.throws(
      () => recurrencePayload(draft),
      (err) => {
        assert.equal(err.code, "invalid_field");
        assert.equal(err.field, "enabled");
        return true;
      }
    );
  }
});

test("recurrencePayload rejects unknown server-rule keys rather than sending backend-invalid fields", () => {
  const draft = makeRecurrenceDraft({
    frequency: "daily",
    interval: 1,
    start_date: "2026-09-01",
    time: "08:00",
    timezone: "UTC",
    weekdays: [1],
    month_day: 1,
    exceptions: [],
    catchup_hours: 24,
    unsupported_extra_key: "danger",
  });

  assert.equal(draft.unsupported_extra_key, "danger");
  assert.throws(
    () => recurrencePayload(draft),
    (err) => {
      assert.equal(err.code, "invalid_field");
      assert.equal(err.field, "unsupported_extra_key");
      return true;
    }
  );

  // Removing the unknown key allows valid payload creation
  delete draft.unsupported_extra_key;
  const payload = recurrencePayload(draft);
  assert.ok(payload);
  assert.equal("unsupported_extra_key" in payload, false);
});

test("recurrencePayload strictly validates and yields canonical server rule with roundtrip preservation", () => {
  const original = {
    frequency: "monthly",
    interval: 3,
    start_date: "2026-01-15",
    until: "2027-01-15",
    time: "14:45",
    timezone: "Europe/Kyiv",
    weekdays: [2, 0, 2], // with duplicate to test deduplication and sorting
    month_day: 31,
    exceptions: ["2026-04-15", "2026-02-15", "2026-02-15"], // unsorted + duplicate
    catchup_hours: 0,
  };

  const draft = makeRecurrenceDraft(original);
  assert.equal(draft.catchup_hours, "0");

  const payload = recurrencePayload(draft);
  assert.deepEqual(payload, {
    frequency: "monthly",
    interval: 3,
    start_date: "2026-01-15",
    until: "2027-01-15",
    time: "14:45",
    timezone: "Europe/Kyiv",
    weekdays: [0, 2],
    month_day: 31,
    exceptions: ["2026-02-15", "2026-04-15"],
    catchup_hours: 0,
  });

  // Re-drafting the produced payload preserves it identically
  const redraft = makeRecurrenceDraft(payload);
  const reprep = recurrencePayload(redraft);
  assert.deepEqual(reprep, payload);
});

test("recurrencePayload throws stable error codes and field names", () => {
  const validDraft = () =>
    makeRecurrenceDraft({
      frequency: "daily",
      interval: 1,
      start_date: "2026-09-01",
      until: null,
      time: "08:00",
      timezone: "UTC",
      weekdays: [0],
      month_day: 1,
      exceptions: [],
      catchup_hours: 24,
    });

  function checkError(draft, expectedField) {
    assert.throws(
      () => recurrencePayload(draft),
      (err) => {
        assert.equal(err.code, "invalid_field");
        assert.equal(err.field, expectedField);
        return true;
      }
    );
  }

  // Invalid root
  assert.throws(() => recurrencePayload(null), { code: "invalid_field", field: "recurrence" });

  // Invalid frequency
  let d = validDraft();
  d.frequency = "yearly";
  checkError(d, "frequency");

  // Strict integer parsing: no parseInt coercion (e.g. "2abc", "3.5", empty)
  d = validDraft();
  d.interval = "2abc";
  checkError(d, "interval");

  d = validDraft();
  d.interval = "2.5";
  checkError(d, "interval");

  d = validDraft();
  d.interval = "0"; // interval must be >= 1
  checkError(d, "interval");

  d = validDraft();
  d.interval = "53"; // interval must be <= 52
  checkError(d, "interval");

  // Calendar dates: real validity check
  d = validDraft();
  d.start_date = "2026-02-29"; // 2026 is not a leap year!
  checkError(d, "start_date");

  d = validDraft();
  d.start_date = "invalid-date";
  checkError(d, "start_date");

  // Leap year 2024-02-29 is valid
  d = validDraft();
  d.start_date = "2024-02-29";
  assert.equal(recurrencePayload(d).start_date, "2024-02-29");

  // Until date before start_date
  d = validDraft();
  d.start_date = "2026-09-10";
  d.until = "2026-09-05";
  checkError(d, "until");

  // Until date invalid calendar
  d = validDraft();
  d.until = "2026-04-31"; // April has 30 days
  checkError(d, "until");

  // Time format
  d = validDraft();
  d.time = "25:00";
  checkError(d, "time");

  d = validDraft();
  d.time = "8:00";
  checkError(d, "time");

  // Timezone real validity
  d = validDraft();
  d.timezone = "Not/A/Zone";
  checkError(d, "timezone");

  d = validDraft();
  d.timezone = "";
  checkError(d, "timezone");

  // Weekdays
  d = validDraft();
  d.weekdays = [];
  checkError(d, "weekdays");

  d = validDraft();
  d.weekdays = [7]; // 0..6
  checkError(d, "weekdays");

  d = validDraft();
  d.weekdays = ["0", "invalid"];
  checkError(d, "weekdays");

  // Month day
  d = validDraft();
  d.month_day = "0";
  checkError(d, "month_day");

  d = validDraft();
  d.month_day = "32";
  checkError(d, "month_day");

  d = validDraft();
  d.month_day = "15.5";
  checkError(d, "month_day");

  // Exceptions count and format
  d = validDraft();
  d.exceptions = "2026-02-29";
  checkError(d, "exceptions");

  d = validDraft();
  d.exceptions = Array(367).fill("2026-01-01").join("\n");
  checkError(d, "exceptions");

  // Catchup hours (0..48)
  d = validDraft();
  d.catchup_hours = "-1";
  checkError(d, "catchup_hours");

  d = validDraft();
  d.catchup_hours = "49";
  checkError(d, "catchup_hours");

  d = validDraft();
  d.catchup_hours = "0"; // 0 is valid!
  assert.equal(recurrencePayload(d).catchup_hours, 0);

  d = validDraft();
  d.catchup_hours = "48"; // 48 is valid!
  assert.equal(recurrencePayload(d).catchup_hours, 48);
});

test("renderRecurrence creates accessible localized fieldset without innerHTML or injection", () => {
  const draft = makeRecurrenceDraft({
    frequency: "weekly",
    interval: 1,
    start_date: "2026-09-07",
    until: "",
    time: "09:00",
    timezone: "Europe/Kyiv",
    weekdays: [0, 2],
    month_day: 1,
    exceptions: "",
    catchup_hours: 24,
  });

  const maliciousText = '<img src=x onerror=alert(1)> <script>alert("xss")</script>';
  draft.timezone = maliciousText;

  const container = document.createElement("div");
  renderRecurrence(container, draft, { language: "uk" });

  assert.equal(container.querySelectorAll("img").length, 0);
  assert.equal(container.querySelectorAll("script").length, 0);

  const tzInput = container.querySelector('[data-recurrence-control="timezone"]');
  assert.equal(tzInput.value, maliciousText);

  // Fieldset and controls exist with appropriate data attributes
  const fieldset = container.querySelector("fieldset[data-recurrence-group='main']");
  assert.ok(fieldset);

  const enableCheckbox = container.querySelector('[data-recurrence-control="enabled"]');
  assert.ok(enableCheckbox);
  assert.equal(enableCheckbox.checked, true);

  // Weekdays checkboxes rendered for weekly
  const weekdayBoxes = container.querySelectorAll('[data-recurrence-control="weekdays"]');
  assert.equal(weekdayBoxes.length, 7);
  assert.equal(weekdayBoxes[0].checked, true); // Monday
  assert.equal(weekdayBoxes[1].checked, false); // Tuesday
  assert.equal(weekdayBoxes[2].checked, true); // Wednesday

  // Explanations present
  const dstHint = container.querySelector('[data-recurrence-hint="dst"]');
  assert.ok(dstHint);
  assert.ok(dstHint.textContent.includes(RECURRENCE_COPY.uk.dstExplanation));

  const catchupZeroHint = container.querySelector('[data-recurrence-hint="catchup_zero"]');
  assert.ok(catchupZeroHint);
  assert.ok(catchupZeroHint.textContent.includes(RECURRENCE_COPY.uk.catchupZeroExplanation));
});

test("hidden irrelevant number controls do not block form.checkValidity, and turning repeat off permits checkValidity and null payload", () => {
  const form = document.createElement("form");
  const draft = makeRecurrenceDraft({
    frequency: "daily",
    interval: 1,
    start_date: "2026-09-07",
    until: "",
    time: "08:00",
    timezone: "UTC",
    weekdays: [0],
    month_day: 99, // Invalid day of month (1..31) in hidden field!
    exceptions: "",
    catchup_hours: 24,
  });

  renderRecurrence(form, draft);

  const monthDayInput = form.querySelector('[data-recurrence-control="month_day"]');
  assert.equal(monthDayInput.value, "99");
  // Since frequency is daily, monthDayInput is irrelevant and disabled so it doesn't block validity
  assert.equal(monthDayInput.disabled, true);
  assert.equal(form.checkValidity(), true);

  // Now set visible interval to an invalid number e.g. 999 (max is 52)
  const intervalInput = form.querySelector('[data-recurrence-control="interval"]');
  intervalInput.value = "999";
  intervalInput.dispatchEvent(new dom.window.Event("input"));
  assert.equal(form.checkValidity(), false);

  // Turning repeat off completely disables body controls and allows form to be valid and payload to be null
  const enableCheckbox = form.querySelector('[data-recurrence-control="enabled"]');
  enableCheckbox.checked = false;
  enableCheckbox.dispatchEvent(new dom.window.Event("change"));

  assert.equal(draft.enabled, false);
  assert.equal(intervalInput.disabled, true);
  assert.equal(form.checkValidity(), true);
  assert.equal(recurrencePayload(draft), null);
});

test("turning recurrence on re-enables controls but respects lockedFields", () => {
  const draft = makeRecurrenceDraft(null, {
    start_date: "2026-09-07",
    timezone: "Europe/Kyiv",
  });
  assert.equal(draft.enabled, false);

  const container = document.createElement("div");
  renderRecurrence(container, draft, {
    lockedFields: ["timezone", "start_date"],
  });

  const enableCheckbox = container.querySelector('[data-recurrence-control="enabled"]');
  const tzInput = container.querySelector('[data-recurrence-control="timezone"]');
  const startInput = container.querySelector('[data-recurrence-control="start_date"]');
  const timeInput = container.querySelector('[data-recurrence-control="time"]');

  // When disabled, all body controls are disabled
  assert.equal(timeInput.disabled, true);
  assert.equal(tzInput.disabled, true);
  assert.equal(startInput.disabled, true);

  // Turn repeat ON
  enableCheckbox.checked = true;
  enableCheckbox.dispatchEvent(new dom.window.Event("change"));

  assert.equal(draft.enabled, true);
  assert.equal(timeInput.disabled, false); // Re-enabled!
  assert.equal(tzInput.disabled, true); // Still locked!
  assert.equal(startInput.disabled, true); // Still locked!
});

test("disabled synthetic events cannot mutate draft", () => {
  const draft = makeRecurrenceDraft({
    frequency: "daily",
    interval: 1,
    start_date: "2026-09-07",
    until: "",
    time: "08:00",
    timezone: "UTC",
    weekdays: [0],
    month_day: 1,
    exceptions: "",
    catchup_hours: 24,
  });

  const container = document.createElement("div");
  renderRecurrence(container, draft, {
    lockedFields: ["interval", "time"],
  });

  const intervalInput = container.querySelector('[data-recurrence-control="interval"]');
  const timeInput = container.querySelector('[data-recurrence-control="time"]');

  assert.equal(intervalInput.disabled, true);
  assert.equal(timeInput.disabled, true);

  // Attempt synthetic dispatch on disabled controls
  intervalInput.value = "10";
  intervalInput.dispatchEvent(new dom.window.Event("input"));
  assert.equal(draft.interval, "1", "Draft interval must not mutate when control is disabled");

  timeInput.value = "12:00";
  timeInput.dispatchEvent(new dom.window.Event("input"));
  assert.equal(draft.time, "08:00", "Draft time must not mutate when control is disabled");

  // When recurrence is turned off, body controls are disabled and cannot be mutated
  const enableCheckbox = container.querySelector('[data-recurrence-control="enabled"]');
  enableCheckbox.checked = false;
  enableCheckbox.dispatchEvent(new dom.window.Event("change"));

  const tzInput = container.querySelector('[data-recurrence-control="timezone"]');
  assert.equal(tzInput.disabled, true);
  tzInput.value = "America/New_York";
  tzInput.dispatchEvent(new dom.window.Event("input"));
  assert.equal(draft.timezone, "UTC", "Disabled body control must not mutate draft when repeat is off");
});

test("visibility toggles preserve values in hidden fields without rebuilding entire DOM", () => {
  const draft = makeRecurrenceDraft({
    frequency: "weekly",
    interval: 2,
    start_date: "2026-09-07",
    until: "",
    time: "09:00",
    timezone: "UTC",
    weekdays: [1, 3],
    month_day: 25,
    exceptions: "",
    catchup_hours: 12,
  });

  const container = document.createElement("div");
  let changeCount = 0;
  renderRecurrence(container, draft, {
    onChange: () => {
      changeCount++;
    },
  });

  const body = container.querySelector('[data-recurrence-group="body"]');
  const weekdaysGroup = container.querySelector('[data-recurrence-group="weekdays"]');
  const monthDayWrap = container.querySelector('[data-recurrence-field="month_day"]');
  const freqSelect = container.querySelector('[data-recurrence-control="frequency"]');

  // Initial: weekly
  assert.equal(body.hidden, false);
  assert.equal(weekdaysGroup.hidden, false);
  assert.equal(monthDayWrap.hidden, true);

  // Switch to monthly
  freqSelect.value = "monthly";
  freqSelect.dispatchEvent(new dom.window.Event("change"));

  assert.equal(draft.frequency, "monthly");
  assert.equal(changeCount, 1);
  assert.equal(weekdaysGroup.hidden, true);
  assert.equal(monthDayWrap.hidden, false);
  // Weekdays preserved in draft!
  assert.deepEqual(draft.weekdays, [1, 3]);

  // Switch to daily
  freqSelect.value = "daily";
  freqSelect.dispatchEvent(new dom.window.Event("change"));

  assert.equal(draft.frequency, "daily");
  assert.equal(weekdaysGroup.hidden, true);
  assert.equal(monthDayWrap.hidden, true);
  // Month day preserved in draft!
  assert.equal(draft.month_day, "25");
});

test("isStale guard blocks mutations and onChange calls", () => {
  const draft = makeRecurrenceDraft({
    frequency: "daily",
    interval: 1,
    start_date: "2026-09-07",
    until: "",
    time: "08:00",
    timezone: "UTC",
    weekdays: [0],
    month_day: 1,
    exceptions: "",
    catchup_hours: 24,
  });

  let stale = false;
  let calls = 0;

  const container = document.createElement("div");
  renderRecurrence(container, draft, {
    isStale: () => stale,
    onChange: () => {
      calls++;
    },
  });

  const intervalInput = container.querySelector('[data-recurrence-control="interval"]');
  intervalInput.value = "5";
  intervalInput.dispatchEvent(new dom.window.Event("input"));

  assert.equal(draft.interval, "5");
  assert.equal(calls, 1);

  // Mark stale
  stale = true;
  intervalInput.value = "10";
  intervalInput.dispatchEvent(new dom.window.Event("input"));

  assert.equal(draft.interval, "5", "Draft must not be mutated when stale");
  assert.equal(calls, 1, "onChange must not be called when stale");
});
test("Ancient dates derive the actual Gregorian weekday, offset-only zones are not IANA keys", () => {
  const draft = makeRecurrenceDraft(null,{start_date:"0001-01-01",timezone:"UTC"});
  assert.deepEqual(draft.weekdays,[0]);
  assert.equal(draft.month_day,"1");
  draft.enabled=true;draft.timezone="+01:00";
  assert.throws(()=>recurrencePayload(draft),e=>e.code==="invalid_field"&&e.field==="timezone");
});
