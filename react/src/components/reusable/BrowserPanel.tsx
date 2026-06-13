/**
 * BrowserPanel — browser automation control panel.
 *
 * Features:
 *  • Navigate to URLs
 *  • Take screenshots
 *  • Get page text/HTML
 *  • Click elements
 *  • Fill forms
 *  • Evaluate JavaScript (requires permission)
 *  • Close browser context
 */

import CloseIcon from "@mui/icons-material/Close";
import {
    Box,
    Button,
    CircularProgress,
    Divider,
    IconButton,
    MenuItem,
    Select,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import { useState } from "react";

import * as api from "./api";

interface Props {
    onClose: () => void;
}

export default function BrowserPanel({ onClose }: Props) {
    const [operation, setOperation] = useState("navigate");
    const [url, setUrl] = useState("");
    const [selector, setSelector] = useState("");
    const [value, setValue] = useState("");
    const [expression, setExpression] = useState("");
    const [fullPage, setFullPage] = useState(false);
    const [loading, setLoading] = useState(false);
    const [output, setOutput] = useState("");
    const [error, setError] = useState("");

    const handleExecute = async () => {
        setLoading(true);
        setError("");
        setOutput("");

        try {
            const result = await api.executeBrowserTool({
                operation,
                url,
                selector,
                value,
                expression,
                full_page: fullPage,
            });

            if ("success" in result && result.success) {
                setOutput("output" in result ? result.output : "Operation completed successfully.");
            } else {
                setError("error" in result && result.error ? result.error : "Operation failed.");
            }
        } catch (err: any) {
            setError(err.message || "Failed to execute browser operation.");
        } finally {
            setLoading(false);
        }
    };

    const handleClose = async () => {
        try {
            await api.executeBrowserTool({ operation: "close" });
        } catch (err) {
            // Ignore errors on close
        }
        onClose();
    };

    return (
        <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
            {/* Header */}
            <Box sx={{ display: "flex", alignItems: "center", p: 1, flexShrink: 0, borderBottom: "1px solid", borderColor: "divider" }}>
                <Typography variant="caption" sx={{ flexGrow: 1 }}>Browser Automation</Typography>
                <Tooltip title="Close browser">
                    <IconButton size="small" onClick={handleClose}>
                        <CloseIcon fontSize="small" />
                    </IconButton>
                </Tooltip>
            </Box>

            {/* Controls */}
            <Box sx={{ p: 1.5, display: "flex", flexDirection: "column", gap: 1.5, flexShrink: 0, overflowY: "auto" }}>
                <Select
                    size="small"
                    value={operation}
                    onChange={(e) => setOperation(e.target.value)}
                    fullWidth
                >
                    <MenuItem value="navigate">Navigate</MenuItem>
                    <MenuItem value="screenshot">Screenshot</MenuItem>
                    <MenuItem value="get_text">Get Text</MenuItem>
                    <MenuItem value="get_html">Get HTML</MenuItem>
                    <MenuItem value="click">Click</MenuItem>
                    <MenuItem value="fill">Fill</MenuItem>
                    <MenuItem value="eval_js">Evaluate JavaScript</MenuItem>
                    <MenuItem value="close">Close Browser</MenuItem>
                </Select>

                {operation === "navigate" && (
                    <TextField
                        label="URL"
                        size="small"
                        fullWidth
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        placeholder="http://localhost:8000"
                    />
                )}

                {operation === "screenshot" && (
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <Typography variant="caption">Full page:</Typography>
                        <input
                            type="checkbox"
                            checked={fullPage}
                            onChange={(e) => setFullPage(e.target.checked)}
                        />
                    </Box>
                )}

                {(operation === "get_text" || operation === "get_html" || operation === "click" || operation === "fill") && (
                    <TextField
                        label="CSS Selector"
                        size="small"
                        fullWidth
                        value={selector}
                        onChange={(e) => setSelector(e.target.value)}
                        placeholder="body, #id, .class"
                    />
                )}

                {operation === "fill" && (
                    <TextField
                        label="Value"
                        size="small"
                        fullWidth
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        placeholder="Text to fill"
                    />
                )}

                {operation === "eval_js" && (
                    <TextField
                        label="JavaScript Expression"
                        size="small"
                        fullWidth
                        multiline
                        rows={3}
                        value={expression}
                        onChange={(e) => setExpression(e.target.value)}
                        placeholder="document.title"
                    />
                )}

                <Button
                    variant="contained"
                    size="small"
                    onClick={handleExecute}
                    disabled={loading || operation === "close"}
                    startIcon={loading ? <CircularProgress size={14} color="inherit" /> : undefined}
                >
                    {loading ? "Executing..." : "Execute"}
                </Button>
            </Box>

            <Divider />

            {/* Output */}
            <Box sx={{ flexGrow: 1, overflowY: "auto", p: 1.5 }}>
                {error && (
                    <Box sx={{ mb: 1, p: 1, bgcolor: "error.main", color: "error.contrastText", borderRadius: 1 }}>
                        <Typography variant="caption">{error}</Typography>
                    </Box>
                )}
                {output && (
                    <Box sx={{ p: 1, bgcolor: "background.paper", borderRadius: 1, border: "1px solid", borderColor: "divider" }}>
                        <Typography variant="caption" component="pre" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                            {output}
                        </Typography>
                    </Box>
                )}
                {!output && !error && !loading && (
                    <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center", display: "block", mt: 2 }}>
                        Select an operation and execute to see results.
                    </Typography>
                )}
            </Box>
        </Box>
    );
}
