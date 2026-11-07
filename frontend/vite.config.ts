import { defineConfig } from "vitest/config";
const proxy = {
  "/api": {
    target: process.env.DASHBOARD_GATEWAY_ORIGIN || "http://127.0.0.1:8010",
    changeOrigin: false,
  },
};
export default defineConfig({
  server: { port: 3000, strictPort: true, proxy },
  preview: { port: 3000, strictPort: true, proxy },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
  build: { sourcemap: false },
});
