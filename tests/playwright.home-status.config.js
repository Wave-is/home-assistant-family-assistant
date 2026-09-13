import {defineConfig} from "@playwright/test";
import {fileURLToPath} from "node:url";
import base from "../playwright.config.js";

// A bounded independent gate; do not compete with the shared 8329 browser run.
export default defineConfig({...base,
  testDir: "browser", testMatch: "home-status.spec.js",
  use: {...base.use, baseURL: "http://127.0.0.1:8337"},
  webServer: {...base.webServer,
    command: "python -m http.server 8337 --bind 127.0.0.1 --protocol HTTP/1.1",
    cwd: fileURLToPath(new URL("../", import.meta.url)),
    url: "http://127.0.0.1:8337",
  },
});
