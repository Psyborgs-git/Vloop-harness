import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Typography,
  Paper,
} from "@mui/material";
import WifiIcon from "@mui/icons-material/Wifi";
import WifiOffIcon from "@mui/icons-material/WifiOff";
import RefreshIcon from "@mui/icons-material/Refresh";
import * as tauriApi from "../api/tauri";

interface HostStatus {
  running: boolean;
  address?: string;
  url?: string;
  qr_png_base64?: string;
  token?: string;
}

export default function HostServiceView() {
  const [status, setStatus] = useState<HostStatus>({ running: false });
  const [loading, setLoading] = useState(false);

  const refreshStatus = () => {
    tauriApi.hostStatus().then((s) => setStatus(s as HostStatus)).catch(() => {});
  };

  useEffect(() => {
    refreshStatus();
  }, []);

  const startHost = async () => {
    setLoading(true);
    try {
      const s = await tauriApi.hostStart();
      setStatus(s as HostStatus);
    } finally {
      setLoading(false);
    }
  };

  const stopHost = async () => {
    await tauriApi.hostStop();
    setStatus({ running: false });
  };

  const rotateToken = async () => {
    const token = await tauriApi.hostRotateToken();
    refreshStatus();
  };

  return (
    <Box sx={{ p: 3, height: "100%", overflow: "auto" }}>
      <Typography variant="h6" gutterBottom>
        LAN Host Service
      </Typography>

      <Paper variant="outlined" sx={{ p: 2, mb: 2, maxWidth: 480 }}>
        <Box display="flex" alignItems="center" gap={1} mb={1}>
          {status.running ? (
            <WifiIcon color="success" />
          ) : (
            <WifiOffIcon color="disabled" />
          )}
          <Typography variant="subtitle2">
            {status.running ? "Active" : "Inactive"}
          </Typography>
          {status.address && (
            <Typography variant="body2" color="text.secondary">
              {status.address}
            </Typography>
          )}
        </Box>

        {status.url && (
          <Alert severity="info" sx={{ mb: 1, fontSize: 12 }}>
            <Typography variant="body2" fontFamily="monospace" sx={{ wordBreak: "break-all" }}>
              {status.url}
            </Typography>
          </Alert>
        )}

        {status.qr_png_base64 && (
          <Box mb={2} textAlign="center">
            <img
              src={`data:image/png;base64,${status.qr_png_base64}`}
              alt="QR Code"
              style={{ width: 200, height: 200, imageRendering: "pixelated" }}
            />
            <Typography variant="caption" display="block">
              Scan to open on mobile
            </Typography>
          </Box>
        )}

        <Box display="flex" gap={1}>
          {!status.running ? (
            <Button
              variant="contained"
              onClick={startHost}
              disabled={loading}
              startIcon={loading ? <CircularProgress size={16} /> : <WifiIcon />}
            >
              Start Host
            </Button>
          ) : (
            <>
              <Button variant="outlined" color="error" onClick={stopHost}>
                Stop
              </Button>
              <Button
                variant="outlined"
                startIcon={<RefreshIcon />}
                onClick={rotateToken}
              >
                Rotate Token
              </Button>
            </>
          )}
        </Box>
      </Paper>

      <Typography variant="body2" color="text.secondary">
        The LAN host service starts an Axum server on port 47299 binding to all interfaces.
        Share the QR code with any device on the same network. Tokens are HMAC-signed and
        expire after 15 minutes.
      </Typography>
    </Box>
  );
}
