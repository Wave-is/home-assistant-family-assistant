import {mkdir, writeFile} from "node:fs/promises";
import path from "node:path";

export default class ControlAuditReporter {
  cases = [];
  onTestEnd(test, result) {
    const attachment = result.attachments.find(item => item.name === "frontend-control-audit");
    if (!attachment?.body) return;
    this.cases.push({file: path.relative(process.cwd(), test.location.file).replaceAll("\\", "/"),
      line: test.location.line, title: test.title, status: result.status, retry: result.retry,
      documents: JSON.parse(attachment.body.toString())});
  }
  async onEnd(result) {
    await mkdir("test-results", {recursive: true});
    await writeFile("test-results/frontend-control-audit.json", JSON.stringify({schema_version: 1,
      evidence: "Synthetic Chromium fixtures only. Invoked handlers and fulfilled fixture requests do not prove production/backend/device behavior.",
      status: result.status, cases: this.cases.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line)}, null, 2) + "\n");
  }
}
