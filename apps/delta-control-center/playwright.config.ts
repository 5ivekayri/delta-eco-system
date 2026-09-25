import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  use: {baseURL: process.env.DELTA_UI_URL || 'http://127.0.0.1:5173', channel: 'chrome', viewport: {width:1366,height:768}},
});
