/**
 * ConfirmDialog — reusable confirmation dialog for destructive actions.
 *
 * Shows a human-readable description and risk badge, with Confirm/Cancel buttons.
 * Auto-dismisses when the token expires (based on expires_in_seconds).
 */

import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import type { ConfirmationRequest } from "./types";

interface ConfirmDialogProps {
  confirmation: ConfirmationRequest;
  onConfirm: (token: string) => void;
  onCancel: (token: string) => void;
}

export default function ConfirmDialog({
  confirmation,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [secondsLeft, setSecondsLeft] = useState(confirmation.expires_in_seconds);

  useEffect(() => {
    if (secondsLeft <= 0) {
      onCancel(confirmation.token);
      return;
    }
    const timer = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [secondsLeft, confirmation.token, onCancel]);

  const isDestructive = confirmation.risk_level === "destructive";

  return (
    <Dialog open maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <WarningAmberIcon
          sx={{ color: isDestructive ? "error.main" : "warning.main" }}
        />
        Confirm Action
        <Box sx={{ flexGrow: 1 }} />
        <Chip
          label={confirmation.risk_level}
          size="small"
          color={isDestructive ? "error" : "warning"}
          variant="outlined"
        />
      </DialogTitle>

      <DialogContent>
        <Alert
          severity={isDestructive ? "error" : "warning"}
          variant="outlined"
          sx={{ mb: 2 }}
        >
          {confirmation.description}
        </Alert>
        <Typography variant="caption" color="text.secondary">
          This confirmation expires in {secondsLeft}s.
        </Typography>
      </DialogContent>

      <DialogActions>
        <Button onClick={() => onCancel(confirmation.token)} color="inherit">
          Cancel
        </Button>
        <Button
          onClick={() => onConfirm(confirmation.token)}
          variant="contained"
          color={isDestructive ? "error" : "warning"}
          autoFocus
        >
          Confirm
        </Button>
      </DialogActions>
    </Dialog>
  );
}
