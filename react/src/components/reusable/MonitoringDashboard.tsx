/**
 * MonitoringDashboard — performance monitoring and metrics visualization.
 *
 * Features:
 *  • Display key metrics (execution time, success rates, tool usage)
 *  • Real-time metric updates
 *  • Histogram summaries
 *  • Counter and gauge displays
 */

import RefreshIcon from "@mui/icons-material/Refresh";
import {
    Box,
    Button,
    Card,
    CardContent,
    CardHeader,
    CircularProgress,
    Divider,
    Grid,
    Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import * as api from "./api";

interface MetricsData {
    counters: Array<{ name: string; value: number; tags: Record<string, string> }>;
    gauges: Array<{ name: string; value: number; tags: Record<string, string> }>;
    histograms: Array<{ name: string; summary: Record<string, number>; tags: Record<string, string> }>;
}

interface MetricsSummary {
    total_counters: number;
    total_gauges: number;
    total_histograms: number;
    key_metrics: Record<string, number | Record<string, number>>;
}

interface Props {
    onClose: () => void;
}

export default function MonitoringDashboard({ onClose }: Props) {
    const [metrics, setMetrics] = useState<MetricsData | null>(null);
    const [summary, setSummary] = useState<MetricsSummary | null>(null);
    const [loading, setLoading] = useState(false);

    const fetchMetrics = async () => {
        setLoading(true);
        try {
            const [metricsData, summaryData] = await Promise.all([
                api.getMetrics(),
                api.getMetricsSummary(),
            ]);
            setMetrics(metricsData);
            setSummary(summaryData);
        } catch (err: any) {
            console.error("Failed to fetch metrics:", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchMetrics();
        const interval = setInterval(fetchMetrics, 5000); // Refresh every 5 seconds
        return () => clearInterval(interval);
    }, []);

    return (
        <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
            {/* Header */}
            <Box sx={{ display: "flex", alignItems: "center", p: 1, flexShrink: 0, borderBottom: "1px solid", borderColor: "divider" }}>
                <Typography variant="caption" sx={{ flexGrow: 1 }}>Performance Monitoring</Typography>
                <Button size="small" onClick={fetchMetrics} disabled={loading} startIcon={<RefreshIcon fontSize="small" />}>
                    Refresh
                </Button>
                <Button size="small" onClick={onClose}>Close</Button>
            </Box>

            {/* Content */}
            <Box sx={{ flexGrow: 1, overflowY: "auto", p: 1.5 }}>
                {loading && !metrics && (
                    <Box sx={{ display: "flex", justifyContent: "center", mt: 2 }}>
                        <CircularProgress size={24} />
                    </Box>
                )}

                {summary && (
                    <Grid container spacing={2} sx={{ mb: 2 }}>
                        <Grid item xs={4}>
                            <Card>
                                <CardContent>
                                    <Typography variant="caption" color="text.secondary">Counters</Typography>
                                    <Typography variant="h6">{summary.total_counters}</Typography>
                                </CardContent>
                            </Card>
                        </Grid>
                        <Grid item xs={4}>
                            <Card>
                                <CardContent>
                                    <Typography variant="caption" color="text.secondary">Gauges</Typography>
                                    <Typography variant="h6">{summary.total_gauges}</Typography>
                                </CardContent>
                            </Card>
                        </Grid>
                        <Grid item xs={4}>
                            <Card>
                                <CardContent>
                                    <Typography variant="caption" color="text.secondary">Histograms</Typography>
                                    <Typography variant="h6">{summary.total_histograms}</Typography>
                                </CardContent>
                            </Card>
                        </Grid>
                    </Grid>
                )}

                {metrics && (
                    <>
                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Key Metrics</Typography>
                        <Grid container spacing={2} sx={{ mb: 2 }}>
                            {Object.entries(summary?.key_metrics || {}).map(([key, value]) => (
                                <Grid item xs={6} key={key}>
                                    <Card>
                                        <CardContent>
                                            <Typography variant="caption" color="text.secondary">{key}</Typography>
                                            <Typography variant="body1">
                                                {typeof value === "object" ? JSON.stringify(value) : String(value)}
                                            </Typography>
                                        </CardContent>
                                    </Card>
                                </Grid>
                            ))}
                        </Grid>

                        <Divider sx={{ my: 2 }} />

                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Execution Duration Histograms</Typography>
                        <Grid container spacing={2}>
                            {metrics.histograms
                                .filter(h => h.name.includes("duration"))
                                .map((hist) => (
                                    <Grid item xs={12} sm={6} key={hist.name}>
                                        <Card>
                                            <CardHeader title={hist.name} titleTypographyProps={{ variant: "subtitle2" }} />
                                            <CardContent>
                                                <Typography variant="caption" color="text.secondary">Count: {hist.summary.count}</Typography>
                                                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                                    Mean: {hist.summary.mean.toFixed(2)}ms
                                                </Typography>
                                                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                                    P95: {hist.summary.p95.toFixed(2)}ms
                                                </Typography>
                                                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                                    P99: {hist.summary.p99.toFixed(2)}ms
                                                </Typography>
                                            </CardContent>
                                        </Card>
                                    </Grid>
                                ))}
                        </Grid>

                        <Divider sx={{ my: 2 }} />

                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Tool Execution Counters</Typography>
                        <Grid container spacing={2}>
                            {metrics.counters
                                .filter(c => c.name.includes("tool_executions"))
                                .map((counter) => (
                                    <Grid item xs={6} sm={4} key={counter.name}>
                                        <Card>
                                            <CardContent>
                                                <Typography variant="caption" color="text.secondary">{counter.name}</Typography>
                                                <Typography variant="h6">{counter.value}</Typography>
                                            </CardContent>
                                        </Card>
                                    </Grid>
                                ))}
                        </Grid>
                    </>
                )}
            </Box>
        </Box>
    );
}
