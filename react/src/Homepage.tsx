import { useEffect, useState } from "react";
import { Box, Typography, Button, CircularProgress } from "@mui/material";
import { useNavigate } from "react-router-dom";

interface ViewComponent {
    id: string;
    name: string;
    description?: string;
}

export default function Homepage() {
    const [components, setComponents] = useState<ViewComponent[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const navigate = useNavigate();

    useEffect(() => {
        const fetchComponents = async () => {
            try {
                const apiUrl = import.meta.env.VITE_API_URL || "";
                const base = apiUrl.replace(/\/+$/, '');
                // Try fetching from the views API
                const response = await fetch(`${base}/api/views`);

                if (!response.ok) {
                    throw new Error(`Failed to fetch components: ${response.status} ${response.statusText}`);
                }

                const data = await response.json();
                // Depending on the exact shape of /api/views, it might be an array or inside a data field
                const list = Array.isArray(data) ? data : (data.items || data.data || []);
                setComponents(list);
            } catch (err: any) {
                console.error("Error fetching homepage components:", err);
                setError(err.message || "Failed to load components");
            } finally {
                setLoading(false);
            }
        };

        fetchComponents();
    }, []);

    if (loading) {
        return (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 2 }}>
                <CircularProgress />
                <Typography color="text.secondary">Loading available views...</Typography>
            </Box>
        );
    }

    if (error) {
        return (
            <Box sx={{ p: 4 }}>
                <Typography variant="h5" color="error">Error Loading Views</Typography>
                <Typography>{error}</Typography>
                <Button variant="outlined" sx={{ mt: 2 }} onClick={() => window.location.reload()}>
                    Retry
                </Button>
            </Box>
        );
    }

    return (
        <Box sx={{ p: 4, maxWidth: 800, margin: '0 auto' }}>
            <Typography variant="h4" gutterBottom>
                Available Views
            </Typography>
            <Typography variant="body1" color="text.secondary" paragraph>
                Select a view to load dynamically.
            </Typography>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 4 }}>
                {components.length === 0 ? (
                    <Typography color="text.secondary">No views found.</Typography>
                ) : (
                    components.map((comp) => (
                        <Box
                            key={comp.id}
                            sx={{
                                p: 2,
                                border: '1px solid',
                                borderColor: 'divider',
                                borderRadius: 1,
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center'
                            }}
                        >
                            <Box>
                                <Typography variant="h6">{comp.name || comp.id}</Typography>
                                {comp.description && (
                                    <Typography variant="body2" color="text.secondary">
                                        {comp.description}
                                    </Typography>
                                )}
                            </Box>
                            <Button
                                variant="contained"
                                onClick={() => navigate(`/${comp.id}`)}
                            >
                                Open
                            </Button>
                        </Box>
                    ))
                )}
            </Box>
        </Box>
    );
}
