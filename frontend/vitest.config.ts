import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/** Component tests run in jsdom. The @ alias matches tsconfig so imports read the same as in the app. */
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost:3000/dashboard" } },
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    setupFiles: ["tests/unit/setup.ts"],
  },
});
