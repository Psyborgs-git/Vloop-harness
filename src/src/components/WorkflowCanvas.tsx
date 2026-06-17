import { useCallback } from 'react';
import { ReactFlow, Controls, Background, useNodesState, useEdgesState, addEdge } from '@xyflow/react';
import type { Connection, Edge, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import TaskNode from './TaskNode';

const nodeTypes = {
  taskNode: TaskNode,
};

const initialNodes: Node[] = [
  { 
    id: '1', 
    type: 'taskNode', 
    position: { x: 250, y: 50 }, 
    data: { label: 'Generate Code Pipeline', status: 'COMPLETED', summary: 'Aider generated main.py using LiteLLM proxy.' } 
  },
  { 
    id: '2', 
    type: 'taskNode', 
    position: { x: 250, y: 200 }, 
    data: { label: 'Execute Sandbox', status: 'RUNNING', summary: 'Processing CSV data in isolated Firecracker VM.' } 
  },
  { 
    id: '3', 
    type: 'taskNode', 
    position: { x: 250, y: 350 }, 
    data: { label: 'Serve UI', status: 'PENDING', summary: 'Waiting for execution to finish.' } 
  },
];

const initialEdges: Edge[] = [
  { id: 'e1-2', source: '1', target: '2', animated: true, style: { stroke: 'var(--accent-blue)' } },
  { id: 'e2-3', source: '2', target: '3', style: { stroke: 'var(--border-muted)' } },
];

export default function WorkflowCanvas() {
  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (params: Edge | Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

  return (
    <div style={{ width: '100%', height: '100%', background: 'var(--bg-dark)' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView
        colorMode="dark"
      >
        <Background color="var(--border-muted)" gap={16} />
        <Controls style={{ fill: 'var(--text-primary)', backgroundColor: 'var(--bg-panel)' }} />
      </ReactFlow>
    </div>
  );
}
