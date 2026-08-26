import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          flow: ["@xyflow/react"],
          graph: ["cytoscape"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/testSetup.ts",
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/testSetup.ts", "src/vite-env.d.ts", "src/types.ts"],
      // Line and statement coverage are the user-visible contract.  Function
      // and branch thresholds account for framework callbacks (React Flow and
      // Cytoscape) that cannot be deterministically driven in jsdom.
      thresholds: { lines: 85, functions: 65, statements: 85, branches: 75 }
    }
  }
});
