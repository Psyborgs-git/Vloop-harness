import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";
import { readdirSync, existsSync } from "fs";

// Auto-discover component entries from src/components/*/main.tsx
function discoverEntries(): Record<string, string> {
  const componentsDir = resolve(__dirname, "src/components");
  const entries: Record<string, string> = {};

  if (!existsSync(componentsDir)) return entries;

  for (const name of readdirSync(componentsDir, { withFileTypes: true })) {
    if (!name.isDirectory()) continue;
    const main = resolve(componentsDir, name.name, "main.tsx");
    if (existsSync(main)) {
      entries[name.name] = main;
    }
  }
  return entries;
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@harness": resolve(__dirname, "src/harness"),
    },
  },
  build: {
    rollupOptions: {
      input: {
        root: resolve(__dirname, "src/components/root/main.tsx"),
        ...discoverEntries(),
      },
    },
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    cors: true,
  },
});
