import assert from "node:assert/strict";
import { test } from "node:test";
import { wallTime, wallTimeCandidates } from "../custom_components/family_assistant/frontend/local-time.js";

test("wallTime: converts UTC ISO to local wall time format YYYY-MM-DDTHH:mm", () => {
  // UTC
  assert.equal(wallTime("2025-01-15T12:30:00Z", "UTC"), "2025-01-15T12:30");
  assert.equal(wallTime("2025-01-15T12:30:00.000Z", "UTC"), "2025-01-15T12:30");
  // Fractional seconds up to 6 digits (microseconds)
  assert.equal(wallTime("2025-01-15T12:30:00.123456Z", "UTC"), "2025-01-15T12:30");

  // Europe/Kyiv (EET: UTC+2 in winter, EEST: UTC+3 in summer)
  assert.equal(wallTime("2025-01-15T12:00:00Z", "Europe/Kyiv"), "2025-01-15T14:00");
  assert.equal(wallTime("2025-07-15T12:00:00Z", "Europe/Kyiv"), "2025-07-15T15:00");

  // Input ISO with explicit offset normalizes correctly
  assert.equal(wallTime("2025-01-15T15:00:00+03:00", "Europe/Kyiv"), "2025-01-15T14:00");
  assert.equal(wallTime("2025-01-15T07:00:00-05:00", "UTC"), "2025-01-15T12:00");
});

test("wallTime: supports half-hour and 45-minute zones", () => {
  assert.equal(wallTime("2025-01-15T12:30Z", "UTC"), "2025-01-15T12:30");
  // Asia/Kathmandu (UTC+05:45)
  assert.equal(wallTime("2025-01-15T12:00:00Z", "Asia/Kathmandu"), "2025-01-15T17:45");

  // Pacific/Chatham (standard UTC+12:45, DST UTC+13:45)
  // In January (Southern hemisphere summer), Chatham is in DST UTC+13:45
  assert.equal(wallTime("2025-01-15T00:00:00Z", "Pacific/Chatham"), "2025-01-15T13:45");
  // In July (winter), Chatham is standard UTC+12:45
  assert.equal(wallTime("2025-07-15T00:00:00Z", "Pacific/Chatham"), "2025-07-15T12:45");

  // Australia/Lord_Howe (standard UTC+10:30, DST UTC+11:00 - 30-minute DST jump!)
  // In January (summer, DST UTC+11:00)
  assert.equal(wallTime("2025-01-15T00:00:00Z", "Australia/Lord_Howe"), "2025-01-15T11:00");
  // In July (winter, standard UTC+10:30)
  assert.equal(wallTime("2025-07-15T00:00:00Z", "Australia/Lord_Howe"), "2025-07-15T10:30");
});

test("calendar bounds survive offset conversion and era formatting", () => {
  for (const iso of ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:00-01:00",
    "2025-01-01T00:00:00+24:00", "2025-01-01T00:00:00+02:60",
    "2025-01-01T00:00:00.1234567Z", "2025-01-01T00:00.123Z"]) {
    assert.throws(() => wallTime(iso, "UTC"), RangeError);
  }
  assert.throws(() => wallTime("0001-01-01T00:00:00Z", "Etc/GMT+1"), RangeError);
  assert.throws(() => wallTime("9999-12-31T23:59:00Z", "Etc/GMT-1"), RangeError);
  assert.deepEqual(wallTimeCandidates("0001-01-01T00:00", "Etc/GMT-1"), []);
  assert.deepEqual(wallTimeCandidates("9999-12-31T23:59", "Etc/GMT+1"), []);
});

