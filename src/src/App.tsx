import React, { useState, Suspense } from 'react';
import Header from './components/Header';

// Code splitting: Lazy load heavy components
const WorkflowCanvas = React.lazy(() => import('./components/WorkflowCanvas'));
const ExecutionFeed = React.lazy(() => import('./components/ExecutionFeed'));

function App() {
  const [devMode, setDevMode] = useState(false);

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
            <WorkflowCanvas />
          </Suspense>
        </div>

        {/* Right Pane: Execution Feed / Dev View */}
        <div>
          <Suspense fallback={<div style={{ padding: '24px', color: 'var(--text-muted)' }}>Loading Feed...</div>}>
            <ExecutionFeed devMode={devMode} />
          </Suspense>
        </div>

      </div>
    </div>
  );
}

export default App;
