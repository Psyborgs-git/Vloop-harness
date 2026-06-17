import { useState } from 'react';

interface ExecutionFeedProps {
  devMode: boolean;
  workflowState: any;
}

export default function ExecutionFeed({ devMode, workflowState }: ExecutionFeedProps) {
  const [activeTab, setActiveTab] = useState<'proxy' | 'diff' | 'logs'>('proxy');

  // Find running or most recently completed node for context
  let activeNode = null;
  if (workflowState && workflowState.nodes) {
    activeNode = workflowState.nodes.find((n: any) => n.status === 'RUNNING') 
      || [...workflowState.nodes].reverse().find((n: any) => n.status === 'COMPLETED' || n.status === 'FAILED');
  }

  if (!devMode) {
    return (
      <div style={{ padding: '24px', height: '100%', overflowY: 'auto' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600, marginTop: 0, marginBottom: '24px' }}>Activity Feed</h2>
        
        {workflowState ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {workflowState.nodes.map((node: any, idx: number) => {
              if (node.status === 'PENDING') return null;
              
              let color = 'var(--status-green)';
              if (node.status === 'RUNNING') color = 'var(--accent-blue)';
              if (node.status === 'FAILED') color = 'var(--status-red)';

              let payload: any = {};
              try { payload = JSON.parse(node.payload || "{}"); } catch(e) {}
              
              return (
                <div key={idx} style={{ display: 'flex', gap: '12px', opacity: node.status === 'RUNNING' ? 1 : 0.7 }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: color, marginTop: '6px', flexShrink: 0 }} />
                  <div>
                    <div style={{ fontSize: '14px', color: 'var(--text-primary)' }}>
                      {node.name === 'harness_coder' && node.status === 'COMPLETED' && "Agent successfully wrote code pipeline."}
                      {node.name === 'harness_coder' && node.status === 'RUNNING' && "Agent is writing code..."}
                      {node.name === 'worker_sandbox' && node.status === 'COMPLETED' && "Executed data pipeline in secure sandbox."}
                      {node.name === 'worker_sandbox' && node.status === 'RUNNING' && "Executing data pipeline in secure sandbox..."}
                      {node.name === 'serve_ui' && node.status === 'COMPLETED' && (
                        <span>UI Served at <a href={payload.served_url || "#"} style={{color: 'var(--accent-blue)'}} target="_blank" rel="noreferrer">{payload.served_url || "localhost"}</a></span>
                      )}
                      {node.name === 'serve_ui' && node.status === 'RUNNING' && "Serving UI Mini-App..."}
                      {node.status === 'FAILED' && `Failed: ${node.name}`}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ color: 'var(--text-muted)' }}>Waiting for activity...</div>
        )}
      </div>
    );
  }

  // Developer Mode View
  let rawLogs = "";
  let gitDiff = "";
  if (activeNode) {
    try {
      const payload = JSON.parse(activeNode.payload || "{}");
      rawLogs = payload.logs || "No logs available.";
      gitDiff = payload.git_diff || "No git diff available.";
    } catch(e) {}
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-panel)' }}>
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border-muted)', padding: '0 16px', marginTop: '16px' }}>
        <button 
          onClick={() => setActiveTab('proxy')}
          style={{ 
            background: 'none', border: 'none', color: activeTab === 'proxy' ? 'var(--text-primary)' : 'var(--text-muted)',
            borderBottom: activeTab === 'proxy' ? '2px solid var(--accent-purple)' : '2px solid transparent',
            padding: '8px 16px', fontSize: '13px', fontWeight: 500
          }}>
          Proxy Intercept
        </button>
        <button 
          onClick={() => setActiveTab('diff')}
          style={{ 
            background: 'none', border: 'none', color: activeTab === 'diff' ? 'var(--text-primary)' : 'var(--text-muted)',
            borderBottom: activeTab === 'diff' ? '2px solid var(--accent-purple)' : '2px solid transparent',
            padding: '8px 16px', fontSize: '13px', fontWeight: 500
          }}>
          Workspace Diff
        </button>
        <button 
          onClick={() => setActiveTab('logs')}
          style={{ 
            background: 'none', border: 'none', color: activeTab === 'logs' ? 'var(--text-primary)' : 'var(--text-muted)',
            borderBottom: activeTab === 'logs' ? '2px solid var(--accent-purple)' : '2px solid transparent',
            padding: '8px 16px', fontSize: '13px', fontWeight: 500
          }}>
          Sandbox Logs
        </button>
      </div>

      <div style={{ flexGrow: 1, padding: '16px', overflowY: 'auto', fontFamily: 'monospace', fontSize: '12px', color: '#a8b2d1', whiteSpace: 'pre-wrap' }}>
        {activeTab === 'proxy' && (
          <pre style={{ margin: 0 }}>{JSON.stringify({
            "model": "gpt-4o-mini",
            "messages": [
              {"role": "system", "content": "You are a helpful coding assistant routed through VLoop LiteLLM proxy."},
              {"role": "user", "content": "Current node execution..."}
            ],
            "note": "Live proxy interception view."
          }, null, 2)}</pre>
        )}
        
        {activeTab === 'diff' && (
          <div style={{ color: 'var(--status-green)' }}>
            {gitDiff}
          </div>
        )}

        {activeTab === 'logs' && (
          <div>
            {rawLogs}
          </div>
        )}
      </div>
    </div>
  );
}
