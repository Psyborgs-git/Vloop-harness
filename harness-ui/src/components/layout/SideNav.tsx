import { List, ListItemButton, ListItemIcon, ListItemText } from "@mui/material";
import { useNavigate, useLocation } from "react-router-dom";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import TerminalIcon from "@mui/icons-material/Terminal";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import PlayCircleIcon from "@mui/icons-material/PlayCircle";
import StorageIcon from "@mui/icons-material/Storage";
import HubIcon from "@mui/icons-material/Hub";
import WifiIcon from "@mui/icons-material/Wifi";
import SettingsIcon from "@mui/icons-material/Settings";

const NAV_ITEMS = [
  { label: "Agents", path: "/agents", Icon: SmartToyIcon },
  { label: "Terminal", path: "/terminal", Icon: TerminalIcon },
  { label: "Files", path: "/files", Icon: FolderOpenIcon },
  { label: "Pipeline", path: "/pipeline", Icon: AccountTreeIcon },
  { label: "Processes", path: "/processes", Icon: PlayCircleIcon },
  { label: "Database", path: "/database", Icon: StorageIcon },
  { label: "Gateway", path: "/gateway", Icon: HubIcon },
  { label: "Host", path: "/host", Icon: WifiIcon },
  { label: "Settings", path: "/settings", Icon: SettingsIcon },
];

export default function SideNav() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  return (
    <List dense sx={{ px: 1, pt: 1 }}>
      {NAV_ITEMS.map(({ label, path, Icon }) => (
        <ListItemButton
          key={path}
          selected={pathname === path}
          onClick={() => navigate(path)}
          sx={{ mb: 0.25 }}
        >
          <ListItemIcon sx={{ minWidth: 36 }}>
            <Icon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary={label} />
        </ListItemButton>
      ))}
    </List>
  );
}
