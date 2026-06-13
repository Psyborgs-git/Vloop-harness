/**
 * AgentRunTimeline - Timeline visualization for agent run steps
 */

import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import {
    Box,
    Chip,
    Paper,
    Step,
    StepConnector,
    StepLabel,
    Stepper,
    Typography,
} from "@mui/material";
import { useState } from "react";

interface AgentRunStep {
    id: string;
    step_type: "plan" | "tool_call" | "dspy_call" | "file_write" | "validation";
    status: "pending" | "running" | "completed" | "failed";
    description: string;
    duration_ms?: number;
    error?: string;
    timestamp: string;
    metadata?: Record<string, any>;
}

interface AgentRunTimelineProps {
    runId: string;
    onClose?: () => void;
}

export default function AgentRunTimeline({ runId, onClose }: AgentRunTimelineProps) {
    const [steps, setSteps] = useState<AgentRunStep[]>([]);
    const [loading, setLoading] = useState(true);

    useState(() => {
        // TODO: Load actual steps from API
        // api.getAgentRunSteps(runId).then(data => {
        //   setSteps(data);
        //   setLoading(false);
        // });

        // Mock data for now
        setSteps([
            {
                id: "1",
                step_type: "plan",
                status: "completed",
                description: "Generated execution plan",
                duration_ms: 1500,
                timestamp: new Date(Date.now() - 10000).toISOString(),
            },
            {
                id: "2",
                step_type: "tool_call",
                status: "completed",
                description: "Executed terminal command: ls -la",
                duration_ms: 200,
                timestamp: new Date(Date.now() - 8000).toISOString(),
            },
            {
                id: "3",
                step_type: "dspy_call",
                status: "completed",
                description: "DSPy reasoning module",
                duration_ms: 3000,
                timestamp: new Date(Date.now() - 5000).toISOString(),
            },
            {
                id: "4",
                step_type: "file_write",
                status: "running",
                description: "Writing file: src/components/NewComponent.tsx",
                timestamp: new Date(Date.now() - 2000).toISOString(),
            },
            {
                id: "5",
                step_type: "validation",
                status: "pending",
                description: "Validate React component",
                timestamp: new Date().toISOString(),
            },
        ]);
        setLoading(false);
    });

    const getStepIcon = (step: AgentRunStep) => {
        switch (step.status) {
            case "completed":
                return <CheckCircleIcon color="success" />;
            case "failed":
                return <ErrorIcon color="error" />;
            case "running":
                return <PlayArrowIcon color="primary" />;
            case "pending":
                return <HourglassEmptyIcon color="disabled" />;
            default:
                return <HourglassEmptyIcon color="disabled" />;
        }
    };

    const getStepTypeColor = (type: AgentRunStep["step_type"]) => {
        switch (type) {
            case "plan":
                return "info";
            case "tool_call":
                return "warning";
            case "dspy_call":
                return "secondary";
            case "file_write":
                return "success";
            case "validation":
                return "primary";
            default:
                return "default";
        }
    };

    const formatDuration = (ms?: number) => {
        if (!ms) return "";
        if (ms < 1000) return `${ms}ms`;
        return `${(ms / 1000).toFixed(2)}s`;
    };

    const formatTimestamp = (timestamp: string) => {
        const date = new Date(timestamp);
        return date.toLocaleTimeString();
    };

    if (loading) {
        return (
            <Box sx={{ p: 3, textAlign: "center" }}>
                <Typography variant="body2" color="text.secondary">
                    Loading timeline...
                </Typography>
            </Box>
        );
    }

    return (
        <Box sx={{ height: "100%", display: "flex", flexDirection: "column", bgcolor: "background.paper" }}>
            {/* Header */}
            <Box sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <Typography variant="subtitle2" fontWeight={600}>
                        Agent Run Timeline
                    </Typography>
                    {onClose && (
                        <Typography
                            variant="caption"
                            color="primary"
                            sx={{ cursor: "pointer" }}
                            onClick={onClose}
                        >
                            Close
                        </Typography>
                    )}
                </Box>
                <Typography variant="caption" color="text.secondary">
                    Run ID: {runId}
                </Typography>
            </Box>

            {/* Timeline */}
            <Box sx={{ flexGrow: 1, overflow: "auto", p: 2 }}>
                <Stepper activeStep={steps.findIndex((s) => s.status === "running")} orientation="vertical">
                    {steps.map((step) => (
                        <Step key={step.id} completed={step.status === "completed"}>
                            <StepConnector />
                            <StepLabel
                                icon={getStepIcon(step)}
                                sx={{
                                    "& .MuiStepLabel-label": {
                                        fontSize: "0.875rem",
                                    },
                                }}
                            >
                                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                                    <Typography variant="body2" fontWeight={500}>
                                        {step.description}
                                    </Typography>
                                    <Chip
                                        label={step.step_type.replace("_", " ")}
                                        size="small"
                                        color={getStepTypeColor(step.step_type) as any}
                                        sx={{ height: 18, fontSize: "0.65rem" }}
                                    />
                                </Box>
                                <Box sx={{ display: "flex", alignItems: "center", gap: 2, mt: 0.5 }}>
                                    <Typography variant="caption" color="text.secondary">
                                        {formatTimestamp(step.timestamp)}
                                    </Typography>
                                    {step.duration_ms && (
                                        <Typography variant="caption" color="text.secondary">
                                            · {formatDuration(step.duration_ms)}
                                        </Typography>
                                    )}
                                </Box>
                                {step.error && (
                                    <Paper
                                        variant="outlined"
                                        sx={{
                                            mt: 1,
                                            p: 1,
                                            bgcolor: "error.dark",
                                            borderColor: "error.main",
                                        }}
                                    >
                                        <Typography variant="caption" color="error.light">
                                            {step.error}
                                        </Typography>
                                    </Paper>
                                )}
                                {step.metadata && Object.keys(step.metadata).length > 0 && (
                                    <Paper
                                        variant="outlined"
                                        sx={{
                                            mt: 1,
                                            p: 1,
                                            bgcolor: "background.default",
                                        }}
                                    >
                                        <Typography variant="caption" color="text.secondary">
                                            {JSON.stringify(step.metadata, null, 2)}
                                        </Typography>
                                    </Paper>
                                )}
                            </StepLabel>
                        </Step>
                    ))}
                </Stepper>
            </Box>

            {/* Footer */}
            <Box sx={{ p: 2, borderTop: 1, borderColor: "divider" }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <Typography variant="caption" color="text.secondary">
                        {steps.length} steps total
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                        {steps.filter((s) => s.status === "completed").length} completed
                    </Typography>
                </Box>
            </Box>
        </Box>
    );
}
