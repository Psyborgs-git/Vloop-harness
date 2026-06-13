/**
 * ViewRegistry - Sidebar for managing generated views, components, and pipelines
 */

import AppsIcon from "@mui/icons-material/Apps";
import CodeIcon from "@mui/icons-material/Code";
import DashboardIcon from "@mui/icons-material/Dashboard";
import ExtensionIcon from "@mui/icons-material/Extension";
import FolderIcon from "@mui/icons-material/Folder";
import SearchIcon from "@mui/icons-material/Search";
import TimelineIcon from "@mui/icons-material/Timeline";
import {
    Box,
    Chip,
    Divider,
    IconButton,
    InputAdornment,
    List,
    ListItem,
    ListItemButton,
    ListItemText,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import { useState } from "react";

interface ViewItem {
    id: string;
    name: string;
    type: "view" | "component" | "pipeline" | "app";
    status: "draft" | "active" | "archived";
    description?: string;
    category?: string;
}

interface ViewCategory {
    name: string;
    items: ViewItem[];
}

export default function ViewRegistry({
    onSelect,
    onClose,
}: {
    onSelect: (item: ViewItem) => void;
    onClose: () => void;
}) {
    const [searchQuery, setSearchQuery] = useState("");
    const [categories] = useState<ViewCategory[]>([
        {
            name: "Apps",
            items: [],
        },
        {
            name: "Views",
            items: [],
        },
        {
            name: "Components",
            items: [],
        },
        {
            name: "Pipelines",
            items: [],
        },
    ]);

    // Load items from API
    useState(() => {
        // TODO: Load from actual API endpoints
        // api.listApps().then(apps => { ... })
        // api.listComponents().then(components => { ... })
        // api.listPipelines().then(pipelines => { ... })
    });

    const filteredCategories = categories.map((category) => ({
        ...category,
        items: category.items.filter(
            (item) =>
                item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                item.description?.toLowerCase().includes(searchQuery.toLowerCase())
        ),
    }));

    const getTypeIcon = (type: ViewItem["type"]) => {
        switch (type) {
            case "app":
                return <AppsIcon fontSize="small" />;
            case "view":
                return <DashboardIcon fontSize="small" />;
            case "component":
                return <ExtensionIcon fontSize="small" />;
            case "pipeline":
                return <TimelineIcon fontSize="small" />;
            default:
                return <CodeIcon fontSize="small" />;
        }
    };

    const getStatusColor = (status: ViewItem["status"]) => {
        switch (status) {
            case "active":
                return "success";
            case "draft":
                return "warning";
            case "archived":
                return "default";
            default:
                return "default";
        }
    };

    return (
        <Box sx={{ height: "100%", display: "flex", flexDirection: "column", bgcolor: "background.paper" }}>
            {/* Header */}
            <Box sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 2 }}>
                    <Typography variant="subtitle2" fontWeight={600}>
                        View Registry
                    </Typography>
                    <Tooltip title="Close">
                        <IconButton size="small" onClick={onClose}>
                            ✕
                        </IconButton>
                    </Tooltip>
                </Box>

                {/* Search */}
                <TextField
                    fullWidth
                    size="small"
                    placeholder="Search views, components, apps..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    InputProps={{
                        startAdornment: (
                            <InputAdornment position="start">
                                <SearchIcon fontSize="small" sx={{ color: "text.secondary" }} />
                            </InputAdornment>
                        ),
                    }}
                    sx={{
                        "& .MuiOutlinedInput-root": {
                            bgcolor: "background.default",
                            borderRadius: 2,
                        },
                    }}
                />
            </Box>

            {/* Categories */}
            <Box sx={{ flexGrow: 1, overflow: "auto" }}>
                {filteredCategories.map((category, idx) => {
                    if (category.items.length === 0) return null;

                    return (
                        <Box key={category.name}>
                            <Box sx={{ px: 2, py: 1, display: "flex", alignItems: "center", gap: 1 }}>
                                <FolderIcon fontSize="small" sx={{ color: "text.secondary" }} />
                                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                                    {category.name}
                                </Typography>
                                <Chip label={category.items.length} size="small" sx={{ height: 16, fontSize: "0.65rem" }} />
                            </Box>

                            <List dense disablePadding>
                                {category.items.map((item) => (
                                    <ListItem key={item.id} disablePadding sx={{ px: 1 }}>
                                        <ListItemButton
                                            onClick={() => onSelect(item)}
                                            sx={{
                                                borderRadius: 1,
                                                px: 2,
                                                py: 1,
                                                "&:hover": {
                                                    bgcolor: "action.hover",
                                                },
                                            }}
                                        >
                                            <Box sx={{ mr: 1.5, color: "text.secondary" }}>{getTypeIcon(item.type)}</Box>
                                            <ListItemText
                                                primary={
                                                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                                                        <Typography variant="body2" noWrap>
                                                            {item.name}
                                                        </Typography>
                                                        <Chip
                                                            label={item.status}
                                                            size="small"
                                                            color={getStatusColor(item.status) as any}
                                                            sx={{ height: 18, fontSize: "0.65rem" }}
                                                        />
                                                    </Box>
                                                }
                                                secondary={
                                                    item.description && (
                                                        <Typography variant="caption" color="text.secondary" noWrap>
                                                            {item.description}
                                                        </Typography>
                                                    )
                                                }
                                            />
                                        </ListItemButton>
                                    </ListItem>
                                ))}
                            </List>

                            {idx < filteredCategories.length - 1 && <Divider />}
                        </Box>
                    );
                })}

                {filteredCategories.every((cat) => cat.items.length === 0) && (
                    <Box sx={{ p: 4, textAlign: "center" }}>
                        <Typography variant="body2" color="text.secondary">
                            No items found
                        </Typography>
                    </Box>
                )}
            </Box>

            {/* Footer */}
            <Box sx={{ p: 2, borderTop: 1, borderColor: "divider" }}>
                <Typography variant="caption" color="text.secondary">
                    {filteredCategories.reduce((sum, cat) => sum + cat.items.length, 0)} items total
                </Typography>
            </Box>
        </Box>
    );
}
