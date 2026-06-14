import { useEffect, useState } from 'react';
import {
    Box, Typography, Button, Table, TableBody, TableCell, TableContainer,
    TableHead, TableRow, Paper, Dialog, DialogTitle, DialogContent,
    DialogActions, TextField, IconButton, Stack, Chip, CircularProgress
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import AddIcon from '@mui/icons-material/Add';

const invoke = async (cmd: string, args?: Record<string, any>) => {
    if ((window as any).__TAURI__ && (window as any).__TAURI__.core) {
        return await (window as any).__TAURI__.core.invoke(cmd, args);
    }
    console.warn('Tauri not available, mock returning for:', cmd);
    return null;
};

interface ProcessConfig {
    command: string;
    args: string[];
    env_vars: string;
    cwd: string;
}

interface ProcessDetail {
    id: string;
    name: string;
    description: string;
    config: ProcessConfig;
    status: string;
    created_at: string;
    updated_at: string;
}

export default function ProcessManager() {
    const [processes, setProcesses] = useState<ProcessDetail[]>([]);
    const [loading, setLoading] = useState(true);
    const [openDialog, setOpenDialog] = useState(false);
    const [editingProcess, setEditingProcess] = useState<ProcessDetail | null>(null);

    // Form state
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [command, setCommand] = useState('');
    const [argsStr, setArgsStr] = useState('');
    const [envVars, setEnvVars] = useState('{}');
    const [cwd, setCwd] = useState('');

    useEffect(() => {
        loadProcesses();
    }, []);

    const loadProcesses = async () => {
        setLoading(true);
        try {
            const data = await invoke('list_processes');
            if (data) {
                setProcesses(data as ProcessDetail[]);
            }
        } catch (e) {
            console.error('Failed to load processes:', e);
        } finally {
            setLoading(false);
        }
    };

    const handleOpenDialog = (process?: ProcessDetail) => {
        if (process) {
            setEditingProcess(process);
            setName(process.name);
            setDescription(process.description);
            setCommand(process.config.command);
            setArgsStr(process.config.args.join(' '));
            setEnvVars(process.config.env_vars);
            setCwd(process.config.cwd);
        } else {
            setEditingProcess(null);
            setName('');
            setDescription('');
            setCommand('');
            setArgsStr('');
            setEnvVars('{}');
            setCwd('');
        }
        setOpenDialog(true);
    };

    const handleCloseDialog = () => {
        setOpenDialog(false);
    };

    const handleSave = async () => {
        const config: ProcessConfig = {
            command,
            args: argsStr.split(' ').filter(a => a.trim() !== ''),
            env_vars: envVars,
            cwd
        };

        try {
            if (editingProcess) {
                await invoke('update_process', { id: editingProcess.id, name, description, config });
            } else {
                await invoke('create_process', { name, description, config });
            }
            handleCloseDialog();
            loadProcesses();
        } catch (e) {
            console.error('Failed to save process:', e);
            alert(`Failed to save: ${e}`);
        }
    };

    const handleDelete = async (id: string) => {
        if (!confirm('Are you sure you want to delete this process?')) return;
        try {
            await invoke('delete_process', { id });
            loadProcesses();
        } catch (e) {
            console.error('Failed to delete process:', e);
        }
    };

    const handleStart = async (id: string) => {
        try {
            await invoke('start_process', { id });
            loadProcesses();
        } catch (e) {
            console.error('Failed to start process:', e);
        }
    };

    const handleStop = async (id: string) => {
        try {
            await invoke('stop_process', { id });
            loadProcesses();
        } catch (e) {
            console.error('Failed to stop process:', e);
        }
    };

    return (
        <Box sx={{ p: 4, maxWidth: 1200, margin: '0 auto' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
                <Typography variant="h4">Process Manager</Typography>
                <Button variant="contained" startIcon={<AddIcon />} onClick={() => handleOpenDialog()}>
                    Add Process
                </Button>
            </Box>

            {loading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                    <CircularProgress />
                </Box>
            ) : (
                <TableContainer component={Paper} variant="outlined">
                    <Table>
                        <TableHead>
                            <TableRow>
                                <TableCell>Name</TableCell>
                                <TableCell>Description</TableCell>
                                <TableCell>Command</TableCell>
                                <TableCell>Status</TableCell>
                                <TableCell align="right">Actions</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {processes.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={5} align="center">No processes configured.</TableCell>
                                </TableRow>
                            ) : (
                                processes.map((p) => (
                                    <TableRow key={p.id}>
                                        <TableCell>{p.name}</TableCell>
                                        <TableCell>{p.description}</TableCell>
                                        <TableCell><code>{p.config.command}</code></TableCell>
                                        <TableCell>
                                            <Chip 
                                                label={p.status} 
                                                color={p.status === 'running' ? 'success' : 'default'} 
                                                size="small" 
                                            />
                                        </TableCell>
                                        <TableCell align="right">
                                            <Stack direction="row" spacing={1} justifyContent="flex-end">
                                                {p.status !== 'running' ? (
                                                    <IconButton color="success" size="small" onClick={() => handleStart(p.id)} title="Start">
                                                        <PlayArrowIcon />
                                                    </IconButton>
                                                ) : (
                                                    <IconButton color="warning" size="small" onClick={() => handleStop(p.id)} title="Stop">
                                                        <StopIcon />
                                                    </IconButton>
                                                )}
                                                <IconButton color="primary" size="small" onClick={() => handleOpenDialog(p)} title="Edit">
                                                    <EditIcon />
                                                </IconButton>
                                                <IconButton color="error" size="small" onClick={() => handleDelete(p.id)} title="Delete">
                                                    <DeleteIcon />
                                                </IconButton>
                                            </Stack>
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
            )}

            <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="md" fullWidth>
                <DialogTitle>{editingProcess ? 'Edit Process' : 'Add Process'}</DialogTitle>
                <DialogContent dividers>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <TextField 
                            label="Name" 
                            fullWidth 
                            value={name} 
                            onChange={(e) => setName(e.target.value)} 
                        />
                        <TextField 
                            label="Description" 
                            fullWidth 
                            value={description} 
                            onChange={(e) => setDescription(e.target.value)} 
                        />
                        <TextField 
                            label="Command (e.g. python, docker)" 
                            fullWidth 
                            value={command} 
                            onChange={(e) => setCommand(e.target.value)} 
                        />
                        <TextField 
                            label="Arguments (space separated)" 
                            fullWidth 
                            value={argsStr} 
                            onChange={(e) => setArgsStr(e.target.value)} 
                        />
                        <TextField 
                            label="Working Directory (CWD)" 
                            fullWidth 
                            value={cwd} 
                            onChange={(e) => setCwd(e.target.value)} 
                        />
                        <TextField 
                            label="Environment Variables (JSON format)" 
                            fullWidth 
                            multiline 
                            rows={3} 
                            value={envVars} 
                            onChange={(e) => setEnvVars(e.target.value)} 
                            helperText='Example: {"PORT": "8080"}'
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseDialog}>Cancel</Button>
                    <Button variant="contained" onClick={handleSave}>Save</Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
}
