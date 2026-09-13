import { test, expect } from "./control-audit.js";

const FIXTURE_URL = "/tests/fixtures/card-registry.html";

test.beforeEach(async ({ page }) => {
  await page.goto(FIXTURE_URL);
  await page.waitForFunction(() => window.fixtureReady === true);
  await expect(page.locator("#canonical-tasks-card ha-card")).toBeVisible();
  await expect(page.locator("#canonical-alarms-card ha-card")).toBeVisible();
});

test("preloaded legacy custom elements and picker metadata remain untouched", async ({
  page,
}) => {
  const legacyInfo = await page.evaluate(() => {
    const OldTasks = window.LegacyTasksCard;
    const OldAlarms = window.LegacyAlarmsCard;
    const currentTasksCtor = customElements.get("family-tasks-card");
    const currentAlarmsCtor = customElements.get("family-alarms-card");
    const canonicalTasksCtor = customElements.get("family-assistant-tasks-card");
    const canonicalAlarmsCtor = customElements.get("family-assistant-alarms-card");

    return {
      tasksMatchesOld: currentTasksCtor === OldTasks,
      alarmsMatchesOld: currentAlarmsCtor === OldAlarms,
      tasksIsLegacy: currentTasksCtor?.isLegacy === true,
      alarmsIsLegacy: currentAlarmsCtor?.isLegacy === true,
      tasksHasFamilyFlag: currentTasksCtor?.familyAssistantCard === true,
      alarmsHasFamilyFlag: currentAlarmsCtor?.familyAssistantCard === true,
      tasksDifferentFromCanonical: currentTasksCtor !== canonicalTasksCtor,
      alarmsDifferentFromCanonical: currentAlarmsCtor !== canonicalAlarmsCtor,
      customCardsTasksRow: window.customCards.find((r) => r.type === "family-tasks-card"),
      customCardsHasLegacyAlarms: window.customCards.some((r) => r.type === "family-alarms-card"),
    };
  });

  expect(legacyInfo.tasksMatchesOld).toBe(true);
  expect(legacyInfo.alarmsMatchesOld).toBe(true);
  expect(legacyInfo.tasksIsLegacy).toBe(true);
  expect(legacyInfo.alarmsIsLegacy).toBe(true);
  expect(legacyInfo.tasksHasFamilyFlag).toBe(false);
  expect(legacyInfo.alarmsHasFamilyFlag).toBe(false);
  expect(legacyInfo.tasksDifferentFromCanonical).toBe(true);
  expect(legacyInfo.alarmsDifferentFromCanonical).toBe(true);
  expect(legacyInfo.customCardsTasksRow).toEqual({
    type: "family-tasks-card",
    name: "Legacy Tasks",
    description: "Legacy pre-registered tasks card",
    preview: true,
  });
  expect(legacyInfo.customCardsHasLegacyAlarms).toBe(false);

  // Legacy DOM instances render their legacy template without ha-card wrapper
  await expect(page.locator("#legacy-tasks-card .legacy-tasks-marker")).toBeVisible();
  await expect(page.locator("#legacy-alarms-card .legacy-alarms-marker")).toBeVisible();
  await expect(page.locator("#legacy-tasks-card ha-card")).toHaveCount(0);
  await expect(page.locator("#legacy-alarms-card ha-card")).toHaveCount(0);
});

test("canonical tasks and alarms cards register with correct default views and exercise callWS view", async ({
  page,
}) => {
  const cardContracts = await page.evaluate(async () => {
    const { cardView } = await import("/custom_components/family_assistant/frontend/card-registry.js");
    const { COPY } = await import("/custom_components/family_assistant/frontend/family-assistant.js");

    const TasksCtor = customElements.get("family-assistant-tasks-card");
    const AlarmsCtor = customElements.get("family-assistant-alarms-card");
    const tasksCard = window.tasksCard;
    const alarmsCard = window.alarmsCard;

    return {
      tasksDefaultView: TasksCtor.defaultView,
      alarmsDefaultView: AlarmsCtor.defaultView,
      tasksIsFamilyAssistantCard: TasksCtor.familyAssistantCard,
      alarmsIsFamilyAssistantCard: AlarmsCtor.familyAssistantCard,
      tasksStubConfig: TasksCtor.getStubConfig(),
      alarmsStubConfig: AlarmsCtor.getStubConfig(),
      tasksResolvedView: cardView("custom:family-assistant-tasks-card"),
      alarmsResolvedView: cardView("custom:family-assistant-alarms-card"),
      tasksCardInstanceView: tasksCard._view,
      alarmsCardInstanceView: alarmsCard._view,
      expectedTasksTitle: COPY.en.tasks,
      expectedAlarmsTitle: COPY.en.alarms,
      wsViewCalls: window.calls.filter((c) => c.type === "family_assistant/view").length,
    };
  });

  expect(cardContracts.tasksDefaultView).toBe("tasks");
  expect(cardContracts.alarmsDefaultView).toBe("alarms");
  expect(cardContracts.tasksIsFamilyAssistantCard).toBe(true);
  expect(cardContracts.alarmsIsFamilyAssistantCard).toBe(true);
  expect(cardContracts.tasksStubConfig).toEqual({ view: "tasks" });
  expect(cardContracts.alarmsStubConfig).toEqual({ view: "alarms" });
  expect(cardContracts.tasksResolvedView).toBe("tasks");
  expect(cardContracts.alarmsResolvedView).toBe("alarms");
  expect(cardContracts.tasksCardInstanceView).toBe("tasks");
  expect(cardContracts.alarmsCardInstanceView).toBe("alarms");
  expect(cardContracts.wsViewCalls).toBeGreaterThanOrEqual(2);

  // Validate that card headers match actual frontend contract definitions
  await expect(page.locator("#canonical-tasks-card h2")).toHaveText(
    cardContracts.expectedTasksTitle,
  );
  await expect(page.locator("#canonical-alarms-card h2")).toHaveText(
    cardContracts.expectedAlarmsTitle,
  );
});