test("wallTime: validates ISO grammar, rejects naive, date-only, rollover, leap-second, year 0000", () => {
  // Invalid string formats
  assert.throws(() => wallTime("invalid-date", "UTC"), RangeError);
  assert.throws(() => wallTime("", "UTC"), RangeError);
  assert.throws(() => wallTime(null, "UTC"), RangeError);
  assert.throws(() => wallTime(123456, "UTC"), RangeError);

  // Naive strings without explicit Z or +/-HH:MM must be rejected
  assert.throws(() => wallTime("2025-01-15T12:00:00", "UTC"), RangeError);
  assert.throws(() => wallTime("2025-01-15 12:00:00", "UTC"), RangeError);

  // Date-only strings rejected
  assert.throws(() => wallTime("2025-01-15", "UTC"), RangeError);

  // Rollover dates rejected
  assert.throws(() => wallTime("2025-02-30T12:00:00Z", "UTC"), RangeError);
  assert.throws(() => wallTime("2025-04-31T12:00:00Z", "UTC"), RangeError);
  assert.throws(() => wallTime("2025-02-29T12:00:00Z", "UTC"), RangeError); // 2025 not leap year
  assert.throws(() => wallTime("2025-13-01T12:00:00Z", "UTC"), RangeError);
  assert.throws(() => wallTime("2025-00-01T12:00:00Z", "UTC"), RangeError);
  assert.throws(() => wallTime("2025-01-00T12:00:00Z", "UTC"), RangeError);
  assert.throws(() => wallTime("2025-01-32T12:00:00Z", "UTC"), RangeError);

  // Leap seconds (second=60) rejected
  assert.throws(() => wallTime("2016-12-31T23:59:60Z", "UTC"), RangeError);

  // Year 0000 rejected
  assert.throws(() => wallTime("0000-01-01T12:00:00Z", "UTC"), RangeError);

  // Invalid zones
  assert.throws(() => wallTime("2025-01-15T12:00:00Z", "Invalid/Timezone"), RangeError);
  assert.throws(() => wallTime("2025-01-15T12:00:00Z", ""), RangeError);
  assert.throws(() => wallTime("2025-01-15T12:00:00Z", null), RangeError);
});

test("wallTime & wallTimeCandidates: safe handling of years 1..99", () => {
  // Test early 2-digit years
  const isoYear50 = "0050-06-15T12:00:00Z";
  assert.equal(wallTime(isoYear50, "UTC"), "0050-06-15T12:00");
  assert.deepEqual(
    wallTimeCandidates("0050-06-15T12:00", "UTC"),
    ["0050-06-15T12:00:00.000Z"]
  );

  const isoYear01 = "0001-01-01T00:00:00Z";
  assert.equal(wallTime(isoYear01, "UTC"), "0001-01-01T00:00");
  assert.deepEqual(
    wallTimeCandidates("0001-01-01T00:00", "UTC"),
    ["0001-01-01T00:00:00.000Z"]
  );
});

test("wallTime & wallTimeCandidates: historical fractional-minute offsets", () => {
  // Europe/Paris had historical LMT offset of +00:09:21 until 1911.
  // In 1900, Paris was UTC+00:09:21 (or +9m).
  const c1900 = wallTimeCandidates("1900-01-01T12:00", "Europe/Paris");
  assert.equal(c1900.length, 1);
  assert.equal(wallTime(c1900[0], "Europe/Paris"), "1900-01-01T12:00");
});

test("wallTimeCandidates: Samoa skipped 2011-12-30", () => {
  // Pacific/Apia crossed the International Date Line by skipping entire day 2011-12-30.
  // The local calendar jumped from 2011-12-29 23:59 directly to 2011-12-31 00:00.
  // Therefore, 2011-12-30 never existed in Pacific/Apia.
  assert.deepEqual(wallTimeCandidates("2011-12-30T10:00", "Pacific/Apia"), []);
  assert.deepEqual(wallTimeCandidates("2011-12-30T00:00", "Pacific/Apia"), []);
  assert.deepEqual(wallTimeCandidates("2011-12-30T23:59", "Pacific/Apia"), []);
});

test("wallTimeCandidates: normal unambiguous times return exactly one ISO UTC candidate", () => {
  assert.deepEqual(
    wallTimeCandidates("2025-01-15T14:00", "Europe/Kyiv"),
    ["2025-01-15T12:00:00.000Z"]
  );
  assert.deepEqual(
    wallTimeCandidates("2025-01-15T12:30", "UTC"),
    ["2025-01-15T12:30:00.000Z"]
  );
  assert.deepEqual(
    wallTimeCandidates("2025-01-15T17:45", "Asia/Kathmandu"),
    ["2025-01-15T12:00:00.000Z"]
  );
});

