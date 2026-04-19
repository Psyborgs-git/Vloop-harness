import { createTheme, PaletteMode } from "@mui/material";

export function buildTheme(mode: PaletteMode, primaryColor: string) {
  return createTheme({
    palette: {
      mode,
      primary: { main: primaryColor },
      background: {
        default: mode === "dark" ? "#0d1117" : "#f5f5f5",
        paper: mode === "dark" ? "#161b22" : "#ffffff",
      },
    },
    typography: {
      fontFamily: "Inter, system-ui, sans-serif",
      fontSize: 13,
    },
    shape: {
      borderRadius: 8,
    },
    components: {
      MuiButton: {
        styleOverrides: {
          root: { textTransform: "none" },
        },
      },
      MuiListItemButton: {
        styleOverrides: {
          root: { borderRadius: 6 },
        },
      },
    },
  });
}
