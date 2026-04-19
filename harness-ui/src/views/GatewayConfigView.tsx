import { useEffect, useState } from "react";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import SendIcon from "@mui/icons-material/Send";
import * as tauriApi from "../api/tauri";

interface AdapterInfo {
  id: string;
  adapter_type: string;
}

export default function GatewayConfigView() {
  const [adapters, setAdapters] = useState<AdapterInfo[]>([]);
  const [openAdd, setOpenAdd] = useState(false);
  const [form, setForm] = useState({
    name: "",
    adapter_type: "stdio",
    url: "",
    path: "",
  });
  const [sendDialog, setSendDialog] = useState<{ id: string } | null>(null);
  const [message, setMessage] = useState("");

  const refresh = () => {
    tauriApi.gatewayListAdapters().then((a) => setAdapters(a as AdapterInfo[]));
  };

  useEffect(() => {
    refresh();
  }, []);

  const addAdapter = async () => {
    await tauriApi.gatewayAddAdapter({
      name: form.name,
      adapter_type: form.adapter_type,
      url: form.url || undefined,
      path: form.path || undefined,
    });
    setOpenAdd(false);
    refresh();
  };

  const removeAdapter = async (id: string) => {
    await tauriApi.gatewayRemoveAdapter(id);
    refresh();
  };

  const send = async () => {
    if (!sendDialog) return;
    await tauriApi.gatewaySend(sendDialog.id, message);
    setSendDialog(null);
    setMessage("");
  };

  return (
    <Box sx={{ p: 2, height: "100%", overflow: "auto" }}>
      <Box display="flex" alignItems="center" gap={1} mb={2}>
        <Typography variant="h6">Gateway Config</Typography>
        <Button
          size="small"
          variant="outlined"
          startIcon={<AddIcon />}
          onClick={() => setOpenAdd(true)}
        >
          Add Adapter
        </Button>
        <Button size="small" onClick={refresh}>
          Refresh
        </Button>
      </Box>

      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {adapters.length === 0 && (
              <TableRow>
                <TableCell colSpan={3}>
                  <Typography variant="body2" color="text.secondary" align="center">
                    No adapters configured
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {adapters.map((a) => (
              <TableRow key={a.id}>
                <TableCell>
                  <Typography variant="body2" fontFamily="monospace">
                    {a.id.slice(0, 12)}…
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip label={a.adapter_type} size="small" />
                </TableCell>
                <TableCell>
                  <Box display="flex" gap={0.5}>
                    <IconButton size="small" onClick={() => setSendDialog({ id: a.id })} title="Send">
                      <SendIcon fontSize="small" />
                    </IconButton>
                    <IconButton size="small" onClick={() => removeAdapter(a.id)} title="Remove">
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Box>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Add adapter dialog */}
      <Dialog open={openAdd} onClose={() => setOpenAdd(false)} fullWidth maxWidth="xs">
        <DialogTitle>Add Adapter</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 1.5, pt: 2 }}>
          <TextField
            label="Name"
            size="small"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
          <FormControl size="small">
            <InputLabel>Type</InputLabel>
            <Select
              label="Type"
              value={form.adapter_type}
              onChange={(e) => setForm((f) => ({ ...f, adapter_type: e.target.value }))}
            >
              {["stdio", "http", "websocket", "unix_socket"].map((t) => (
                <MenuItem key={t} value={t}>
                  {t}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {(form.adapter_type === "http" || form.adapter_type === "websocket") && (
            <TextField
              label="URL"
              size="small"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            />
          )}
          {form.adapter_type === "unix_socket" && (
            <TextField
              label="Socket path"
              size="small"
              value={form.path}
              onChange={(e) => setForm((f) => ({ ...f, path: e.target.value }))}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAdd(false)}>Cancel</Button>
          <Button variant="contained" onClick={addAdapter} disabled={!form.name}>
            Add
          </Button>
        </DialogActions>
      </Dialog>

      {/* Send dialog */}
      {sendDialog && (
        <Dialog open onClose={() => setSendDialog(null)} fullWidth maxWidth="sm">
          <DialogTitle>Send Message</DialogTitle>
          <DialogContent>
            <TextField
              fullWidth
              multiline
              rows={4}
              label="Message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              sx={{ mt: 1 }}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setSendDialog(null)}>Cancel</Button>
            <Button variant="contained" onClick={send} disabled={!message}>
              Send
            </Button>
          </DialogActions>
        </Dialog>
      )}
    </Box>
  );
}
