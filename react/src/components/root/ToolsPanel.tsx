/**
 * ToolsPanel — top-level Tools tab with sub-navigation.
 *
 * Sub-tabs:
 *   Terminal   — command execution
 *   Filesystem — file tree + viewer
 *   Policy     — view / edit execution policy
 */

import PolicyIcon from "@mui/icons-material/Policy";
import StorageIcon from "@mui/icons-material/Storage";
import TerminalIcon from "@mui/icons-material/Terminal";
import { Box, Tab, Tabs } from "@mui/material";
import { useState } from "react";

import FilesystemPanel from "./FilesystemPanel";
import PolicyPanel from "./PolicyPanel";
import TerminalPanel from "./TerminalPanel";

type SubTab = "terminal" | "filesystem" | "policy";

export default function ToolsPanel() {
  const [subTab, setSubTab] = useState<SubTab>("terminal");

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <Box sx={{ borderBottom: "1px solid", borderColor: "divider" }}>
        <Tabs
          value={subTab}
          onChange={(_, v) => setSubTab(v as SubTab)}
          textColor="primary"
          indicatorColor="primary"
          variant="scrollable"
          scrollButtons="auto"
          sx={{ minHeight: 40 }}
        >
          <Tab
            value="terminal"
            label="Terminal"
            icon={<TerminalIcon fontSize="small" />}
            iconPosition="start"
            sx={{ minHeight: 40, textTransform: "none", fontSize: "0.82rem" }}
          />
          <Tab
            value="filesystem"
            label="Filesystem"
            icon={<StorageIcon fontSize="small" />}
            iconPosition="start"
            sx={{ minHeight: 40, textTransform: "none", fontSize: "0.82rem" }}
          />
          <Tab
            value="policy"
            label="Policy"
            icon={<PolicyIcon fontSize="small" />}
            iconPosition="start"
            sx={{ minHeight: 40, textTransform: "none", fontSize: "0.82rem" }}
          />
        </Tabs>
      </Box>

      <Box sx={{ flexGrow: 1, overflow: "hidden" }}>
        {subTab === "terminal" && <TerminalPanel />}
        {subTab === "filesystem" && <FilesystemPanel />}
        {subTab === "policy" && <PolicyPanel />}
      </Box>
    </Box>
  );
}