test("wallTimeCandidates: DST spring forward gap returns empty array []", () => {
  // Europe/Berlin spring forward 2025: Sunday, March 30, 2025 at 02:00 clocks jump to 03:00 (UTC+1 to UTC+2).
  // Times between 02:00 and 02:59 do not exist on wall clock.
  assert.deepEqual(wallTimeCandidates("2025-03-30T02:30", "Europe/Berlin"), []);

  // America/New_York spring forward 2025: Sunday, March 9, 2025 at 02:00 clocks jump to 03:00 (UTC-5 to UTC-4).
  // Times between 02:00 and 02:59 do not exist on wall clock.
  assert.deepEqual(wallTimeCandidates("2025-03-09T02:15", "America/New_York"), []);
});

test("wallTimeCandidates: DST autumn fold returns BOTH candidates sorted in chronological order", () => {
  // Europe/Berlin autumn transition 2025: Sunday, October 26, 2025 at 03:00 clocks jump back to 02:00 (UTC+2 to UTC+1).
  // 02:30 happens first at UTC+2 (00:30 UTC), then again at UTC+1 (01:30 UTC).
  assert.deepEqual(
    wallTimeCandidates("2025-10-26T02:30", "Europe/Berlin"),
    ["2025-10-26T00:30:00.000Z", "2025-10-26T01:30:00.000Z"]
  );

  // America/New_York autumn transition 2025: Sunday, November 2, 2025 at 02:00 clocks jump back to 01:00 (EDT UTC-4 to EST UTC-5).
  // 01:30 happens first at EDT UTC-4 (05:30 UTC), then at EST UTC-5 (06:30 UTC).
  assert.deepEqual(
    wallTimeCandidates("2025-11-02T01:30", "America/New_York"),
    ["2025-11-02T05:30:00.000Z", "2025-11-02T06:30:00.000Z"]
  );
});

test("wallTimeCandidates: Lord Howe Island 30-minute DST transition", () => {
  // Australia/Lord_Howe spring forward 2025: Sunday, October 5, 2025 at 02:00 -> 02:30 (+10:30 to +11:00)
  // 02:15 does not exist
  assert.deepEqual(wallTimeCandidates("2025-10-05T02:15", "Australia/Lord_Howe"), []);
  // 02:30 exists once (at +11:00)
  assert.deepEqual(
    wallTimeCandidates("2025-10-05T02:30", "Australia/Lord_Howe"),
    ["2025-10-04T15:30:00.000Z"]
  );

  // Australia/Lord_Howe autumn fold 2025: Sunday, April 6, 2025 at 02:00 -> 01:30 (+11:00 to +10:30)
  // 01:45 occurs twice: first at +11:00 (14:45 UTC prev day), then at +10:30 (15:15 UTC prev day)
  assert.deepEqual(
    wallTimeCandidates("2025-04-06T01:45", "Australia/Lord_Howe"),
    ["2025-04-05T14:45:00.000Z", "2025-04-05T15:15:00.000Z"]
  );
});

test("wallTimeCandidates: Chatham 45-minute DST transitions", () => {
  // Pacific/Chatham autumn fold 2025: Sunday, April 6, 2025 at 03:45 -> 02:45 (+13:45 to +12:45)
  // 03:00 occurs twice: first at +13:45 (13:15 UTC prev day), then at +12:45 (14:15 UTC prev day)
  assert.deepEqual(
    wallTimeCandidates("2025-04-06T03:00", "Pacific/Chatham"),
    ["2025-04-05T13:15:00.000Z", "2025-04-05T14:15:00.000Z"]
  );
});

