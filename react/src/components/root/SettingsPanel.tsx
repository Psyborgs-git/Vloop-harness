/**
 * SettingsPanel — provider configuration and global settings.
 *
 * Sections:
 *  1. AI Providers — CRUD with encrypted API key handling
 *  2. Ollama model discovery
 *  3. Appearance settings (stored in global settings JSON)
 */

import AddIcon from "@mui/icons-material/Add";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditIcon from "@mui/icons-material/Edit";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import StarIcon from "@mui/icons-material/Star";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import * as api from "./api";
import type { Provider } from "./types";

const PROVIDER_TYPES = ["ollama", "anthropic", "openai", "custom"] as const;
type ProviderType = (typeof PROVIDER_TYPES)[number];

const PROVIDER_LABELS: Record<ProviderType, string> = {
  ollama: "Ollama (local)",
  anthropic: "Anthropic",
  openai: "OpenAI",
  custom: "Custom (OpenAI-compatible)",
};

const DEFAULT_MODELS: Record<ProviderType, string> = {
  ollama: "llama3.2",
  anthropic: "claude-sonnet-4-6",
  openai: "gpt-4o",
  custom: "your-model-name",
};

const DEFAULT_URLS: Record<ProviderType, string> = {
  ollama: "http://localhost:11434",
  anthropic: "",
  openai: "",
  custom: "http://localhost:9101",
};

interface ProviderFormState {
  id?: string;
  name: string;
  provider_type: ProviderType;
  model: string;
  base_url: string;
  api_key: string;
}

export default function SettingsPanel() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<ProviderFormState | null>(null);
  const [testResult, setTestResult] = useState<Record<string, { status: string; detail?: string }>>({});
  const [testing, setTesting] = useState<string | null>(null);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);

  useEffect(() => {
    refresh();
    discoverOllama();
  }, []);

  async function refresh() {
    setLoading(true);
    try {
      const p = await api.listProviders();
      setProviders(p);
    } finally {
      setLoading(false);
    }
  }

  async function discoverOllama() {
    const result = await api.listOllamaModels().catch(() => ({ status: "error", models: [] }));
    setOllamaModels(result.models ?? []);
  }

  function openCreate() {
    setEditingProvider({
      name: "",
      provider_type: "ollama",
      model: DEFAULT_MODELS.ollama,
      base_url: DEFAULT_URLS.ollama,
      api_key: "",
    });
    setDialogOpen(true);
  }

  function openEdit(p: Provider) {
    setEditingProvider({
      id: p.id,
      name: p.name,
      provider_type: p.provider_type as ProviderType,
      model: p.model,
      base_url: p.base_url,
      api_key: "",
    });
    setDialogOpen(true);
  }

  async function saveProvider(form: ProviderFormState) {
    if (form.id) {
      await api.updateProvider(form.id, {
        name: form.name,
        provider_type: form.provider_type,
        model: form.model,
        base_url: form.base_url,
        ...(form.api_key ? { api_key: form.api_key } : {}),
      });
    } else {
      await api.createProvider({
        name: form.name,
        provider_type: form.provider_type,
        model: form.model,
        base_url: form.base_url,
        api_key: form.api_key,
      });
    }
    setDialogOpen(false);
    await refresh();
  }

  async function remove(id: string) {
    await api.deleteProvider(id);
    await refresh();
  }

  async function setDefault(id: string) {
    await api.setDefaultProvider(id);
    await refresh();
  }

  async function test(id: string) {
    setTesting(id);
    const result = await api.testProvider(id).catch((e) => ({
      status: "error",
      detail: e.message,
    }));
    setTestResult((prev) => ({ ...prev, [id]: result }));
    setTesting(null);
  }

  return (
    <Box sx={{ maxWidth: 800, mx: "auto", p: 3, overflow: "auto" }}>
      {/* Rust Kernel Settings Button */}
      {(window as any).__TAURI__ && (
        <Box
          sx={{
            p: 2,
            mb: 4,
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            backgroundColor: "action.hover",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: { xs: "wrap", sm: "nowrap" },
            gap: 2,
          }}
        >
          <Box>
            <Typography variant="subtitle2" fontWeight={600} color="text.primary">
              Rust Kernel Configuration
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Configure system-level environment settings, server ports, and completions proxy in an external panel.
            </Typography>
          </Box>
          <Button
            size="small"
            variant="contained"
            color="primary"
            onClick={() => {
              (window as any).__TAURI__.core.invoke("open_settings_window")
                .catch((err: any) => console.error("Failed to open settings window:", err));
            }}
            sx={{ flexShrink: 0 }}
          >
            Manage Kernel Settings
          </Button>
        </Box>
      )}

      {/* Providers */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
          <Typography variant="h6" fontWeight={600} sx={{ flexGrow: 1 }}>
            AI Providers
          </Typography>
          <Button
            size="small"
            startIcon={<AddIcon />}
            variant="outlined"
            onClick={openCreate}
          >
            Add Provider
          </Button>
        </Box>

        {loading ? (
          <CircularProgress size={24} />
        ) : (
          <Stack spacing={1.5}>
            {providers.map((p) => (
              <ProviderCard
                key={p.id}
                provider={p}
                testResult={testResult[p.id]}
                testing={testing === p.id}
                onEdit={() => openEdit(p)}
                onDelete={() => remove(p.id)}
                onSetDefault={() => setDefault(p.id)}
                onTest={() => test(p.id)}
              />
            ))}
            {providers.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                No providers configured. Add one to enable AI features.
              </Typography>
            )}
          </Stack>
        )}
      </Box>

      {/* Ollama discovery */}
      {ollamaModels.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Typography variant="h6" fontWeight={600} gutterBottom>
            Locally Available Ollama Models
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            {ollamaModels.map((m) => (
              <Chip key={m} label={m} size="small" variant="outlined" />
            ))}
          </Box>
        </Box>
      )}

      {/* Provider dialog */}
      {editingProvider && (
        <ProviderDialog
          open={dialogOpen}
          form={editingProvider}
          ollamaModels={ollamaModels}
          onClose={() => setDialogOpen(false)}
          onSave={saveProvider}
        />
      )}
    </Box>
  );
}

