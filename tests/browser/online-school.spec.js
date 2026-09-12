import { test, expect } from "@playwright/test";
import { ONLINE_SCHOOL_COPY } from "../../custom_components/family_assistant/frontend/online-school-copy.js";

const NOW = new Date("2026-09-14T21:30:00Z"); // 15 September in the source timezone.
const TEXT = {
  en: { school: "Fictional school", subject: "Science", topic: "States of matter", homework: "Read pages 12–14.\nPrepare two questions; do not submit them yet.", cancelled: "Art workshop", today: "Today’s reading", absence: "Excused absence", file: "Practice worksheet.pdf" },
  ru: { school: "Учебная школа", subject: "Естествознание", topic: "Состояния вещества", homework: "Прочитать страницы 12–14.\nПодготовить два вопроса; пока не отправлять.", cancelled: "Творческая мастерская", today: "Чтение на сегодня", absence: "Уважительная причина", file: "Лист для самостоятельной работы.pdf" },
  uk: { school: "Навчальна школа", subject: "Природознавство", topic: "Стани речовини", homework: "Прочитати сторінки 12–14.\nПідготувати два запитання; поки не надсилати.", cancelled: "Творча майстерня", today: "Читання на сьогодні", absence: "Поважна причина", file: "Аркуш для самостійної роботи.pdf" },
};

function source(language, { id = "OS1", member = "child" } = {}) {
  const words = TEXT[language];
  return {
    id, revision: 1, member, member_revision: 1, provider: "respublika", student_id: "101",
    label: member === "child" ? words.school : "Sibling-only school", timezone: "Europe/Kyiv",
    enabled: true, status: "online_school_timeout", stale: true, last_success: "2026-09-14T12:00:00Z",
    changes: [{ kind: "homework", at: "2026-09-14T12:00:00Z" }], acknowledgements: {},
    snapshot: {
      student_id: "101", student_name: "Fictional learner", timezone: "Europe/Kyiv",
      source_url: "https://school.example.invalid/daybook/101", coverage_start: "2026-09-14", coverage_end: "2026-09-20",
      lessons: [
        { id: "L-today", date: "2026-09-15", start: "08:00", end: "08:45", subject: words.today, teacher: "Fictional teacher", room: "A",
          topic: "", homework: "Read one paragraph", estimated_minutes: null, cancelled: false, replacement: false, links: [], attachments: [] },
        { id: "L-tomorrow", date: "2026-09-16", start: "09:00", end: "09:45", subject: words.subject, teacher: "Fictional teacher", room: "B",
          topic: words.topic, homework: words.homework, estimated_minutes: 25, cancelled: false, replacement: true,
          links: ["https://resource.example.invalid/" + "chapter-".repeat(24)],
          attachments: [{ id: "F1", name: words.file, ext: "pdf", size: 2048 }] },
        { id: "L-cancelled", date: "2026-09-16", start: "10:00", end: "10:45", subject: words.cancelled, teacher: "Fictional teacher", room: "C",
          topic: "", homework: "", estimated_minutes: null, cancelled: true, replacement: false, links: [], attachments: [] },
      ],
      grades: [
        { id: "G1", date: "2026-09-14", period: "14", subject: words.subject, value: "Н/А", kind: "Practice", comment: "Not assessed" },
        { id: "G2", date: null, period: "Semester", subject: "Art", value: "pass", kind: "Term", comment: "" },
      ],
      absences: [{ id: "A1", date: "2026-09-14", period: "14", subject: words.subject, comment: words.absence }],
    },
  };
}

async function load(page, language, options = {}) {
  await page.goto(`/tests/fixtures/school.html?lang=${language}&actor=${options.actor || "parent"}`);
  await page.waitForFunction(() => window.card?._data?.school);
  await page.evaluate(async ({ sources, member }) => {
    window.fixture.school.online = { sources };
    if (member) window.card._config.member_id = member;
    await window.card.refresh();
    window.card.render();
  }, { sources: options.sources || [source(language)], member: options.member });
  return page.locator("family-school-card").locator(".online-school");
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(NOW);
});

