import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  Stack,
  CircularProgress,





} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import AddIcon from '@mui/icons-material/Add';
import WorkflowEditor from './WorkflowEditor';

interface Pipeline {
  id: string;
  name: string;
  description: string;
  status: string;
}

export default function PipelineManager() {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const loading = false;

  const [showEditor, setShowEditor] = useState(false);

  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL || "";
    fetch(`${apiUrl}/api/pipelines/templates`)
      .then(res => {
        if (!res.ok) throw new Error("Network response was not ok");
        return res.json();
      })
      .then(data => {
        if (Array.isArray(data)) {
          setPipelines(data);
        }
      })
      .catch(error => {
        console.error("Failed to fetch pipelines:", error);
        setPipelines([
          { id: '1', name: 'Sample Workflow', description: 'Test', status: 'ready' }
        ]);
      });
  }, []);

  if (showEditor) {
    return (
      <Box sx={{ p: 4, height: '80vh', width: '100%' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h4">Workflow Editor</Typography>
          <Button variant="outlined" onClick={() => setShowEditor(false)}>Back</Button>
        </Box>
        <Paper variant="outlined" sx={{ height: '100%', width: '100%' }}>
          <WorkflowEditor />
        </Paper>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 4, maxWidth: 1200, margin: '0 auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h4">Pipelines / Workflows</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setShowEditor(true)}>
          Create Workflow
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
                <TableCell>Status</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pipelines.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{p.name}</TableCell>
                  <TableCell>{p.description}</TableCell>
                  <TableCell>
                    <Chip label={p.status} size="small" />
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={1} justifyContent="flex-end">
                      <IconButton color="success" size="small" title="Run">
                        <PlayArrowIcon />
                      </IconButton>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
