import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider, CssBaseline } from "@mui/material";
import { useThemeStore } from "./stores/themeStore";
import { buildTheme } from "./theme/theme";
import AppShell from "./components/layout/AppShell";
import AgentConsoleView from "./views/AgentConsoleView";
import TerminalView from "./views/TerminalView";
import FileExplorerView from "./views/FileExplorerView";
import PipelineStudioView from "./views/PipelineStudioView";
import ProcessManagerView from "./views/ProcessManagerView";
import DatabaseExplorerView from "./views/DatabaseExplorerView";
import GatewayConfigView from "./views/GatewayConfigView";
import HostServiceView from "./views/HostServiceView";
import SettingsView from "./views/SettingsView";

export default function App() {
  const { mode, primaryColor } = useThemeStore();
  const theme = buildTheme(mode, primaryColor);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/" element={<Navigate to="/agents" replace />} />
            <Route path="/agents" element={<AgentConsoleView />} />
            <Route path="/terminal" element={<TerminalView />} />
            <Route path="/files" element={<FileExplorerView />} />
            <Route path="/pipeline" element={<PipelineStudioView />} />
            <Route path="/processes" element={<ProcessManagerView />} />
            <Route path="/database" element={<DatabaseExplorerView />} />
            <Route path="/gateway" element={<GatewayConfigView />} />
            <Route path="/host" element={<HostServiceView />} />
            <Route path="/settings" element={<SettingsView />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
    </ThemeProvider>
  );
}
