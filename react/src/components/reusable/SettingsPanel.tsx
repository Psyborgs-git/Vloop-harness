import { useEffect, useState } from 'react';
import {
  Box, Typography, Button, TextField,
  CircularProgress, Alert, Stack
} from '@mui/material';

const invoke = async (cmd: string, args?: Record<string, any>) => {
  if ((window as any).__TAURI__ && (window as any).__TAURI__.core) {
    return await (window as any).__TAURI__.core.invoke(cmd, args);
  }
  throw new Error("Tauri not available");
};

export default function SettingsPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [alert, setAlert] = useState<{ type: 'success' | 'error', message: string } | null>(null);

  const [harnessPort, setHarnessPort] = useState('9100');
  const [vitePort, setVitePort] = useState('9102');
  const [stateDbPath, setStateDbPath] = useState('.harness/state.db');
  const [logDir, setLogDir] = useState('.harness/logs');

  useEffect(() => {
    loadConfig();
  }, []);

  async function loadConfig() {
    setLoading(true);
    setAlert(null);
    try {
      const config = await invoke('get_settings_config');

      setHarnessPort(config.HARNESS_PORT || '9100');
      setVitePort(config.VITE_PORT || '9102');
      setStateDbPath(config.STATE_DB_PATH || '.harness/state.db');
      setLogDir(config.LOG_DIR || '.harness/logs');
    } catch (e: any) {
      setAlert({ type: 'error', message: 'Failed to load config: ' + e.message });
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setAlert(null);

    const payload: any = {
      HARNESS_PORT: harnessPort,
      VITE_PORT: vitePort,
      STATE_DB_PATH: stateDbPath,
      LOG_DIR: logDir,
    };

    try {
      await invoke('save_settings_config', { config: payload });
      setAlert({ type: 'success', message: 'Configuration successfully saved into .env file!' });
    } catch (e: any) {
      setAlert({ type: 'error', message: 'Failed to save config: ' + e.message });
    } finally {
      setSaving(false);
    }
  }


  async function handleRestart() {
    if (!confirm('Are you sure you want to restart all underlying Harness services?')) return;
    setLoading(true);
    try {
      await invoke('restart_services');
      setAlert({ type: 'success', message: 'Services successfully restarted!' });
    } catch (e: any) {
      setAlert({ type: 'error', message: 'Failed to restart services: ' + e.message });
    } finally {
      setLoading(false);
    }
  }

  if (loading && !saving) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 600, mx: "auto", p: 3, overflow: "auto" }}>
      <Typography variant="h5" fontWeight={600} fontFamily="Inter, sans-serif" gutterBottom>
        Rust Kernel Configuration
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        Manage system-level configurations, AI proxy endpoints, and underlying server environments.
      </Typography>

      {alert && (
        <Alert severity={alert.type} sx={{ mb: 3 }}>
          {alert.message}
        </Alert>
      )}

      <Stack spacing={3}>

        {/* Harness Ports */}
        <Box>
          <Typography variant="subtitle1" fontWeight={600} gutterBottom color="primary">
            Harness Ports
          </Typography>
          <Stack direction="row" spacing={2}>
            <TextField
              label="Harness Server Port"
              size="small"
              fullWidth
              type="number"
              value={harnessPort}
              onChange={(e) => setHarnessPort(e.target.value)}
            />
            <TextField
              label="Vite Frontend Port"
              size="small"
              fullWidth
              type="number"
              value={vitePort}
              onChange={(e) => setVitePort(e.target.value)}
            />
          </Stack>
        </Box>

        {/* System Paths */}
        <Box>
          <Typography variant="subtitle1" fontWeight={600} gutterBottom color="primary">
            System Paths
          </Typography>
          <Stack spacing={2}>
            <TextField
              label="State DB File Path"
              size="small"
              fullWidth
              value={stateDbPath}
              onChange={(e) => setStateDbPath(e.target.value)}
            />
            <TextField
              label="Logs Directory"
              size="small"
              fullWidth
              value={logDir}
              onChange={(e) => setLogDir(e.target.value)}
            />
          </Stack>
        </Box>

        {/* Actions */}
        <Stack spacing={2} sx={{ mt: 2 }}>
          <Button
            variant="contained"
            color="primary"
            onClick={handleSave}
            disabled={saving || loading}
          >
            {saving ? <CircularProgress size={20} color="inherit" /> : 'Save Configuration'}
          </Button>
          <Button
            variant="outlined"
            color="warning"
            onClick={handleRestart}
            disabled={loading}
          >
            Restart Harness Services
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
}