test("wallTimeCandidates: validates exact format, Gregorian calendar, leap days, ranges, rejects year 0000", () => {
  // Invalid strings & precision
  assert.throws(() => wallTimeCandidates("2025-01-15", "UTC"), RangeError);
  assert.throws(() => wallTimeCandidates("2025-01-15T12:00:00", "UTC"), RangeError);
  assert.throws(() => wallTimeCandidates("2025-01-15T12:00:00Z", "UTC"), RangeError);
  assert.throws(() => wallTimeCandidates("2025-1-15T12:00", "UTC"), RangeError);
  assert.throws(() => wallTimeCandidates("not-a-date", "UTC"), RangeError);
  assert.throws(() => wallTimeCandidates(null, "UTC"), RangeError);

  // Year 0000 rejected (Python HA / ISO component bound 1..9999)
  assert.throws(() => wallTimeCandidates("0000-01-01T12:00", "UTC"), RangeError);

  // Invalid calendar dates
  assert.throws(() => wallTimeCandidates("2025-02-29T12:00", "UTC"), RangeError); // 2025 is not a leap year
  assert.throws(() => wallTimeCandidates("2025-04-31T12:00", "UTC"), RangeError); // April has 30 days
  assert.throws(() => wallTimeCandidates("2025-13-01T12:00", "UTC"), RangeError); // Month 13
  assert.throws(() => wallTimeCandidates("2025-00-01T12:00", "UTC"), RangeError); // Month 0
  assert.throws(() => wallTimeCandidates("2025-01-00T12:00", "UTC"), RangeError); // Day 0
  assert.throws(() => wallTimeCandidates("2025-01-32T12:00", "UTC"), RangeError); // Day 32

  // Hours / Minutes
  assert.throws(() => wallTimeCandidates("2025-01-15T24:00", "UTC"), RangeError); // Hour 24
  assert.throws(() => wallTimeCandidates("2025-01-15T-1:00", "UTC"), RangeError);
  assert.throws(() => wallTimeCandidates("2025-01-15T12:60", "UTC"), RangeError); // Minute 60

  // Valid leap day
  assert.deepEqual(
    wallTimeCandidates("2024-02-29T12:00", "UTC"),
    ["2024-02-29T12:00:00.000Z"]
  );

  // Invalid zone
  assert.throws(() => wallTimeCandidates("2025-01-15T12:00", "Invalid/Zone"), RangeError);
  assert.throws(() => wallTimeCandidates("2025-01-15T12:00", ""), RangeError);
  assert.throws(() => wallTimeCandidates("2025-01-15T12:00", null), RangeError);
});

test("process TZ independence: changing process.env.TZ produces identical outputs", () => {
  const originalTZ = process.env.TZ;
  try {
    const testZones = ["UTC", "Pacific/Honolulu", "Asia/Tokyo", "Europe/London", "America/Santiago"];
    for (const testTz of testZones) {
      process.env.TZ = testTz;

      // Europe/Kyiv wallTime
      assert.equal(wallTime("2025-01-15T12:00:00Z", "Europe/Kyiv"), "2025-01-15T14:00");
      // Europe/Berlin fold
      assert.deepEqual(
        wallTimeCandidates("2025-10-26T02:30", "Europe/Berlin"),
        ["2025-10-26T00:30:00.000Z", "2025-10-26T01:30:00.000Z"]
      );
      // New York gap
      assert.deepEqual(wallTimeCandidates("2025-03-09T02:15", "America/New_York"), []);
      // Lord Howe half-hour
      assert.deepEqual(
        wallTimeCandidates("2025-04-06T01:45", "Australia/Lord_Howe"),
        ["2025-04-05T14:45:00.000Z", "2025-04-05T15:15:00.000Z"]
      );
    }
  } finally {
    if (originalTZ === undefined) {
      delete process.env.TZ;
    } else {
      process.env.TZ = originalTZ;
    }
  }
});

test("roundtrip verification: wallTime(candidate, zone) === local", () => {
  const zones = [
    "UTC",
    "Europe/Kyiv",
    "Europe/Berlin",
    "America/New_York",
    "Asia/Kathmandu",
    "Australia/Lord_Howe",
    "Pacific/Chatham"
  ];
  const testLocals = [
    "2025-01-01T00:00",
    "2025-06-15T12:30",
    "2025-12-31T23:59"
  ];

  for (const zone of zones) {
    for (const local of testLocals) {
      const candidates = wallTimeCandidates(local, zone);
      assert.ok(candidates.length >= 1, `Must have candidate for ${local} in ${zone}`);
      for (const iso of candidates) {
        assert.equal(wallTime(iso, zone), local);
      }
    }
  }
});
