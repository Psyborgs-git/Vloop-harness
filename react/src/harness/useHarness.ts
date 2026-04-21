/**
 * useHarness — primary hook for every harness component React app.
 *
 * Reads window.__HARNESS__ on mount, connects to the Python WebSocket,
 * keeps state in sync, and exposes an emit() function.
 */

import { useContext } from "react";
import { HarnessCtx } from "./HarnessProvider";
import type { HarnessContext } from "./types";

export function useHarness(): HarnessContext {
  const ctx = useContext(HarnessCtx);
  if (!ctx) {
    throw new Error("useHarness must be used inside <HarnessProvider>");
  }
  return ctx;
}

export { HarnessCtx };
