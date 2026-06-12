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
  Chip,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import type { ConfirmationRequest } from "./types";
import Dialog from "../ui/Dialog";
import Button from "../ui/Button";

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

  const dialogTitle = (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, width: "100%" }}>
      <WarningAmberIcon
        sx={{ color: isDestructive ? "error.main" : "warning.main", fontSize: 20 }}
      />
      <span style={{ fontSize: "1rem" }}>Confirm Action</span>
      <Box sx={{ flexGrow: 1 }} />
      <Chip
        label={confirmation.risk_level}
        size="small"
        variant="outlined"
        sx={{
          color: isDestructive ? "#ef4444" : "#f59e0b",
          borderColor: isDestructive ? "rgba(239,68,68,0.3)" : "rgba(245,158,11,0.3)",
          fontFamily: "Inter, sans-serif",
          fontWeight: 600,
          textTransform: "capitalize",
          height: 20,
          fontSize: "0.7rem",
        }}
      />
    </Box>
  );

  const dialogActions = (
    <>
      <Button
        onClick={() => onCancel(confirmation.token)}
        variant="text"
        colorType="neutral"
        size="small"
      >
        Cancel
      </Button>
      <Button
        onClick={() => onConfirm(confirmation.token)}
        variant="contained"
        colorType={isDestructive ? "danger" : "secondary"}
        size="small"
        autoFocus
      >
        Confirm
      </Button>
    </>
  );

  return (
    <Dialog
      open
      maxWidth="sm"
      fullWidth
      titleText={dialogTitle}
      actions={dialogActions}
    >
      <Alert
        severity={isDestructive ? "error" : "warning"}
        variant="outlined"
        sx={{
          mb: 2,
          borderRadius: "8px",
          bgcolor: isDestructive ? "rgba(239,68,68,0.03)" : "rgba(245,158,11,0.03)",
          borderColor: isDestructive ? "rgba(239,68,68,0.15)" : "rgba(245,158,11,0.15)",
          color: isDestructive ? "#fecaca" : "#fef3c7",
          fontFamily: "Inter, sans-serif",
          fontSize: "0.875rem",
          "& .MuiAlert-icon": {
            color: isDestructive ? "#f87171" : "#fbbf24",
          },
        }}
      >
        {confirmation.description}
      </Alert>
      <Typography variant="caption" color="text.secondary" fontFamily="Inter, sans-serif" sx={{ display: "block", textAlign: "right" }}>
        This confirmation expires in {secondsLeft}s.
      </Typography>
    </Dialog>
  );
}
