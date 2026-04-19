import { useState } from "react";
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
                onChange={(e) => setLmProvider(e.target.value)}
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
              onChange={(e) => setLmModel(e.target.value)}
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
            onChange={(_, v) => setFontSize(v as number)}
            valueLabelDisplay="auto"
            sx={{ maxWidth: 280 }}
          />
        </Box>
      </Stack>
    </Box>
  );
}
