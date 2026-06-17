import React, { useState, useEffect, Suspense } from 'react';
import { invoke } from '@tauri-apps/api/core';
import Header from './components/Header';

// Code splitting: Lazy load heavy components
const WorkflowCanvas = React.lazy(() => import('./components/WorkflowCanvas'));
const ExecutionFeed = React.lazy(() => import('./components/ExecutionFeed'));

function App() {
  const [devMode, setDevMode] = useState(false);
  const [workflowState, setWorkflowState] = useState<any>(null);

  useEffect(() => {
    const pollState = async () => {
      try {
        const stateStr = await invoke<string>('get_workflow_state', { workflowId: null });
        if (stateStr) {
          setWorkflowState(JSON.parse(stateStr));
        }
      } catch (e) {
        console.error("Failed to poll workflow state:", e);
      }
    };

    pollState(); // initial fetch
    const interval = setInterval(pollState, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ 
      display: 'grid', 
      gridTemplateRows: '60px 1fr', 
      height: '100vh', 
      width: '100vw',
      background: 'var(--bg-dark)'
    }}>
      {/* Top Header */}
      <Header devMode={devMode} setDevMode={setDevMode} />

      {/* Split Pane Canvas */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: '60% 40%', 
        height: '100%', 
        overflow: 'hidden' 
      }}>
        
        {/* Left Pane: Interactive DAG */}
        <div style={{ borderRight: '1px solid var(--border-muted)', position: 'relative' }}>
          <Suspense fallback={<div style={{ padding: '24px', color: 'var(--text-muted)' }}>Loading Canvas...</div>}>
            <WorkflowCanvas workflowState={workflowState} />
          </Suspense>
        </div>

        {/* Right Pane: Execution Feed / Dev View */}
        <div>
          <Suspense fallback={<div style={{ padding: '24px', color: 'var(--text-muted)' }}>Loading Feed...</div>}>
            <ExecutionFeed devMode={devMode} workflowState={workflowState} />
          </Suspense>
        </div>

      </div>
    </div>
  );
}

export default App;
