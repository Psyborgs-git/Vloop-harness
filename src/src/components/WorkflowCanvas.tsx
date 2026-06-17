import { useCallback, useEffect } from 'react';
import { ReactFlow, Controls, Background, useNodesState, useEdgesState, addEdge } from '@xyflow/react';
import type { Connection, Edge, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { invoke } from '@tauri-apps/api/core';

import TaskNode from './TaskNode';

const nodeTypes = {
  taskNode: TaskNode,
};

interface WorkflowCanvasProps {
  workflowState: any;
}

export default function WorkflowCanvas({ workflowState }: WorkflowCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    if (!workflowState || !workflowState.nodes) return;

    // Layout the nodes dynamically in a vertical line for simplicity
    const newNodes: Node[] = workflowState.nodes.map((n: any, idx: number) => ({
      id: n.node_id,
      type: 'taskNode',
      position: { x: 250, y: 50 + idx * 150 },
      data: {
        label: n.name,
        status: n.status,
        summary: n.payload ? JSON.parse(n.payload).objective : '',
        onRewind: async () => {
          try {
            await invoke('rewind_workflow', { workflowId: workflowState.workflow_id, targetNodeId: n.node_id });
          } catch (e) {
            console.error('Rewind failed:', e);
          }
        }
      }
    }));

    // Build edges based on dependencies
    const newEdges: Edge[] = [];
    workflowState.nodes.forEach((n: any) => {
      const deps = JSON.parse(n.dependencies || "[]");
      deps.forEach((dep: string) => {
        newEdges.push({
          id: `e${dep}-${n.node_id}`,
          source: dep,
          target: n.node_id,
          animated: n.status === 'RUNNING',
          style: { stroke: n.status === 'RUNNING' ? 'var(--accent-blue)' : 'var(--border-muted)' }
        });
      });
    });

    setNodes(newNodes);
    setEdges(newEdges);
  }, [workflowState, setNodes, setEdges]);

  const onConnect = useCallback(
    (params: Edge | Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

  return (
    <div style={{ width: '100%', height: '100%', background: 'var(--bg-dark)' }}>
      {nodes.length === 0 && (
        <div style={{ padding: '24px', color: 'var(--text-muted)' }}>Waiting for workflow tasks...</div>
      )}
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