for (const language of ["en", "ru", "uk"]) {
  for (const [device, viewport] of Object.entries({ mobile: { width: 390, height: 844 }, desktop: { width: 1280, height: 1000 } })) {
    test(`Online school keeps literal facts and stale status readable (${language}, ${device})`, async ({ page }, testInfo) => {
      await page.setViewportSize(viewport);
      const externalRequests = [];
      await page.route("https://**", route => { externalRequests.push(route.request().url()); return route.abort(); });
      const panel = await load(page, language);
      const copy = ONLINE_SCHOOL_COPY[language], words = TEXT[language];
      await expect(panel.getByRole("heading", { name: copy.title, exact: true })).toBeVisible();
      await expect(panel).toContainText(copy.stale);
      await expect(panel).toContainText(copy.timeout);
      await expect(panel).toContainText(copy.lastSuccess);
      await expect(panel).toContainText("2026-09-14 – 2026-09-20");
      await expect(panel).toContainText("2026-09-16 · Europe/Kyiv");
      await expect(panel.locator('[data-lesson-id="L-tomorrow"] .online-body').last()).toHaveText(words.homework);
      await expect(panel).toContainText(words.topic);
      await expect(panel).toContainText(copy.minutes.replace("{minutes}", "25"));
      await expect(panel).toContainText(copy.replacement);
      await expect(panel).toContainText(copy.cancelled);
      await expect(panel).toContainText(copy.target);
      await expect(panel).toContainText(words.file);
      await expect(panel).toContainText(copy.filesHint);
      const assignmentLink = panel.locator(".online-assignment-link");
      const fullHref = source(language).snapshot.lessons[1].links[0];
      await expect(assignmentLink).toHaveAttribute("href", fullHref);
      await expect(assignmentLink).toHaveAttribute("title", fullHref);
      expect((await assignmentLink.textContent()).length).toBeLessThanOrEqual(80);
      expect(await assignmentLink.evaluate(link => link.getBoundingClientRect().height <= parseFloat(getComputedStyle(link).lineHeight) * 3 + 1)).toBe(true);
      const gradeDetails = panel.locator("details").filter({ has: page.locator("summary", { hasText: copy.grades }) });
      await gradeDetails.locator("summary").click();
      await expect(gradeDetails).toContainText(`${words.subject} · Н/А`);
      await expect(gradeDetails).toContainText("Semester · Art · pass");
      await expect(gradeDetails).toContainText(copy.literal);
      const absenceDetails = panel.locator("details").filter({ has: page.locator("summary", { hasText: copy.absences }) });
      await absenceDetails.locator("summary").click();
      await expect(absenceDetails).toContainText(words.absence);
      await expect(absenceDetails).not.toContainText(`${words.subject} · 0`);
      await expect(panel.locator("img,iframe,object,script,a[download],input[type=password]")).toHaveCount(0);
      expect(await panel.locator("a").evaluateAll(links => links.every(link => link.protocol === "https:" && link.target === "_blank" && link.rel === "noopener noreferrer" && link.referrerPolicy === "no-referrer"))).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(await panel.evaluate(element => [...element.querySelectorAll(".online-source,.online-lesson")].every(row => row.scrollWidth <= row.clientWidth + 1))).toBe(true);
      await panel.screenshot({ path: testInfo.outputPath(`online-school-${language}-${device}.png`) });
      await panel.getByRole("button", { name: copy.today, exact: true }).click();
      await expect(panel).toContainText("2026-09-15 · Europe/Kyiv");
      await expect(panel).toContainText(words.today);
      await expect(panel.locator('[data-lesson-id="L-tomorrow"]')).toHaveCount(0);
      await panel.getByRole("button", { name: copy.tomorrow, exact: true }).click();
      await expect(panel.locator('[data-lesson-id="L-tomorrow"]')).toBeVisible();
      expect(externalRequests).toEqual([]);
      expect(await page.evaluate(() => window.calls)).toEqual([]);
    });
  }
}

test("Child sees only their source and changed membership clears imported private facts", async ({ page }) => {
  const panel = await load(page, "uk", { actor: "child", sources: [source("uk"), source("uk", { id: "OS2", member: "sibling" })] });
  await expect(panel.locator(".online-source")).toHaveCount(1);
  await expect(panel).not.toContainText("Sibling-only school");
  await page.evaluate(async () => {
    window.fixture.members.find(member => member.id === "child").revision++;
    await window.card.refresh();
  });
  await expect(panel.locator(".online-source")).toHaveCount(0);
  await expect(panel).not.toContainText(TEXT.uk.homework);
  expect(await page.evaluate(() => window.calls)).toEqual([]);
});

test("HTML stays literal and missing coverage does not claim there is no homework", async ({ page }) => {
  const fixtureSource = source("en");
  const literal = '<img src="https://track.example.invalid/pixel" onerror="alert(1)">';
  fixtureSource.snapshot.lessons[1].homework = literal;
  fixtureSource.snapshot.lessons[1].links.push("javascript:alert(1)", "https://school.example.invalid/?token=synthetic");
  const externalRequests = [];
  await page.route("https://**", route => { externalRequests.push(route.request().url()); return route.abort(); });
  const panel = await load(page, "en", { sources: [fixtureSource] });
  await expect(panel.locator('[data-lesson-id="L-tomorrow"] .online-body').last()).toHaveText(literal);
  await expect(panel.locator("img,script,iframe,a[href^=javascript]")).toHaveCount(0);
  await expect(panel.locator('a[href*="token="]')).toHaveCount(0);
  await page.evaluate(async () => {
    window.fixture.school.online.sources[0].snapshot.coverage_end = "2026-09-15";
    await window.card.refresh();
  });
  await expect(panel).toContainText(ONLINE_SCHOOL_COPY.en.outside);
  await expect(panel).not.toContainText(ONLINE_SCHOOL_COPY.en.emptyDay);
  await expect(panel).not.toContainText(ONLINE_SCHOOL_COPY.en.noHomework);
  expect(externalRequests).toEqual([]);
  expect(await page.evaluate(() => window.calls)).toEqual([]);
});
