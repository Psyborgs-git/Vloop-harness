import {
  Dialog as MuiDialog,
  DialogActions as MuiDialogActions,
  DialogContent as MuiDialogContent,
  DialogTitle as MuiDialogTitle,
  DialogProps as MuiDialogProps,
} from "@mui/material";
import React from "react";

export interface DialogProps extends MuiDialogProps {
  titleText?: React.ReactNode;
  actions?: React.ReactNode;
  contentSx?: any;
}

export default function Dialog({
  titleText,
  actions,
  children,
  contentSx,
  PaperProps,
  ...props
}: DialogProps) {
  return (
    <MuiDialog
      maxWidth="xs"
      fullWidth
      PaperProps={{
        ...PaperProps,
        sx: {
          bgcolor: "background.paper",
          border: "1px solid rgba(255,255,255,0.08)",
          boxShadow: "none",
          borderRadius: "8px",
          backgroundImage: "none",
          ...PaperProps?.sx,
        },
      }}
      {...props}
    >
      {titleText && (
        <MuiDialogTitle
          fontWeight={600}
          fontFamily="Inter, sans-serif"
          sx={{
            fontSize: "1.125rem",
            letterSpacing: "-0.01em",
            borderBottom: "1px solid rgba(255,255,255,0.04)",
            py: 2,
            px: 3,
          }}
        >
          {titleText}
        </MuiDialogTitle>
      )}
      <MuiDialogContent sx={{ py: 2, px: 3, mt: titleText ? 1 : 0, ...contentSx }}>
        {children}
      </MuiDialogContent>
      {actions && (
        <MuiDialogActions
          sx={{
            py: 2,
            px: 3,
            borderTop: "1px solid rgba(255,255,255,0.04)",
            gap: 1,
          }}
        >
          {actions}
        </MuiDialogActions>
      )}
    </MuiDialog>
  );
}
