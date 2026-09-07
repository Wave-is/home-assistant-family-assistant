import {defineConfig} from "@playwright/test";
export default defineConfig({
  testDir:"tests/browser",timeout:30000,fullyParallel:true,
  use:{baseURL:"http://127.0.0.1:8329",headless:true,
    channel:process.env.CI?undefined:"chrome",screenshot:"only-on-failure"},
  // Keep module requests on persistent connections. HTTP/1.0 creates one new
  // loopback socket per module and can exhaust Windows socket buffers in a full run.
  webServer:{command:"python -m http.server 8329 --bind 127.0.0.1 --protocol HTTP/1.1",url:"http://127.0.0.1:8329",reuseExistingServer:false},
});
