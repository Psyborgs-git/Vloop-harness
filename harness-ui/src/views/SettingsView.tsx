import { useState, useEffect } from "react";
import {
  Box,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { useThemeStore } from "../stores/themeStore";
import * as tauriApi from "../api/tauri";

const PRESET_COLORS = [
  "#7c6af7",
  "#00b4d8",
  "#06d6a0",
  "#ef476f",
  "#ffd166",
  "#ffffff",
];

export default function SettingsView() {
  const { mode, primaryColor, setMode, setPrimaryColor } = useThemeStore();
  const [lmProvider, setLmProvider] = useState("ollama");
  const [lmModel, setLmModel] = useState("llama3");
  const [fontSize, setFontSize] = useState(13);

  // Load persisted settings from harness-core app_config on mount
  useEffect(() => {
    const load = async () => {
      try {
        const [prov, model, size] = await Promise.all([
          tauriApi.dbConfigGet("lm_provider"),
          tauriApi.dbConfigGet("lm_model"),
          tauriApi.dbConfigGet("terminal_font_size"),
        ]);
        if (prov) setLmProvider(prov);
        if (model) setLmModel(model);
        if (size) setFontSize(Number(size));
      } catch {
        // harness-core may not be running in dev / web preview — ignore
      }
    };
    load();
  }, []);

  const handleProviderChange = async (value: string) => {
    setLmProvider(value);
    try {
      await tauriApi.dbConfigSet("lm_provider", value);
    } catch {}
  };

  const handleModelChange = async (value: string) => {
    setLmModel(value);
    try {
      await tauriApi.dbConfigSet("lm_model", value);
    } catch {}
  };

  const handleFontSizeChange = async (value: number) => {
    setFontSize(value);
    try {
      await tauriApi.dbConfigSet("terminal_font_size", String(value));
    } catch {}
  };

  return (
    <Box sx={{ p: 3, height: "100%", overflow: "auto" }}>
      <Typography variant="h6" gutterBottom>
        Settings
      </Typography>
      <Divider sx={{ mb: 2 }} />

      <Stack spacing={3} maxWidth={500}>
        {/* Theme */}
        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Appearance
          </Typography>
          <Stack direction="row" alignItems="center" gap={2} mb={1}>
            <Typography variant="body2">Dark Mode</Typography>
            <Switch
              checked={mode === "dark"}
              onChange={(_, checked) => setMode(checked ? "dark" : "light")}
            />
          </Stack>
          <Typography variant="body2" gutterBottom>
            Accent colour
          </Typography>
          <Box display="flex" gap={1} flexWrap="wrap">
            {PRESET_COLORS.map((c) => (
              <Box
                key={c}
                onClick={() => setPrimaryColor(c)}
                sx={{
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  bgcolor: c,
                  cursor: "pointer",
                  border: primaryColor === c ? "3px solid white" : "2px solid transparent",
                  boxSizing: "border-box",
                }}
              />
            ))}
            <input
              type="color"
              value={primaryColor}
              onChange={(e) => setPrimaryColor(e.target.value)}
              style={{ width: 28, height: 28, cursor: "pointer", border: "none", padding: 0 }}
              title="Custom colour"
            />
          </Box>
        </Box>

        <Divider />

        {/* LM */}
        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Language Model
          </Typography>
          <Stack spacing={1.5}>
            <FormControl size="small">
              <InputLabel>Provider</InputLabel>
              <Select
                label="Provider"
                value={lmProvider}
                onChange={(e) => handleProviderChange(e.target.value)}
              >
                {["ollama", "openai", "anthropic", "lmstudio"].map((p) => (
                  <MenuItem key={p} value={p}>
                    {p}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Model"
              size="small"
              value={lmModel}
              onChange={(e) => handleModelChange(e.target.value)}
            />
          </Stack>
        </Box>

        <Divider />

        {/* Terminal */}
        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Terminal Font Size
          </Typography>
          <Slider
            min={10}
            max={20}
            value={fontSize}
            onChange={(_, v) => handleFontSizeChange(v as number)}
            valueLabelDisplay="auto"
            sx={{ maxWidth: 280 }}
          />
        </Box>
      </Stack>
    </Box>
  );
}
