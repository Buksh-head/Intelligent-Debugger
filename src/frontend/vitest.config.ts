import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.ts";

// Frontend tests live in tests/frontend at the project root, next to the
// backend tests. They sit outside this app, so these packages are pinned to
// this app's copies.
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
        "axios",
      ],
    },
    server: {
      fs: { allow: ["../.."] },
    },
    test: {
      dir: "../../tests/frontend",
      environment: "jsdom",
      // The Supabase client is created on import; tests replace the login, so
      // any values will do.
      env: {
        VITE_SUPABASE_URL: "http://localhost:54321",
        VITE_SUPABASE_ANON_KEY: "test-anon-key",
      },
      coverage: {
        provider: "v8",
        include: ["src/**/*.{ts,tsx}"],
        exclude: [
          "src/main.tsx",
          "src/vite-env.d.ts",
        ],
        reporter: ["text", "text-summary", "json-summary", "html"],
        reportsDirectory: "coverage",
      },
    },
  }),
);
