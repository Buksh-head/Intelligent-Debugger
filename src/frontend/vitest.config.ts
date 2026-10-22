import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.ts";

// Frontend tests live in tests/frontend at the repo root, next to the backend
// tests. The repo root has its own stray node_modules with a second copy of
// React, so these packages are pinned to this app's copies.
export default mergeConfig(
  viteConfig,
  defineConfig({
    resolve: {
      dedupe: [
        "react",
        "react-dom",
        "react-router-dom",
        "@monaco-editor/react",
        "@testing-library/react",
        "@testing-library/user-event",
      ],
    },
    server: {
      fs: { allow: ["../.."] },
    },
    test: {
      dir: "../../tests/frontend",
      environment: "jsdom",
      // `npm run coverage` writes the report to tests/coverage/frontend, next
      // to the backend report, so both are part of the handover package.
      coverage: {
        provider: "v8",
        include: ["src/**/*.{ts,tsx}"],
        exclude: [
          "src/debugging-assistant-ui/**",
          "src/main.tsx",
          "src/vite-env.d.ts",
        ],
        reporter: ["text", "text-summary", "json-summary", "html"],
        reportsDirectory: "../../tests/coverage/frontend",
      },
    },
  }),
);
