/**
 * Root UI — window manager shell.
 *
 * Fetches the component list from the Python API on mount, then renders
 * a floating View (iframe) for each running component.
 */

import React, { useEffect, useRef, useState } from "react";
import { useHarness } from "@harness/useHarness";

interface ComponentSnapshot {
  id: string;
  state: Record<string, unknown>;
  props: Record<string, unknown>;
  permissions: string[];
}

interface ViewState {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minimised: boolean;
  title: string;
}

function View({
  view,
  apiBase,
  onMinimise,
  onClose,
  onMove,
}: {
  view: ViewState;
  apiBase: string;
  onMinimise: (id: string) => void;
  onClose: (id: string) => void;
  onMove: (id: string, x: number, y: number) => void;
}) {
  const dragStart = useRef<{ mx: number; my: number; vx: number; vy: number } | null>(null);

  function handleMouseDown(e: React.MouseEvent) {
    dragStart.current = { mx: e.clientX, my: e.clientY, vx: view.x, vy: view.y };

    function onMove(e: MouseEvent) {
      if (!dragStart.current) return;
      const dx = e.clientX - dragStart.current.mx;
      const dy = e.clientY - dragStart.current.my;
      onMoveView(dragStart.current.vx + dx, dragStart.current.vy + dy);
    }

    function onUp() {
      dragStart.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function onMoveView(x: number, y: number) {
    onMove(view.id, x, y);
  }

  return (
    <div
      style={{
        position: "absolute",
        left: view.x,
        top: view.y,
        width: view.w,
        height: view.h + 32,
        display: view.minimised ? "none" : "flex",
        flexDirection: "column",
        border: "1px solid #333",
        borderRadius: 6,
        overflow: "hidden",
        boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
        background: "#1a1a1a",
      }}
    >
      {/* Title bar */}
      <div
        onMouseDown={handleMouseDown}
        style={{
          height: 32,
          background: "#2a2a2a",
          display: "flex",
          alignItems: "center",
          padding: "0 8px",
          cursor: "grab",
          userSelect: "none",
          flexShrink: 0,
        }}
      >
        <span style={{ flex: 1, fontSize: 12, color: "#ccc" }}>{view.title}</span>
        <button
          onClick={() => onMinimise(view.id)}
          style={btnStyle}
          title="Minimise"
        >
          −
        </button>
        <button
          onClick={() => onClose(view.id)}
          style={{ ...btnStyle, marginLeft: 4 }}
          title="Close"
        >
          ✕
        </button>
      </div>
      {/* Component iframe */}
      <iframe
        src={`/ui/${view.id}/`}
        style={{ flex: 1, border: "none", background: "#111" }}
        title={view.id}
      />
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#aaa",
  cursor: "pointer",
  fontSize: 14,
  padding: "2px 6px",
  borderRadius: 3,
};

export default function App() {
  const { connected } = useHarness();
  const [components, setComponents] = useState<ComponentSnapshot[]>([]);
  const [views, setViews] = useState<Map<string, ViewState>>(new Map());
  const apiBase = window.__HARNESS__?.API_URL?.replace(/\/api\/.*/, "") ?? "http://localhost:8000";

  useEffect(() => {
    fetch(`${apiBase}/api/components`)
      .then((r) => r.json())
      .then((list: ComponentSnapshot[]) => {
        setComponents(list.filter((c) => c.id !== "root"));
        list.forEach((c, i) => {
          if (c.id === "root") return;
          setViews((prev) => {
            if (prev.has(c.id)) return prev;
            const next = new Map(prev);
            next.set(c.id, {
              id: c.id,
              x: 40 + i * 30,
              y: 40 + i * 30,
              w: 480,
              h: 360,
              minimised: false,
              title: c.id,
            });
            return next;
          });
        });
      })
      .catch(() => {});
  }, [apiBase]);

  function closeComponent(id: string) {
    fetch(`${apiBase}/api/components/${id}`, { method: "DELETE" }).catch(() => {});
    setViews((prev) => {
      const next = new Map(prev);
      next.delete(id);
      return next;
    });
    setComponents((prev) => prev.filter((c) => c.id !== id));
  }

  function minimiseComponent(id: string) {
    setViews((prev) => {
      const v = prev.get(id);
      if (!v) return prev;
      const next = new Map(prev);
      next.set(id, { ...v, minimised: true });
      return next;
    });
    fetch(`${apiBase}/api/${id}/event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "hide", payload: null }),
    }).catch(() => {});
  }

  function moveView(id: string, x: number, y: number) {
    setViews((prev) => {
      const v = prev.get(id);
      if (!v) return prev;
      const next = new Map(prev);
      next.set(id, { ...v, x, y });
      return next;
    });
  }

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: "#0d0d0d",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Status bar */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 24,
          background: "#111",
          display: "flex",
          alignItems: "center",
          padding: "0 12px",
          gap: 12,
          fontSize: 11,
          color: "#666",
          zIndex: 9999,
        }}
      >
        <span style={{ color: connected ? "#4ade80" : "#f87171" }}>
          {connected ? "● connected" : "○ disconnected"}
        </span>
        <span>{views.size} component{views.size !== 1 ? "s" : ""}</span>
        {/* Minimised pills */}
        {[...views.values()]
          .filter((v) => v.minimised)
          .map((v) => (
            <button
              key={v.id}
              onClick={() =>
                setViews((prev) => {
                  const next = new Map(prev);
                  next.set(v.id, { ...v, minimised: false });
                  return next;
                })
              }
              style={{ ...btnStyle, color: "#ccc", background: "#222", border: "1px solid #333" }}
            >
              {v.title}
            </button>
          ))}
      </div>

      {/* Floating views */}
      {[...views.values()].map((v) => (
        <View
          key={v.id}
          view={v}
          apiBase={apiBase}
          onMinimise={minimiseComponent}
          onClose={closeComponent}
          onMove={moveView}
        />
      ))}
    </div>
  );
}
