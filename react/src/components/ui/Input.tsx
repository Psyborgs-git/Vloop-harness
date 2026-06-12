import { TextField as MuiTextField, TextFieldProps as MuiTextFieldProps } from "@mui/material";

export type InputProps = MuiTextFieldProps;

export default function Input({
  sx,
  size = "small",
  ...props
}: InputProps) {
  return (
    <MuiTextField
      size={size}
      sx={{
        "& .MuiOutlinedInput-root": {
          borderRadius: "8px",
          bgcolor: "background.default",
          fontFamily: "Inter, sans-serif",
          fontSize: "0.875rem",
          "& fieldset": { borderColor: "rgba(255,255,255,0.08)", transition: "border-color 0.15s" },
          "&:hover fieldset": { borderColor: "rgba(255,255,255,0.15)" },
          "&.Mui-focused fieldset": { borderColor: "primary.main" },
        },
        "& .MuiInputLabel-root": {
          fontFamily: "Inter, sans-serif",
          fontSize: "0.875rem",
          color: "text.secondary",
          "&.Mui-focused": { color: "primary.main" },
        },
        "& .MuiFormHelperText-root": {
          fontFamily: "Inter, sans-serif",
          fontSize: "0.75rem",
          color: "text.secondary",
        },
        ...sx,
      }}
      {...props}
    />
  );
}
