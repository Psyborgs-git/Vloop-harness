import { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';

export default function AuditLog() {
  const [objective, setObjective] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);

  const dispatchTask = async () => {
    if (!objective) return;
    
    setIsProcessing(true);
    setLogs(prev => [...prev, `[System] Dispatching task: ${objective}`]);
    
    try {
      const response = await invoke<string>('dispatch_task', {
        taskId: `task-${Date.now()}`,
        objective: objective
      });
      setLogs(prev => [...prev, `[Success] ${response}`]);
    } catch (error) {
      setLogs(prev => [...prev, `[Error] ${error}`]);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div style={{ border: '1px solid #ccc', padding: '16px', borderRadius: '8px' }}>
      <h2>Agent Orchestration</h2>
      
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <input 
          type="text" 
          value={objective} 
          onChange={(e) => setObjective(e.target.value)} 
          placeholder="E.g., Scrape hacker news and extract top 5 articles." 
          style={{ padding: '8px', flexGrow: 1 }}
          disabled={isProcessing}
        />
        <button onClick={dispatchTask} disabled={isProcessing} style={{ padding: '8px 16px' }}>
          {isProcessing ? 'Processing...' : 'Dispatch Task'}
        </button>
      </div>

      <div style={{ background: '#1e1e1e', color: '#00ff00', padding: '12px', borderRadius: '4px', height: '200px', overflowY: 'auto', fontFamily: 'monospace', fontSize: '12px' }}>
        {logs.length === 0 ? <span style={{ color: '#888' }}>No active tasks. Audit log empty.</span> : null}
        {logs.map((log, idx) => (
          <div key={idx}>{log}</div>
        ))}
      </div>
    </div>
  );
}
