import { useCallback, useState } from "react";
import ReactFlow, {
  addEdge,
  Background,
  Connection,
  Controls,
  Edge,
  MiniMap,
  Node,
  useEdgesState,
  useNodesState,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Box,
  Button,
  TextField,
  Typography,
  Paper,
  Snackbar,
  Alert,
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import SaveIcon from "@mui/icons-material/Save";
import * as inferenceApi from "../api/inference";

const initialNodes: Node[] = [
  {
    id: "1",
    type: "input",
    data: { label: "Input" },
    position: { x: 100, y: 100 },
  },
  {
    id: "2",
    data: { label: "Process" },
    position: { x: 300, y: 100 },
  },
  {
    id: "3",
    type: "output",
    data: { label: "Output" },
    position: { x: 500, y: 100 },
  },
];

const initialEdges: Edge[] = [
  { id: "e1-2", source: "1", target: "2" },
  { id: "e2-3", source: "2", target: "3" },
];

export default function PipelineStudioView() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [pipelineName, setPipelineName] = useState("my_pipeline");
  const [runInput, setRunInput] = useState("{}");
  const [snack, setSnack] = useState<{ msg: string; sev: "success" | "error" } | null>(null);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const savePipeline = async () => {
    try {
      const definition = {
        nodes: nodes.map((n) => ({ id: n.id, label: n.data.label, type: n.type })),
        edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
      };
      await fetch("http://localhost:47201/pipeline/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: pipelineName, definition }),
      });
      setSnack({ msg: "Pipeline saved!", sev: "success" });
    } catch (e) {
      setSnack({ msg: String(e), sev: "error" });
    }
  };

  const runPipeline = async () => {
    try {
      const inputs = JSON.parse(runInput || "{}");
      const result = await inferenceApi.runPipeline(pipelineName, inputs);
      setSnack({ msg: `Result: ${JSON.stringify(result.result)}`, sev: "success" });
    } catch (e) {
      setSnack({ msg: String(e), sev: "error" });
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Paper
        elevation={0}
        sx={{ p: 1, borderBottom: 1, borderColor: "divider", display: "flex", gap: 1, alignItems: "center" }}
      >
        <TextField
          label="Pipeline name"
          value={pipelineName}
          onChange={(e) => setPipelineName(e.target.value)}
          size="small"
          sx={{ width: 180 }}
        />
        <Button
          size="small"
          variant="outlined"
          startIcon={<SaveIcon />}
          onClick={savePipeline}
        >
          Save
        </Button>
        <TextField
          label="Run inputs (JSON)"
          value={runInput}
          onChange={(e) => setRunInput(e.target.value)}
          size="small"
          sx={{ width: 200 }}
        />
        <Button
          size="small"
          variant="contained"
          startIcon={<PlayArrowIcon />}
          onClick={runPipeline}
        >
          Run
        </Button>
      </Paper>
      <Box sx={{ flex: 1 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </Box>
      <Snackbar
        open={!!snack}
        autoHideDuration={4000}
        onClose={() => setSnack(null)}
      >
        <Alert severity={snack?.sev ?? "info"} onClose={() => setSnack(null)}>
          {snack?.msg}
        </Alert>
      </Snackbar>
    </Box>
  );
}
