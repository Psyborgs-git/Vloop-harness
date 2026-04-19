import { useEffect, useRef, useState } from "react";
import * as tauriApi from "../../api/tauri";

interface Props {
  sessionId: string;
}

export default function XtermInstance({ sessionId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<unknown>(null);
  const fitAddonRef = useRef<unknown>(null);
  const unlistenRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let cancelled = false;

    const init = async () => {
      const { Terminal } = await import("xterm");
      const { FitAddon } = await import("xterm-addon-fit");

      if (cancelled || !containerRef.current) return;

      const term = new Terminal({
        theme: { background: "#0d1117", foreground: "#c9d1d9" },
        fontSize: 13,
        fontFamily: "JetBrains Mono, Menlo, monospace",
        cursorBlink: true,
      });
      const fitAddon = new FitAddon();
      term.loadAddon(fitAddon);
      term.open(containerRef.current);
      fitAddon.fit();
      termRef.current = term;
      fitAddonRef.current = fitAddon;

      // Write session output to xterm
      const unlisten = await tauriApi.onTerminalOutput(
        ({ session_id, data }) => {
          if (session_id === sessionId) term.write(data);
        }
      );
      unlistenRef.current = unlisten;

      // Send xterm keystrokes to PTY
      term.onData((data) => {
        tauriApi.terminalWrite(sessionId, data).catch(() => {});
      });

      // Resize observer
      const ro = new ResizeObserver(() => {
        fitAddon.fit();
        tauriApi
          .terminalResize(sessionId, term.cols, term.rows)
          .catch(() => {});
      });
      if (containerRef.current) ro.observe(containerRef.current);

      return () => ro.disconnect();
    };

    init();

    return () => {
      cancelled = true;
      unlistenRef.current?.();
      (termRef.current as { dispose?: () => void })?.dispose?.();
    };
  }, [sessionId]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", overflow: "hidden" }}
    />
  );
}
