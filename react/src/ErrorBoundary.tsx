import { Component, ErrorInfo, ReactNode } from "react";
import { Box, Typography } from "@mui/material";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error:", error, errorInfo);
    this.setState({ errorInfo });
  }

  public render() {
    if (this.state.hasError) {
      return (
        <Box sx={{ p: 4, bgcolor: "error.light", color: "error.contrastText", borderRadius: 1, m: 2 }}>
          <Typography variant="h5" gutterBottom>
            Something went wrong rendering this component.
          </Typography>
          <Typography variant="body1" sx={{ mt: 2, fontWeight: 'bold' }}>
            {this.state.error && this.state.error.toString()}
          </Typography>
          <Box
            component="pre"
            sx={{
              mt: 2,
              p: 2,
              bgcolor: "rgba(0, 0, 0, 0.1)",
              borderRadius: 1,
              overflowX: "auto",
              fontSize: "0.875rem"
            }}
          >
            {this.state.errorInfo && this.state.errorInfo.componentStack}
          </Box>
        </Box>
      );
    }

    return this.props.children;
  }
}
