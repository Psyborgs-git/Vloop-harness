import { Button as MuiButton, ButtonProps as MuiButtonProps } from "@mui/material";

export interface ButtonProps extends MuiButtonProps {
  variant?: "contained" | "outlined" | "text";
  colorType?: "primary" | "secondary" | "neutral" | "danger";
}

export default function Button({
  variant = "contained",
  colorType = "primary",
  sx,
  ...props
}: ButtonProps) {
  const getColorStyles = () => {
    switch (colorType) {
      case "primary":
        return variant === "contained"
          ? {
              bgcolor: "primary.main",
              color: "#ffffff",
              "&:hover": { bgcolor: "primary.dark", boxShadow: "none" },
            }
          : variant === "outlined"
          ? {
              borderColor: "primary.main",
              color: "primary.main",
              "&:hover": { bgcolor: "rgba(99,102,241,0.08)", borderColor: "primary.dark" },
            }
          : {
              color: "primary.main",
              "&:hover": { bgcolor: "rgba(99,102,241,0.04)" },
            };
      case "secondary":
        return variant === "contained"
          ? {
              bgcolor: "secondary.main",
              color: "#ffffff",
              "&:hover": { bgcolor: "secondary.dark", boxShadow: "none" },
            }
          : variant === "outlined"
          ? {
              borderColor: "secondary.main",
              color: "secondary.main",
              "&:hover": { bgcolor: "rgba(236,72,153,0.08)", borderColor: "secondary.dark" },
            }
          : {
              color: "secondary.main",
              "&:hover": { bgcolor: "rgba(236,72,153,0.04)" },
            };
      case "neutral":
        return variant === "contained"
          ? {
              bgcolor: "rgba(255,255,255,0.04)",
              color: "text.primary",
              border: "1px solid rgba(255,255,255,0.08)",
              "&:hover": { bgcolor: "rgba(255,255,255,0.08)", boxShadow: "none" },
            }
          : variant === "outlined"
          ? {
              borderColor: "rgba(255,255,255,0.08)",
              color: "text.secondary",
              "&:hover": { bgcolor: "rgba(255,255,255,0.02)", color: "text.primary", borderColor: "rgba(255,255,255,0.15)" },
            }
          : {
              color: "text.secondary",
              "&:hover": { bgcolor: "rgba(255,255,255,0.02)", color: "text.primary" },
            };
      case "danger":
        return variant === "contained"
          ? {
              bgcolor: "#ef4444",
              color: "#ffffff",
              "&:hover": { bgcolor: "#dc2626", boxShadow: "none" },
            }
          : variant === "outlined"
          ? {
              borderColor: "#ef4444",
              color: "#ef4444",
              "&:hover": { bgcolor: "rgba(239,68,68,0.08)", borderColor: "#dc2626" },
            }
          : {
              color: "#ef4444",
              "&:hover": { bgcolor: "rgba(239,68,68,0.04)" },
            };
      default:
        return {};
    }
  };

  return (
    <MuiButton
      variant={variant === "text" ? "text" : variant === "outlined" ? "outlined" : "contained"}
      sx={{
        borderRadius: "8px",
        textTransform: "none",
        fontWeight: 500,
        boxShadow: "none",
        fontFamily: "Inter, sans-serif",
        px: 2,
        py: 0.75,
        transition: "all 0.15s ease-in-out",
        "&.Mui-disabled": {
          bgcolor: variant === "contained" ? "rgba(255,255,255,0.02)" : "transparent",
          color: "text.disabled",
          border: variant === "outlined" ? "1px solid rgba(255,255,255,0.04)" : "none",
        },
        ...getColorStyles(),
        ...sx,
      }}
      {...props}
    />
  );
}
