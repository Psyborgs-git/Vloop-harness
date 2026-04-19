import { useState } from "react";
import { Box, Drawer, IconButton, Toolbar, useTheme } from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import SideNav from "./SideNav";
import TopBar from "./TopBar";

const DRAWER_WIDTH = 220;

interface Props {
  children: React.ReactNode;
}

export default function AppShell({ children }: Props) {
  const [open, setOpen] = useState(true);
  const theme = useTheme();

  return (
    <Box sx={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <TopBar drawerOpen={open} onToggle={() => setOpen(!open)} />
      <Drawer
        variant="persistent"
        open={open}
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: DRAWER_WIDTH,
            boxSizing: "border-box",
            borderRight: `1px solid ${theme.palette.divider}`,
            top: 48,
            height: "calc(100vh - 48px)",
          },
        }}
      >
        <SideNav />
      </Drawer>
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          mt: "48px",
          height: "calc(100vh - 48px)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          ml: open ? `${DRAWER_WIDTH}px` : 0,
          transition: theme.transitions.create("margin", {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.enteringScreen,
          }),
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
