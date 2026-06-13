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
  Chip,
  CircularProgress,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import * as api from "./api";
import type { Provider } from "./types";
import Button from "../ui/Button";
import Input from "../ui/Input";
import Card from "../ui/Card";
import Dialog from "../ui/Dialog";

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
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "8px",
            backgroundColor: "rgba(255,255,255,0.02)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: { xs: "wrap", sm: "nowrap" },
            gap: 2,
          }}
        >
          <Box>
            <Typography variant="subtitle2" fontWeight={600} fontFamily="Inter, sans-serif" color="text.primary">
              Rust Kernel Configuration
            </Typography>
            <Typography variant="body2" fontFamily="Inter, sans-serif" color="text.secondary">
              Configure system-level environment settings, server ports, and completions proxy in an external panel.
            </Typography>
          </Box>
          <Button
            size="small"
            variant="contained"
            colorType="primary"
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
          <Typography variant="h6" fontWeight={600} fontFamily="Inter, sans-serif" sx={{ flexGrow: 1 }}>
            AI Providers
          </Typography>
          <Button
            size="small"
            startIcon={<AddIcon />}
            variant="outlined"
            colorType="primary"
            onClick={openCreate}
          >
            Add Provider
          </Button>
        </Box>

        {loading ? (
          <CircularProgress size={24} sx={{ color: "primary.main" }} />
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
              <Typography variant="body2" fontFamily="Inter, sans-serif" color="text.secondary">
                No providers configured. Add one to enable AI features.
              </Typography>
            )}
          </Stack>
        )}
      </Box>

      {/* Ollama discovery */}
      {ollamaModels.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Typography variant="h6" fontWeight={600} fontFamily="Inter, sans-serif" gutterBottom>
            Locally Available Ollama Models
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            {ollamaModels.map((m) => (
              <Chip
                key={m}
                label={m}
                size="small"
                variant="outlined"
                sx={{
                  fontFamily: "monospace",
                  borderColor: "rgba(255,255,255,0.08)",
                  bgcolor: "rgba(255,255,255,0.02)",
                  color: "text.secondary",
                  borderRadius: "4px",
                }}
              />
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
    <Card
      paddingType="compact"
      sx={{
        borderColor: provider.is_default ? "primary.main" : "rgba(255,255,255,0.08)",
        bgcolor: provider.is_default ? "rgba(99,102,241,0.05)" : "background.paper",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
        <Box sx={{ flexGrow: 1 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
            <Typography variant="subtitle2" fontWeight={600} fontFamily="Inter, sans-serif">
              {provider.name}
            </Typography>
            {provider.is_default && (
              <Chip
                icon={<StarIcon sx={{ fontSize: "14px !important", color: "primary.main !important" }} />}
                label="Default"
                size="small"
                variant="outlined"
                sx={{
                  color: "primary.main",
                  borderColor: "rgba(99,102,241,0.3)",
                  height: 20,
                  fontSize: "0.7rem",
                  fontFamily: "Inter, sans-serif",
                  fontWeight: 600,
                }}
              />
            )}
            <Chip
              label={PROVIDER_LABELS[provider.provider_type as ProviderType] ?? provider.provider_type}
              size="small"
              variant="outlined"
              sx={{
                borderColor: "rgba(255,255,255,0.08)",
                bgcolor: "rgba(255,255,255,0.02)",
                height: 20,
                fontSize: "0.7rem",
                color: "text.secondary",
                fontFamily: "Inter, sans-serif",
              }}
            />
          </Box>
          <Typography variant="body2" fontFamily="Inter, sans-serif" color="text.secondary">
            {provider.model}
            {provider.base_url && ` · ${provider.base_url}`}
            {provider.has_api_key && " · 🔑 API key set"}
          </Typography>
          {testResult && (
            <Alert
              severity={testResult.status === "ok" ? "success" : "error"}
              variant="outlined"
              sx={{
                mt: 1.5,
                py: 0.25,
                borderRadius: "6px",
                fontFamily: "Inter, sans-serif",
                fontSize: "0.8rem",
                bgcolor: testResult.status === "ok" ? "rgba(46,125,50,0.03)" : "rgba(211,47,47,0.03)",
                borderColor: testResult.status === "ok" ? "rgba(46,125,50,0.15)" : "rgba(211,47,47,0.15)",
                color: testResult.status === "ok" ? "#a3e635" : "#fca5a5",
                "& .MuiAlert-icon": { color: testResult.status === "ok" ? "#a3e635" : "#f87171" },
              }}
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
                sx={{
                  borderRadius: "4px",
                  color: provider.is_default ? "primary.main" : "text.secondary",
                  "&:hover": { color: "text.primary" },
                }}
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
            <IconButton
              size="small"
              onClick={onTest}
              disabled={testing}
              sx={{ borderRadius: "4px", color: "text.secondary", "&:hover": { color: "text.primary" } }}
            >
              {testing ? <CircularProgress size={16} sx={{ color: "primary.main" }} /> : <span style={{ fontSize: 14 }}>⚡</span>}
            </IconButton>
          </Tooltip>
          <Tooltip title="Edit">
            <IconButton
              size="small"
              onClick={onEdit}
              sx={{ borderRadius: "4px", color: "text.secondary", "&:hover": { color: "text.primary" } }}
            >
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Delete">
            <IconButton
              size="small"
              onClick={onDelete}
              sx={{ borderRadius: "4px", color: "error.main", opacity: 0.7, "&:hover": { opacity: 1, bgcolor: "rgba(239,68,68,0.06)" } }}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>
    </Card>
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

  const dialogActions = (
    <>
      <Button onClick={onClose} variant="text" colorType="neutral" size="small">
        Cancel
      </Button>
      <Button
        variant="contained"
        colorType="primary"
        onClick={save}
        size="small"
        disabled={!state.name.trim() || !state.model.trim() || saving}
      >
        {saving ? "Saving…" : "Save"}
      </Button>
    </>
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      titleText={form.id ? "Edit Provider" : "Add Provider"}
      actions={dialogActions}
      contentSx={{ display: "flex", flexDirection: "column", gap: 2 }}
    >
      <Input
        label="Display name"
        value={state.name}
        onChange={(e) => update({ name: e.target.value })}
        fullWidth
      />

      <FormControl
        size="small"
        fullWidth
        sx={{
          "& .MuiOutlinedInput-root": {
            borderRadius: "8px",
            bgcolor: "background.default",
            fontFamily: "Inter, sans-serif",
            fontSize: "0.875rem",
            "& fieldset": { borderColor: "rgba(255,255,255,0.08)" },
            "&:hover fieldset": { borderColor: "rgba(255,255,255,0.15)" },
            "&.Mui-focused fieldset": { borderColor: "primary.main" },
          },
          "& .MuiInputLabel-root": {
            fontFamily: "Inter, sans-serif",
            fontSize: "0.875rem",
            color: "text.secondary",
            "&.Mui-focused": { color: "primary.main" },
          },
        }}
      >
        <InputLabel>Provider type</InputLabel>
        <Select
          label="Provider type"
          value={state.provider_type}
          onChange={(e) => update({ provider_type: e.target.value as ProviderType })}
        >
          {PROVIDER_TYPES.map((t) => (
            <MenuItem key={t} value={t} sx={{ fontFamily: "Inter, sans-serif" }}>
              {PROVIDER_LABELS[t]}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {isOllama && ollamaModels.length > 0 ? (
        <FormControl
          size="small"
          fullWidth
          sx={{
            "& .MuiOutlinedInput-root": {
              borderRadius: "8px",
              bgcolor: "background.default",
              fontFamily: "Inter, sans-serif",
              fontSize: "0.875rem",
              "& fieldset": { borderColor: "rgba(255,255,255,0.08)" },
              "&:hover fieldset": { borderColor: "rgba(255,255,255,0.15)" },
              "&.Mui-focused fieldset": { borderColor: "primary.main" },
            },
            "& .MuiInputLabel-root": {
              fontFamily: "Inter, sans-serif",
              fontSize: "0.875rem",
              color: "text.secondary",
              "&.Mui-focused": { color: "primary.main" },
            },
          }}
        >
          <InputLabel>Model</InputLabel>
          <Select
            label="Model"
            value={state.model}
            onChange={(e) => update({ model: e.target.value })}
          >
            {ollamaModels.map((m) => (
              <MenuItem key={m} value={m} sx={{ fontFamily: "monospace" }}>
                {m}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      ) : (
        <Input
          label="Model name"
          value={state.model}
          onChange={(e) => update({ model: e.target.value })}
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
        <Input
          label="Base URL"
          value={state.base_url}
          onChange={(e) => update({ base_url: e.target.value })}
          fullWidth
        />
      )}

      {needsKey && (
        <Input
          label={form.id ? "API key (leave blank to keep existing)" : "API key"}
          type="password"
          value={state.api_key}
          onChange={(e) => update({ api_key: e.target.value })}
          fullWidth
          helperText="Stored encrypted at rest with Fernet symmetric encryption"
        />
      )}

      {error && (
        <Alert
          severity="error"
          variant="outlined"
          sx={{
            borderRadius: "8px",
            fontFamily: "Inter, sans-serif",
            bgcolor: "rgba(211,47,47,0.03)",
            borderColor: "rgba(211,47,47,0.15)",
            color: "#fca5a5",
          }}
        >
          {error}
        </Alert>
      )}
    </Dialog>
  );
}
