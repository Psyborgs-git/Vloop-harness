import { useState } from 'react';

interface ExecutionFeedProps {
  devMode: boolean;
}

export default function ExecutionFeed({ devMode }: ExecutionFeedProps) {
  const [activeTab, setActiveTab] = useState<'proxy' | 'diff' | 'logs'>('proxy');

  if (!devMode) {
    return (
      <div style={{ padding: '24px', height: '100%', overflowY: 'auto' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600, marginTop: 0, marginBottom: '24px' }}>Activity Feed</h2>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--status-green)', marginTop: '6px' }} />
            <div>
              <div style={{ fontSize: '14px', color: 'var(--text-primary)' }}>Agent successfully wrote data_cleaner.py</div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>2 minutes ago</div>
            </div>
          </div>
          
          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--accent-blue)', marginTop: '6px' }} />
            <div>
              <div style={{ fontSize: '14px', color: 'var(--text-primary)' }}>Executing data pipeline in secure sandbox...</div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>Just now</div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Developer Mode View
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

      <div style={{ flexGrow: 1, padding: '16px', overflowY: 'auto', fontFamily: 'monospace', fontSize: '12px', color: '#a8b2d1' }}>
        {activeTab === 'proxy' && (
          <pre style={{ margin: 0 }}>{JSON.stringify({
            "model": "gpt-4o-mini",
            "messages": [
              {"role": "system", "content": "You are a helpful coding assistant."},
              {"role": "user", "content": "Clean this CSV..."}
            ],
            "usage": { "prompt_tokens": 142, "completion_tokens": 58 }
          }, null, 2)}</pre>
        )}
        
        {activeTab === 'diff' && (
          <div style={{ color: 'var(--status-green)' }}>
            + import pandas as pd<br/>
            + df = pd.read_csv('data.csv')<br/>
            + df = df.dropna()<br/>
          </div>
        )}

        {activeTab === 'logs' && (
          <div>
            [sandbox-exec] Booting runsc gVisor environment...<br/>
            [sandbox-exec] Mounting volume /tmp/vloop-workspaces/...<br/>
            [sandbox-exec] Executing python main.py<br/>
          </div>
        )}
      </div>
    </div>
  );
}
