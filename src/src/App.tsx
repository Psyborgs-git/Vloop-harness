import React, { useState, useEffect, Suspense } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

import Header from './components/Header';
import SidebarNav from './components/SidebarNav';
import Vault from './components/Vault';

import StudioView from './views/StudioView';
import AdaptersView from './views/AdaptersView';
import ProfilesView from './views/ProfilesView';
import KnowledgeBaseView from './views/KnowledgeBaseView';
import SwarmFleetView from './views/SwarmFleetView';

const ExecutionFeed = React.lazy(() => import('./components/ExecutionFeed'));

function App() {
  const [devMode, setDevMode] = useState(false);
  const [workflowState, setWorkflowState] = useState<any>(null);
  const [isVaultOpen, setIsVaultOpen] = useState(false);

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
    <Router>
      <div style={{ 
        display: 'grid', 
        gridTemplateRows: '60px 1fr', 
        height: '100vh', 
        width: '100vw',
        background: 'var(--bg-dark)'
      }}>
        {/* Top Header */}
        <Header devMode={devMode} setDevMode={setDevMode} />

        {/* 3-Pane Layout Below Header */}
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: '5% 65% 30%', 
          height: '100%', 
          overflow: 'hidden' 
        }}>
          
          {/* Pane 1: Navigation Dock */}
          <SidebarNav onOpenVault={() => setIsVaultOpen(true)} />

          {/* Pane 2: Main Workspace (Dynamic Stage) */}
          <div style={{ position: 'relative' }}>
            <Routes>
              <Route path="/" element={<StudioView workflowState={workflowState} />} />
              <Route path="/adapters" element={<AdaptersView />} />
              <Route path="/profiles" element={<ProfilesView />} />
              <Route path="/kb" element={<KnowledgeBaseView />} />
              <Route path="/swarm" element={<SwarmFleetView />} />
            </Routes>
          </div>

          {/* Pane 3: Context/Dev Panel (Execution Feed) */}
          <div style={{ borderLeft: '1px solid var(--border-muted)' }}>
            <Suspense fallback={<div style={{ padding: '24px', color: 'var(--text-muted)' }}>Loading Feed...</div>}>
              <ExecutionFeed devMode={devMode} workflowState={workflowState} />
            </Suspense>
          </div>

        </div>
      </div>
      
      {/* Global Modals */}
      {isVaultOpen && <Vault onClose={() => setIsVaultOpen(false)} />}
    </Router>
  );
}

export default App;
