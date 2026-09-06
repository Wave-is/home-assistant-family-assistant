import {defineConfig} from "@playwright/test";
export default defineConfig({
  testDir:"tests/browser",timeout:30000,fullyParallel:true,
  use:{baseURL:"http://127.0.0.1:8329",headless:true,
    channel:process.env.CI?undefined:"chrome",screenshot:"only-on-failure"},
  webServer:{command:"python -m http.server 8329 --bind 127.0.0.1",url:"http://127.0.0.1:8329",reuseExistingServer:false},
});

