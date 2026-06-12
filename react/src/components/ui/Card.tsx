import { Box, BoxProps } from "@mui/material";

export interface CardProps extends BoxProps {
  paddingType?: "none" | "compact" | "medium" | "cozy";
  bordered?: boolean;
}

export default function Card({
  paddingType = "medium",
  bordered = true,
  sx,
  ...props
}: CardProps) {
  const getPadding = () => {
    switch (paddingType) {
      case "none":
        return 0;
      case "compact":
        return 1.5; // 12px
      case "medium":
        return 2; // 16px
      case "cozy":
        return 3; // 24px
      default:
        return 2;
    }
  };

  return (
    <Box
      sx={{
        bgcolor: "background.paper",
        borderRadius: "8px",
        p: getPadding(),
        border: bordered ? "1px solid rgba(255,255,255,0.08)" : "none",
        transition: "border-color 0.15s",
        ...sx,
      }}
      {...props}
    />
  );
}
