import React from 'react';
import { Button, Typography, Paper } from '@mui/material';

export const ManifestInstaller: React.FC = () => {
    const handleInstall = async () => {
        // Mocking the IPC / Backend call for HITL approval of Extension Manifests
        const response = await fetch('/api/sandbox/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sandbox_type: 'Local',
                command: 'echo',
                args: ['Manifest installed with permissions']
            })
        });
        const result = await response.json();
        alert(result.stdout);
    };

    return (
        <Paper sx={{ p: 2, mt: 2 }}>
            <Typography variant="h6">Install Extension (VSCode-style Manifest)</Typography>
            <Typography variant="body2" sx={{ mb: 2 }}>
                Load a package.json equivalent to request sandbox boundaries securely.
            </Typography>
            <Button variant="contained" color="primary" onClick={handleInstall}>
                Simulate Manifest Installation (HITL Approval)
            </Button>
        </Paper>
    );
};
