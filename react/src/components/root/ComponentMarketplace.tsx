/**
 * ComponentMarketplace — search and discovery UI for reusable components.
 *
 * Features:
 *  • Search components by name, description, tags
 *  • Filter by category
 *  • View component details
 *  • Clone/activate components
 *  • View component versions
 */

import SearchIcon from "@mui/icons-material/Search";
import {
    Box,
    Button,
    Card,
    CardActions,
    CardContent,
    CardHeader,
    Chip,
    CircularProgress,
    Divider,
    Grid,
    InputAdornment,
    MenuItem,
    Select,
    TextField,
    Typography,
} from "@mui/material";
import { useState } from "react";

import * as api from "./api";

interface Component {
    id: string;
    name: string;
    description: string;
    category: string;
    tags: string[];
    version: string;
    author: string;
    created_at: string;
}

interface Props {
    onClose: () => void;
    onActivate?: (componentId: string) => void;
}

export default function ComponentMarketplace({ onClose, onActivate }: Props) {
    const [search, setSearch] = useState("");
    const [category, setCategory] = useState("all");
    const [components, setComponents] = useState<Component[]>([]);
    const [loading, setLoading] = useState(false);
    const [selectedComponent, setSelectedComponent] = useState<Component | null>(null);

    const handleSearch = async () => {
        setLoading(true);
        try {
            // In a real implementation, this would call a search API
            // For now, use the component list
            const comps = await api.listComponents();
            setComponents(comps as unknown as Component[]);
        } catch (err: any) {
            console.error("Failed to search components:", err);
        } finally {
            setLoading(false);
        }
    };

    const handleActivate = (componentId: string) => {
        if (onActivate) {
            onActivate(componentId);
        }
    };

    const filteredComponents = components.filter((comp) => {
        const matchesSearch =
            comp.name.toLowerCase().includes(search.toLowerCase()) ||
            comp.description.toLowerCase().includes(search.toLowerCase());
        const matchesCategory = category === "all" || comp.category === category;
        return matchesSearch && matchesCategory;
    });

    return (
        <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
            {/* Header */}
            <Box sx={{ display: "flex", alignItems: "center", p: 1, flexShrink: 0, borderBottom: "1px solid", borderColor: "divider" }}>
                <Typography variant="caption" sx={{ flexGrow: 1 }}>Component Marketplace</Typography>
                <Button size="small" onClick={onClose}>Close</Button>
            </Box>

            {/* Search and Filters */}
            <Box sx={{ p: 1.5, display: "flex", gap: 1, flexShrink: 0 }}>
                <TextField
                    size="small"
                    placeholder="Search components..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    fullWidth
                    InputProps={{
                        startAdornment: (
                            <InputAdornment position="start">
                                <SearchIcon fontSize="small" />
                            </InputAdornment>
                        ),
                    }}
                />
                <Select
                    size="small"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    sx={{ minWidth: 120 }}
                >
                    <MenuItem value="all">All Categories</MenuItem>
                    <MenuItem value="general">General</MenuItem>
                    <MenuItem value="nlp">NLP</MenuItem>
                    <MenuItem value="data">Data Processing</MenuItem>
                    <MenuItem value="automation">Automation</MenuItem>
                </Select>
                <Button variant="contained" size="small" onClick={handleSearch} disabled={loading}>
                    {loading ? <CircularProgress size={16} color="inherit" /> : "Search"}
                </Button>
            </Box>

            <Divider />

            {/* Component Grid */}
            <Box sx={{ flexGrow: 1, overflowY: "auto", p: 1.5 }}>
                {filteredComponents.length === 0 && !loading && (
                    <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center", display: "block", mt: 2 }}>
                        No components found. Try a different search or filter.
                    </Typography>
                )}

                <Grid container spacing={2}>
                    {filteredComponents.map((comp) => (
                        <Grid item xs={12} sm={6} md={4} key={comp.id}>
                            <Card
                                sx={{
                                    height: "100%",
                                    display: "flex",
                                    flexDirection: "column",
                                    cursor: "pointer",
                                    "&:hover": { boxShadow: 4 },
                                }}
                                onClick={() => setSelectedComponent(comp)}
                            >
                                <CardHeader
                                    title={comp.name}
                                    subheader={`v${comp.version} • ${comp.author}`}
                                    titleTypographyProps={{ variant: "subtitle2" }}
                                    subheaderTypographyProps={{ variant: "caption" }}
                                />
                                <CardContent sx={{ flexGrow: 1 }}>
                                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                                        {comp.description}
                                    </Typography>
                                    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                                        {comp.tags.slice(0, 3).map((tag) => (
                                            <Chip key={tag} label={tag} size="small" variant="outlined" />
                                        ))}
                                    </Box>
                                </CardContent>
                                <CardActions>
                                    <Button size="small" onClick={(e) => { e.stopPropagation(); handleActivate(comp.id); }}>
                                        Activate
                                    </Button>
                                    <Button size="small" onClick={(e) => { e.stopPropagation(); setSelectedComponent(comp); }}>
                                        Details
                                    </Button>
                                </CardActions>
                            </Card>
                        </Grid>
                    ))}
                </Grid>
            </Box>

            {/* Component Details Panel */}
            {selectedComponent && (
                <Box
                    sx={{
                        position: "absolute",
                        top: 0,
                        right: 0,
                        width: 400,
                        height: "100%",
                        bgcolor: "background.paper",
                        borderLeft: "1px solid",
                        borderColor: "divider",
                        display: "flex",
                        flexDirection: "column",
                        zIndex: 1,
                    }}
                >
                    <Box sx={{ display: "flex", alignItems: "center", p: 1, borderBottom: "1px solid", borderColor: "divider" }}>
                        <Typography variant="subtitle2" sx={{ flexGrow: 1 }}>{selectedComponent.name}</Typography>
                        <Button size="small" onClick={() => setSelectedComponent(null)}>Close</Button>
                    </Box>
                    <Box sx={{ flexGrow: 1, overflowY: "auto", p: 1.5 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                            {selectedComponent.description}
                        </Typography>
                        <Divider sx={{ my: 1 }} />
                        <Typography variant="caption" sx={{ fontWeight: "bold", display: "block", mb: 0.5 }}>
                            Version
                        </Typography>
                        <Typography variant="caption" sx={{ display: "block", mb: 1 }}>
                            {selectedComponent.version}
                        </Typography>
                        <Typography variant="caption" sx={{ fontWeight: "bold", display: "block", mb: 0.5 }}>
                            Author
                        </Typography>
                        <Typography variant="caption" sx={{ display: "block", mb: 1 }}>
                            {selectedComponent.author}
                        </Typography>
                        <Typography variant="caption" sx={{ fontWeight: "bold", display: "block", mb: 0.5 }}>
                            Category
                        </Typography>
                        <Typography variant="caption" sx={{ display: "block", mb: 1 }}>
                            {selectedComponent.category}
                        </Typography>
                        <Typography variant="caption" sx={{ fontWeight: "bold", display: "block", mb: 0.5 }}>
                            Tags
                        </Typography>
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 1 }}>
                            {selectedComponent.tags.map((tag) => (
                                <Chip key={tag} label={tag} size="small" />
                            ))}
                        </Box>
                        <Typography variant="caption" sx={{ fontWeight: "bold", display: "block", mb: 0.5 }}>
                            Created
                        </Typography>
                        <Typography variant="caption" sx={{ display: "block" }}>
                            {new Date(selectedComponent.created_at).toLocaleDateString()}
                        </Typography>
                    </Box>
                    <Box sx={{ p: 1, borderTop: "1px solid", borderColor: "divider" }}>
                        <Button
                            variant="contained"
                            fullWidth
                            size="small"
                            onClick={() => {
                                handleActivate(selectedComponent.id);
                                setSelectedComponent(null);
                            }}
                        >
                            Activate Component
                        </Button>
                    </Box>
                </Box>
            )}
        </Box>
    );
}
