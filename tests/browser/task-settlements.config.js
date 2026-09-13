import {defineConfig} from "@playwright/test";
import {fileURLToPath} from "node:url";
// Standalone focused runner; coordinate port ownership with the integrator.
const root = fileURLToPath(new URL("../../", import.meta.url));
const python = process.env.TASK_SETTLEMENTS_PYTHON || "python";
export default defineConfig({
  testDir: ".", testMatch: "task-settlements.spec.js", timeout:30000, fullyParallel:true,
  use:{baseURL:"http://127.0.0.1:8329",headless:true,channel:process.env.CI?undefined:"chrome",screenshot:"only-on-failure"},
  webServer:{command:`"${python}" -m http.server 8329 --bind 127.0.0.1 --protocol HTTP/1.1`,cwd:root,url:"http://127.0.0.1:8329",reuseExistingServer:false},
});
