/**
 * Pure frontend date/time helper for household IANA timezone operations.
 */

const LOCAL_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;

const ISO_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?(?:Z|([+-])(\d{2}):(\d{2}))$/;

const FORMATTER_CACHE_LIMIT = 16;
const formatterCache = new Map();

function getCachedFormatter(zone) {
  let dtf = formatterCache.get(zone);
  if (!dtf) {
    if (formatterCache.size >= FORMATTER_CACHE_LIMIT) {
      const oldestKey = formatterCache.keys().next().value;
      formatterCache.delete(oldestKey);
    }
    dtf = new Intl.DateTimeFormat("en-US-u-ca-gregory-nu-latn", {
      timeZone: zone,
      hourCycle: "h23",
      year: "numeric",
      era: "short",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
    formatterCache.set(zone, dtf);
  }
  return dtf;
}

function assertValidZone(zone) {
  if (typeof zone !== "string" || !zone.trim()) {
    throw new RangeError(`Invalid IANA time zone: ${zone}`);
  }
  try {
    getCachedFormatter(zone);
  } catch (err) {
    throw new RangeError(`Invalid IANA time zone: ${zone}`);
  }
}

function isLeapYear(year) {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

function daysInMonth(year, month) {
  if (month === 2) {
    return isLeapYear(year) ? 29 : 28;
  }
  if (month === 4 || month === 6 || month === 9 || month === 11) {
    return 30;
  }
  return 31;
}

function parseValidIsoInstant(iso) {
  if (typeof iso !== "string") {
    throw new RangeError(`Invalid ISO timestamp: ${iso}`);
  }
  const match = ISO_PATTERN.exec(iso);
  if (!match) {
    throw new RangeError(`Invalid ISO timestamp format: ${iso}`);
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6] || 0);
  const fractionStr = match[7];
  const offsetSign = match[8];
  const offsetHours = match[9] !== undefined ? Number(match[9]) : undefined;
  const offsetMinutes = match[10] !== undefined ? Number(match[10]) : undefined;

  if (year < 1 || year > 9999) {
    throw new RangeError(`Year out of range (1..9999): ${year}`);
  }
  if (month < 1 || month > 12) {
    throw new RangeError(`Month out of range (1..12): ${month}`);
  }
  const maxDay = daysInMonth(year, month);
  if (day < 1 || day > maxDay) {
    throw new RangeError(`Day out of range for month: ${day}`);
  }
  if (hour < 0 || hour > 23) {
    throw new RangeError(`Hour out of range (0..23): ${hour}`);
  }
  if (minute < 0 || minute > 59) {
    throw new RangeError(`Minute out of range (0..59): ${minute}`);
  }
  if (second < 0 || second > 59) {
    // Leap-seconds (60) and out-of-range seconds are rejected
    throw new RangeError(`Second out of range (0..59): ${second}`);
  }

  let totalOffsetMinutes = 0;
  if (offsetSign !== undefined) {
    if (offsetHours < 0 || offsetHours > 23 || offsetMinutes < 0 || offsetMinutes > 59) {
      throw new RangeError(`Offset out of range: ${offsetHours}:${offsetMinutes}`);
    }
    const offsetMag = offsetHours * 60 + offsetMinutes;
    totalOffsetMinutes = offsetSign === "+" ? offsetMag : -offsetMag;
  }

  const msFraction = fractionStr ? Number((fractionStr + "000").slice(0, 3)) : 0;

  const utcDate = new Date(0);
  utcDate.setUTCFullYear(year, month - 1, day);
  utcDate.setUTCHours(hour, minute, second, msFraction);

  const utcMs = utcDate.getTime() - totalOffsetMinutes * 60 * 1000;
  if (!Number.isFinite(utcMs)) {
    throw new RangeError(`Invalid timestamp instant: ${iso}`);
  }

  const instant = new Date(utcMs);
  if (instant.getUTCFullYear() < 1 || instant.getUTCFullYear() > 9999) {
    throw new RangeError("Instant outside supported calendar");
  }
  return instant;
}

function parseAndValidateLocalParts(local) {
  if (typeof local !== "string") {
    throw new RangeError(`Invalid local time string: ${local}`);
  }
  const match = LOCAL_PATTERN.exec(local);
  if (!match) {
    throw new RangeError(`Invalid local time string format: ${local}`);
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);

  if (year < 1 || year > 9999) {
    throw new RangeError(`Year out of range (1..9999): ${year}`);
  }
  if (month < 1 || month > 12) {
    throw new RangeError(`Invalid month in local time: ${local}`);
  }
  const maxDay = daysInMonth(year, month);
  if (day < 1 || day > maxDay) {
    throw new RangeError(`Invalid day for month in local time: ${local}`);
  }
  if (hour < 0 || hour > 23) {
    throw new RangeError(`Invalid hour in local time: ${local}`);
  }
  if (minute < 0 || minute > 59) {
    throw new RangeError(`Invalid minute in local time: ${local}`);
  }

  return { year, month, day, hour, minute };
}

function getZonedParts(date, zone) {
  const dtf = getCachedFormatter(zone);
  const parts = dtf.formatToParts(date);
  let year = "";
  let month = "";
  let day = "";
  let hour = "";
  let minute = "";
  let second = "";
  let era = "";

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    switch (part.type) {
      case "era":
        era = part.value;
        break;
      case "year":
        year = part.value;
        break;
      case "month":
        month = part.value;
        break;
      case "day":
        day = part.value;
        break;
      case "hour":
        hour = part.value;
        break;
      case "minute":
        minute = part.value;
        break;
      case "second":
        second = part.value;
        break;
    }
  }

  return {
    year: era === "BC" ? 1 - Number(year) : Number(year),
    month: Number(month),
    day: Number(day),
    hour: Number(hour),
    minute: Number(minute),
    second: Number(second),
    formatted: `${year.padStart(4, "0")}-${month.padStart(2, "0")}-${day.padStart(2, "0")}T${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`
  };
}

export function wallTime(iso, zone) {
  assertValidZone(zone);
  const date = parseValidIsoInstant(iso);
  const parts = getZonedParts(date, zone);
  if (parts.year < 1 || parts.year > 9999) throw new RangeError("Local date outside supported calendar");
  return parts.formatted;
}

export function wallTimeCandidates(local, zone) {
  assertValidZone(zone);
  const { year, month, day, hour, minute } = parseAndValidateLocalParts(local);

  const anchorDate = new Date(0);
  anchorDate.setUTCFullYear(year, month - 1, day);
  anchorDate.setUTCHours(hour, minute, 0, 0);
  const targetWallUtcMs = anchorDate.getTime();

  const offsets = new Set();
  const stepMs = 15 * 60 * 1000;
  const startMs = targetWallUtcMs - 36 * 60 * 60 * 1000;
  const endMs = targetWallUtcMs + 36 * 60 * 60 * 1000;

  for (let t = startMs; t <= endMs; t += stepMs) {
    const d = new Date(t);
    const zParts = getZonedParts(d, zone);
    const zWallDate = new Date(0);
    zWallDate.setUTCFullYear(zParts.year, zParts.month - 1, zParts.day);
    zWallDate.setUTCHours(zParts.hour, zParts.minute, zParts.second, 0);
    const offsetMs = zWallDate.getTime() - t;
    offsets.add(offsetMs);
  }

  const matchingTimestamps = [];

  for (const offsetMs of offsets) {
    const candidateUtcMs = targetWallUtcMs - offsetMs;
    // Discard any fractional seconds/milliseconds to ensure exact second=0 check
    if (candidateUtcMs % 1000 !== 0) {
      continue;
    }
    const candidateDate = new Date(candidateUtcMs);
    if (candidateDate.getUTCFullYear() < 1 || candidateDate.getUTCFullYear() > 9999) continue;
    const parts = getZonedParts(candidateDate, zone);

    if (
      parts.year === year &&
      parts.month === month &&
      parts.day === day &&
      parts.hour === hour &&
      parts.minute === minute &&
      parts.second === 0
    ) {
      matchingTimestamps.push(candidateUtcMs);
    }
  }

  matchingTimestamps.sort((a, b) => a - b);
  const uniqueTimestamps = [...new Set(matchingTimestamps)];

  return uniqueTimestamps.map((ms) => new Date(ms).toISOString());
}