// ── Provider card ──────────────────────────────────────────────────────────────

function ProviderCard({
  provider,
  testResult,
  testing,
  onEdit,
  onDelete,
  onSetDefault,
  onTest,
}: {
  provider: Provider;
  testResult?: { status: string; detail?: string };
  testing: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onSetDefault: () => void;
  onTest: () => void;
}) {
  return (
    <Box
      sx={{
        p: 2,
        border: "1px solid",
        borderColor: provider.is_default ? "primary.main" : "divider",
        borderRadius: 2,
        bgcolor: provider.is_default ? "action.selected" : "background.paper",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
        <Box sx={{ flexGrow: 1 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
            <Typography variant="subtitle2" fontWeight={600}>
              {provider.name}
            </Typography>
            {provider.is_default && (
              <Chip
                icon={<StarIcon sx={{ fontSize: "14px !important" }} />}
                label="Default"
                size="small"
                color="primary"
              />
            )}
            <Chip
              label={PROVIDER_LABELS[provider.provider_type as ProviderType] ?? provider.provider_type}
              size="small"
              variant="outlined"
            />
          </Box>
          <Typography variant="body2" color="text.secondary">
            {provider.model}
            {provider.base_url && ` · ${provider.base_url}`}
            {provider.has_api_key && " · 🔑 API key set"}
          </Typography>
          {testResult && (
            <Alert
              severity={testResult.status === "ok" ? "success" : "error"}
              variant="outlined"
              sx={{ mt: 1, py: 0 }}
            >
              {testResult.status === "ok" ? "Connection OK" : testResult.detail}
            </Alert>
          )}
        </Box>

        <Box sx={{ display: "flex", gap: 0.5, flexShrink: 0 }}>
          <Tooltip title={provider.is_default ? "Already default" : "Set as default"}>
            <span>
              <IconButton
                size="small"
                onClick={onSetDefault}
                disabled={provider.is_default}
                color={provider.is_default ? "primary" : "default"}
              >
                {provider.is_default ? (
                  <CheckCircleIcon fontSize="small" />
                ) : (
                  <RadioButtonUncheckedIcon fontSize="small" />
                )}
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="Test connection">
            <IconButton size="small" onClick={onTest} disabled={testing}>
              {testing ? <CircularProgress size={16} /> : <span style={{ fontSize: 14 }}>⚡</span>}
            </IconButton>
          </Tooltip>
          <Tooltip title="Edit">
            <IconButton size="small" onClick={onEdit}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Delete">
            <IconButton
              size="small"
              onClick={onDelete}
              sx={{ color: "error.main", opacity: 0.7, "&:hover": { opacity: 1 } }}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>
    </Box>
  );
}

// ── Provider form dialog ───────────────────────────────────────────────────────

function ProviderDialog({
  open,
  form,
  ollamaModels,
  onClose,
  onSave,
}: {
  open: boolean;
  form: ProviderFormState;
  ollamaModels: string[];
  onClose: () => void;
  onSave: (f: ProviderFormState) => void;
}) {
  const [state, setState] = useState<ProviderFormState>(form);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setState(form);
    setError(null);
  }, [form, open]);

  function update(patch: Partial<ProviderFormState>) {
    setState((prev) => {
      const next = { ...prev, ...patch };
      if (patch.provider_type) {
        next.model = next.model || DEFAULT_MODELS[patch.provider_type];
        next.base_url = DEFAULT_URLS[patch.provider_type];
      }
      return next;
    });
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave(state);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const needsKey = state.provider_type === "anthropic" || state.provider_type === "openai";
  const needsUrl = state.provider_type === "ollama" || state.provider_type === "custom";
  const isOllama = state.provider_type === "ollama";

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{form.id ? "Edit Provider" : "Add Provider"}</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
        <TextField
          label="Display name"
          value={state.name}
          onChange={(e) => update({ name: e.target.value })}
          size="small"
          fullWidth
        />

        <FormControl size="small" fullWidth>
          <InputLabel>Provider type</InputLabel>
          <Select
            label="Provider type"
            value={state.provider_type}
            onChange={(e) => update({ provider_type: e.target.value as ProviderType })}
          >
            {PROVIDER_TYPES.map((t) => (
              <MenuItem key={t} value={t}>
                {PROVIDER_LABELS[t]}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {isOllama && ollamaModels.length > 0 ? (
          <FormControl size="small" fullWidth>
            <InputLabel>Model</InputLabel>
            <Select
              label="Model"
              value={state.model}
              onChange={(e) => update({ model: e.target.value })}
            >
              {ollamaModels.map((m) => (
                <MenuItem key={m} value={m}>
                  {m}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        ) : (
          <TextField
            label="Model name"
            value={state.model}
            onChange={(e) => update({ model: e.target.value })}
            size="small"
            fullWidth
            helperText={
              state.provider_type === "anthropic"
                ? "e.g. claude-sonnet-4-6"
                : state.provider_type === "openai"
                ? "e.g. gpt-4o"
                : undefined
            }
          />
        )}

        {needsUrl && (
          <TextField
            label="Base URL"
            value={state.base_url}
            onChange={(e) => update({ base_url: e.target.value })}
            size="small"
            fullWidth
          />
        )}

        {needsKey && (
          <TextField
            label={form.id ? "API key (leave blank to keep existing)" : "API key"}
            type="password"
            value={state.api_key}
            onChange={(e) => update({ api_key: e.target.value })}
            size="small"
            fullWidth
            helperText="Stored encrypted at rest with Fernet symmetric encryption"
          />
        )}

        {error && (
          <Alert severity="error" variant="outlined">
            {error}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={save}
          disabled={!state.name.trim() || !state.model.trim() || saving}
        >
          {saving ? "Saving…" : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
