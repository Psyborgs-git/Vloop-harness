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
        ...discoverEntries(),
        index: resolve(__dirname, "index.html"),
        control_pane: resolve(__dirname, "control-pane.html"),
      },
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            const parts = id.replace(/\\/g, "/").split("/node_modules/");
            const packagePath = parts[parts.length - 1];
            if (!packagePath) return;

            let packageName = "";
            if (packagePath.startsWith("@")) {
              const subParts = packagePath.split("/");
              if (subParts.length >= 2) {
                packageName = `${subParts[0]}/${subParts[1]}`;
              } else {
                packageName = subParts[0];
              }
            } else {
              packageName = packagePath.split("/")[0];
            }

            if (packageName.startsWith("@mui") || packageName.startsWith("@emotion")) {
              return "vendor-mui";
            }
            if (packageName === "react-syntax-highlighter") {
              return "vendor-syntax-highlighter";
            }
            if (packageName === "lucide-react") {
              return "vendor-icons";
            }
            if (packageName.startsWith("@connectrpc") || packageName.startsWith("@bufbuild") || packageName === "protobufjs") {
              return "vendor-connect-grpc";
            }
            if (packageName.startsWith("@xterm")) {
              return "vendor-xterm";
            }
            if (
              packageName === "react" ||
              packageName === "react-dom" ||
              packageName === "react-router" ||
              packageName === "react-router-dom" ||
              packageName === "scheduler"
            ) {
              return "vendor-react-core";
            }
            return "vendor-others";
          }
        }
      }
    },
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 9102,
    strictPort: true,
    cors: true,
    hmr: {
      protocol: "ws",
      host: "localhost",
      port: 9102,
    },
    allowedHosts: [
      "jae.local",
      "localhost"
    ]
  },
});