test("card editor resolves correct default views from frontend contracts", async ({
  page,
}) => {
  const editorViewSelect = page.locator('#card-editor select[name="view"]');

  // Initial config uses custom:family-assistant-tasks-card
  await expect(editorViewSelect).toHaveValue("tasks");

  // Reconfigure with canonical alarms card
  await page.evaluate(() => {
    window.editor.setConfig({ type: "custom:family-assistant-alarms-card" });
  });
  await expect(editorViewSelect).toHaveValue("alarms");

  // Legacy task alias resolves to tasks default view
  await page.evaluate(() => {
    window.editor.setConfig({ type: "custom:family-tasks-card" });
  });
  await expect(editorViewSelect).toHaveValue("tasks");

  // Legacy alarm alias resolves to alarms default view
  await page.evaluate(() => {
    window.editor.setConfig({ type: "custom:family-alarms-card" });
  });
  await expect(editorViewSelect).toHaveValue("alarms");

  // Verify all canonical views from card-registry contract configure editor view select correctly
  const allViewsEditorCheck = await page.evaluate(async () => {
    const { CARD_VIEWS } = await import("/custom_components/family_assistant/frontend/card-registry.js");
    const editor = window.editor;
    const results = [];
    for (const [view, suffix] of CARD_VIEWS) {
      const type = view === "today" ? "family-assistant-card" : `family-assistant-${suffix}-card`;
      editor.setConfig({ type: `custom:${type}` });
      const select = editor.shadowRoot.querySelector('[name="view"]');
      results.push({ view, type, actualValue: select?.value });
    }
    return results;
  });

  for (const item of allViewsEditorCheck) {
    expect(item.actualValue).toBe(item.view);
  }
});

test("safe text rendering strictly prevents script execution and HTML injection", async ({
  page,
}) => {
  // Global script execution probes must remain undefined
  const injectionExecuted = await page.evaluate(() => ({
    taskScript: window.injectedTaskScript,
    alarmScript: window.injectedAlarmScript,
  }));
  expect(injectionExecuted.taskScript).toBeUndefined();
  expect(injectionExecuted.alarmScript).toBeUndefined();

  // Injected probe elements must not exist in shadow DOM
  const tasksCard = page.locator("#canonical-tasks-card");
  const alarmsCard = page.locator("#canonical-alarms-card");
  await expect(tasksCard.locator(".injected-probe")).toHaveCount(0);
  await expect(alarmsCard.locator(".injected-alarm-probe")).toHaveCount(0);
  await expect(alarmsCard.locator("img")).toHaveCount(0);

  // Literal probe strings must be safely escaped and displayed as text content
  const taskTitleText = await page.evaluate(() => window.fixture.tasks[0].title);
  const alarmNameText = await page.evaluate(() => window.fixture.alarms[0].name);
  await expect(tasksCard.locator("strong").first()).toHaveText(taskTitleText);
  await expect(alarmsCard.locator("strong").first()).toHaveText(alarmNameText);
});

