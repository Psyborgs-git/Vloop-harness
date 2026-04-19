import { AppBar, Box, IconButton, Toolbar, Typography } from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import { useThemeStore } from "../../stores/themeStore";

interface Props {
  drawerOpen: boolean;
  onToggle: () => void;
}

export default function TopBar({ onToggle }: Props) {
  const { mode, toggleMode } = useThemeStore();
  return (
    <AppBar
      position="fixed"
      elevation={0}
      sx={{ zIndex: (t) => t.zIndex.drawer + 1, height: 48 }}
    >
      <Toolbar variant="dense" sx={{ minHeight: 48 }}>
        <IconButton
          edge="start"
          color="inherit"
          aria-label="menu"
          onClick={onToggle}
          size="small"
          sx={{ mr: 1 }}
        >
          <MenuIcon fontSize="small" />
        </IconButton>
        <Typography variant="subtitle1" fontWeight={700} sx={{ flexGrow: 1 }}>
          Vloop Harness
        </Typography>
        <IconButton color="inherit" size="small" onClick={toggleMode}>
          {mode === "dark" ? (
            <LightModeIcon fontSize="small" />
          ) : (
            <DarkModeIcon fontSize="small" />
          )}
        </IconButton>
      </Toolbar>
    </AppBar>
  );
}
