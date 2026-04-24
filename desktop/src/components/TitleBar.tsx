import { useEffect, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Minus, Square, X } from "lucide-react";
import { useStore } from "../lib/store";
import { getSettings } from "../lib/api";

interface Props {
  healthStatus: "online" | "degraded" | "offline";
}

const statusColor = {
  online:   "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.6)]",
  degraded: "bg-yellow-400 shadow-[0_0_6px_rgba(250,204,21,0.6)]",
  offline:  "bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.5)]",
};

const statusLabel = {
  online:   "online",
  degraded: "degraded",
  offline:  "offline",
};

export default function TitleBar({ healthStatus }: Props) {
  const { provider, modelAlias } = useStore();
  const win = getCurrentWindow();
  const [controlsSide, setControlsSide] = useState<"left" | "right">("right");
  const [controlsStyle, setControlsStyle] = useState<"windows" | "mac">("windows");
  const [controlsOrder, setControlsOrder] = useState<Array<"minimize" | "maximize" | "close">>([
    "minimize",
    "maximize",
    "close",
  ]);

  function parseOrder(raw: string | undefined): Array<"minimize" | "maximize" | "close"> {
    const fallback: Array<"minimize" | "maximize" | "close"> = ["minimize", "maximize", "close"];
    if (!raw) return fallback;
    const allowed = new Set(["minimize", "maximize", "close"]);
    const parts = raw
      .split(",")
      .map((p) => p.trim().toLowerCase())
      .filter((p) => allowed.has(p));
    if (parts.length !== 3 || new Set(parts).size !== 3) return fallback;
    return parts as Array<"minimize" | "maximize" | "close">;
  }

  async function reloadControlsConfig() {
    try {
      const settings = await getSettings();
      const sideRaw = (settings.WINDOW_CONTROLS_SIDE || "right").toLowerCase();
      const styleRaw = (settings.WINDOW_CONTROLS_STYLE || "windows").toLowerCase();
      setControlsSide(sideRaw === "left" ? "left" : "right");
      setControlsStyle(styleRaw === "mac" ? "mac" : "windows");
      setControlsOrder(parseOrder(settings.WINDOW_CONTROLS_ORDER));
    } catch {
      setControlsSide("right");
      setControlsStyle("windows");
      setControlsOrder(["minimize", "maximize", "close"]);
    }
  }

  useEffect(() => {
    reloadControlsConfig();
    const onSettingsUpdated = () => { reloadControlsConfig(); };
    window.addEventListener("unlz-settings-updated", onSettingsUpdated);
    return () => window.removeEventListener("unlz-settings-updated", onSettingsUpdated);
  }, []);

  const controlAction: Record<"minimize" | "maximize" | "close", () => Promise<void>> = {
    minimize: () => win.minimize(),
    maximize: () => win.toggleMaximize(),
    close: () => win.close(),
  };
  const controlIcon: Record<"minimize" | "maximize" | "close", JSX.Element> = {
    minimize: <Minus size={12} />,
    maximize: <Square size={10} />,
    close: <X size={12} />,
  };
  const controlClassWindows: Record<"minimize" | "maximize" | "close", string> = {
    minimize: "win-btn-windows",
    maximize: "win-btn-windows",
    close: "win-btn-windows close",
  };
  const controlClassMac: Record<"minimize" | "maximize" | "close", string> = {
    close: "win-btn-mac close",
    minimize: "win-btn-mac minimize",
    maximize: "win-btn-mac maximize",
  };
  const controls = (
    <div className={`flex items-center z-10 pointer-events-auto ${controlsStyle === "mac" ? "gap-1.5" : ""}`}>
      {controlsOrder.map((name) =>
        controlsStyle === "mac" ? (
          <button
            key={name}
            className={controlClassMac[name]}
            onClick={() => controlAction[name]()}
            title={name}
          />
        ) : (
          <button
            key={name}
            className={controlClassWindows[name]}
            onClick={() => controlAction[name]()}
            title={name}
          >
            {controlIcon[name]}
          </button>
        )
      )}
    </div>
  );

  return (
    <div
      className="flex items-center justify-between h-9 px-3 bg-surface border-b border-border shrink-0 select-none"
      data-tauri-drag-region
    >
      {controlsSide === "left" ? controls : (
        <div className="flex items-center gap-1.5 text-[11px] text-muted pointer-events-none">
          <span className="text-secondary font-medium">{provider}</span>
          {modelAlias && (
            <>
              <span className="text-border">·</span>
              <span className="font-mono">{modelAlias}</span>
            </>
          )}
        </div>
      )}

      {/* Center: app name + status */}
      <div
        className="absolute left-1/2 -translate-x-1/2 flex items-center gap-2 pointer-events-none"
        data-tauri-drag-region
      >
        <span className="text-xs font-semibold tracking-widest text-secondary uppercase">
          UNLZ Agent
        </span>
        <span className={`status-dot ${statusColor[healthStatus]}`} />
        <span className="text-[10px] text-muted">{statusLabel[healthStatus]}</span>
      </div>

      {controlsSide === "right" ? controls : (
        <div className="flex items-center gap-1.5 text-[11px] text-muted pointer-events-none">
          <span className="text-secondary font-medium">{provider}</span>
          {modelAlias && (
            <>
              <span className="text-border">·</span>
              <span className="font-mono">{modelAlias}</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}