test("card picker rows are canonical and reflect frontend contracts", async ({
  page,
}) => {
  const pickerEvaluation = await page.evaluate(async () => {
    const { CARD_VIEWS } = await import("/custom_components/family_assistant/frontend/card-registry.js");
    const { COPY } = await import("/custom_components/family_assistant/frontend/family-assistant.js");

    const cards = window.customCards;
    const newCards = cards.filter((c) => c.type !== "family-tasks-card");

    const allNewCanonical = newCards.every((c) => c.type.startsWith("family-assistant-"));
    const noLegacyAlarms = !cards.some((c) => c.type === "family-alarms-card");

    const types = cards.map((c) => c.type);
    const hasDuplicates = new Set(types).size !== types.length;

    const viewsVerified = CARD_VIEWS.map(([view, suffix]) => {
      const canonicalType =
        view === "today" ? "family-assistant-card" : `family-assistant-${suffix}-card`;
      const entry = cards.find((c) => c.type === canonicalType);
      const expectedLabel = COPY.en[view];
      return {
        view,
        canonicalType,
        found: !!entry,
        nameExact: entry?.name === `Family Assistant · ${expectedLabel}`,
        descExact: entry?.description === expectedLabel,
        preview: entry?.preview === true,
      };
    });

    return {
      allNewCanonical,
      noLegacyAlarms,
      hasDuplicates,
      viewsVerified,
      totalCards: cards.length,
      expectedTotal: CARD_VIEWS.length + 1,
    };
  });

  expect(pickerEvaluation.allNewCanonical).toBe(true);
  expect(pickerEvaluation.noLegacyAlarms).toBe(true);
  expect(pickerEvaluation.hasDuplicates).toBe(false);
  expect(pickerEvaluation.totalCards).toBe(pickerEvaluation.expectedTotal);

  for (const row of pickerEvaluation.viewsVerified) {
    expect(row.found).toBe(true);
    expect(row.nameExact).toBe(true);
    expect(row.descExact).toBe(true);
    expect(row.preview).toBe(true);
  }
});

test("unoccupied legacy aliases work for dashboards but are not advertised in picker", async ({
  page,
}) => {
  const unoccupiedEvaluation = await page.evaluate(async () => {
    const { cardView } = await import("/custom_components/family_assistant/frontend/card-registry.js");

    const ShoppingCard = customElements.get("family-shopping-card");
    const isAdvertised = window.customCards.some((c) => c.type === "family-shopping-card");
    const stub = ShoppingCard?.getStubConfig?.();
    const resolvedView = cardView("custom:family-shopping-card");

    const elem = document.createElement("family-shopping-card");
    elem.setConfig({ type: "custom:family-shopping-card", entry_id: "synthetic-household" });

    return {
      hasShoppingCard: !!ShoppingCard,
      stubConfig: stub,
      isAdvertised,
      resolvedView,
      elementView: elem._view,
    };
  });

  expect(unoccupiedEvaluation.hasShoppingCard).toBe(true);
  expect(unoccupiedEvaluation.stubConfig).toEqual({ view: "shopping" });
  expect(unoccupiedEvaluation.isAdvertised).toBe(false);
  expect(unoccupiedEvaluation.resolvedView).toBe("shopping");
  expect(unoccupiedEvaluation.elementView).toBe("shopping");
});

test("repeated registration preserves constructors and prevents duplicate picker rows", async ({
  page,
}) => {
  const repeatEvaluation = await page.evaluate(async () => {
    const beforeCount = window.customCards.length;
    const beforeCards = structuredClone(window.customCards);
    const tasksCtorBefore = customElements.get("family-assistant-tasks-card");
    const alarmsCtorBefore = customElements.get("family-assistant-alarms-card");
    const legacyTasksCtorBefore = customElements.get("family-tasks-card");
    const legacyAlarmsCtorBefore = customElements.get("family-alarms-card");

    await import("/custom_components/family_assistant/frontend/family-assistant.js?repeat-test");

    const afterCount = window.customCards.length;
    const tasksCtorAfter = customElements.get("family-assistant-tasks-card");
    const alarmsCtorAfter = customElements.get("family-assistant-alarms-card");
    const legacyTasksCtorAfter = customElements.get("family-tasks-card");
    const legacyAlarmsCtorAfter = customElements.get("family-alarms-card");

    return {
      countPreserved: beforeCount === afterCount,
      cardsIdentical: JSON.stringify(beforeCards) === JSON.stringify(window.customCards),
      tasksCtorIdentical: tasksCtorBefore === tasksCtorAfter,
      alarmsCtorIdentical: alarmsCtorBefore === alarmsCtorAfter,
      legacyTasksCtorIdentical: legacyTasksCtorBefore === legacyTasksCtorAfter,
      legacyAlarmsCtorIdentical: legacyAlarmsCtorBefore === legacyAlarmsCtorAfter,
    };
  });

  expect(repeatEvaluation.countPreserved).toBe(true);
  expect(repeatEvaluation.cardsIdentical).toBe(true);
  expect(repeatEvaluation.tasksCtorIdentical).toBe(true);
  expect(repeatEvaluation.alarmsCtorIdentical).toBe(true);
  expect(repeatEvaluation.legacyTasksCtorIdentical).toBe(true);
  expect(repeatEvaluation.legacyAlarmsCtorIdentical).toBe(true);
});
