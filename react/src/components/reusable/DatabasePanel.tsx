/**
 * DatabasePanel — database inspection and query panel.
 *
 * Features:
 *  • View database schema
 *  • Execute read queries
 *  • Execute write queries (with confirmation)
 *  • View query results
 *  • Parameterized query support
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

export default function DatabasePanel({ onClose }: Props) {
    const [operation, setOperation] = useState("schema_info");
    const [sql, setSql] = useState("");
    const [params, setParams] = useState("");
    const [loading, setLoading] = useState(false);
    const [output, setOutput] = useState("");
    const [error, setError] = useState("");

    const handleExecute = async () => {
        setLoading(true);
        setError("");
        setOutput("");

        try {
            const parsedParams = params ? JSON.parse(params) : {};

            const result = await api.executeDatabase({
                operation: operation as any,
                sql,
                params: parsedParams,
            });

            if ("success" in result && result.success) {
                setOutput("output" in result ? result.output : "Operation completed successfully.");
            } else {
                setError("error" in result && result.error ? result.error : "Operation failed.");
            }
        } catch (err: any) {
            if (err.message.includes("requires_confirmation")) {
                setError("This operation requires confirmation. Please use the confirmation dialog.");
            } else {
                setError(err.message || "Failed to execute database operation.");
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
            {/* Header */}
            <Box sx={{ display: "flex", alignItems: "center", p: 1, flexShrink: 0, borderBottom: "1px solid", borderColor: "divider" }}>
                <Typography variant="caption" sx={{ flexGrow: 1 }}>Database Inspection</Typography>
                <Tooltip title="Close panel">
                    <IconButton size="small" onClick={onClose}>
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
                    <MenuItem value="schema_info">Schema Info</MenuItem>
                    <MenuItem value="query_read">Query (Read)</MenuItem>
                    <MenuItem value="query_write">Query (Write)</MenuItem>
                </Select>

                {operation !== "schema_info" && (
                    <TextField
                        label="SQL Query"
                        size="small"
                        fullWidth
                        multiline
                        rows={4}
                        value={sql}
                        onChange={(e) => setSql(e.target.value)}
                        placeholder="SELECT * FROM table_name WHERE id = :id"
                    />
                )}

                {operation !== "schema_info" && (
                    <TextField
                        label="Parameters (JSON)"
                        size="small"
                        fullWidth
                        multiline
                        rows={2}
                        value={params}
                        onChange={(e) => setParams(e.target.value)}
                        placeholder='{"id": 1}'
                    />
                )}

                <Button
                    variant="contained"
                    size="small"
                    onClick={handleExecute}
                    disabled={loading}
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
                        {operation === "schema_info"
                            ? "Click Execute to view database schema."
                            : "Enter a SQL query and parameters, then click Execute."}
                    </Typography>
                )}
            </Box>
        </Box>
    );
}
