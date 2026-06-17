import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Network, Plus, Trash2, Settings2 } from 'lucide-react';

interface SwarmNode {
  id: string;
  ip: string;
  key: string;
  cpu: number;
  ram: number;
  status: 'Online' | 'Offline';
  rules: string;
}

export default function SwarmFleetView() {
  const [nodes, setNodes] = useState<SwarmNode[]>([]);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [formData, setFormData] = useState({ ip: '', key: '', rules: 'all-tasks' });

  const loadData = async () => {
    try {
      const val = await invoke<SwarmNode[]>('get_swarm_nodes');
      setNodes(val);
    } catch (e) {
      console.error("Failed to load nodes:", e);
    }
  };

  useEffect(() => {
    loadData();

    // Telemetry simulator
    const interval = setInterval(() => {
      setNodes(current => current.map(n => n.status === 'Online' ? {
        ...n,
        cpu: Math.min(100, Math.max(0, n.cpu + (Math.random() * 10 - 5))),
        ram: Math.min(100, Math.max(0, n.ram + (Math.random() * 4 - 2)))
      } : n));
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const newNode = {
      id: Date.now().toString(),
      ...formData,
      cpu: Math.random() * 20 + 10,
      ram: Math.random() * 40 + 20,
      status: 'Online'
    };

    try {
      await invoke('add_swarm_node', { node: newNode });
      setIsFormOpen(false);
      setFormData({ ip: '', key: '', rules: 'all-tasks' });
      loadData();
    } catch (e) {
      alert("Failed to add node: " + e);
    }
  };

  const handleToggleRule = async (id: string, currentRules: string) => {
    const nextRules = currentRules === 'all-tasks' ? 'gpu-tasks-only' : currentRules === 'gpu-tasks-only' ? 'pause-allocation' : 'all-tasks';
    try {
      await invoke('update_node_rules', { id, rules: nextRules });
      loadData();
    } catch (e) {
      alert("Failed to update rules: " + e);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await invoke('delete_swarm_node', { id });
      loadData();
    } catch (e) {
      alert("Failed to delete node: " + e);
    }
  };

  return (
    <div style={{ padding: '24px', height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px', margin: 0 }}>Swarm Fleet</h2>
        <button onClick={() => setIsFormOpen(!isFormOpen)} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', background: 'var(--accent-purple)', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
          <Plus size={16} /> Add Node
        </button>
      </div>

      {isFormOpen && (
        <form onSubmit={handleSubmit} style={{ background: 'var(--bg-panel)', padding: '16px', borderRadius: '8px', marginBottom: '24px', border: '1px solid var(--border-muted)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <input required placeholder="IP Address (e.g. 192.168.1.100)" value={formData.ip} onChange={e => setFormData({...formData, ip: e.target.value})} style={inputStyle} />
          <input required placeholder="Auth Key" value={formData.key} onChange={e => setFormData({...formData, key: e.target.value})} style={inputStyle} />
          <select value={formData.rules} onChange={e => setFormData({...formData, rules: e.target.value})} style={{...inputStyle, gridColumn: 'span 2'}}>
            <option value="all-tasks">All Tasks</option>
            <option value="gpu-tasks-only">GPU Tasks Only</option>
            <option value="pause-allocation">Pause Allocation</option>
          </select>
          <button type="submit" style={{ gridColumn: 'span 2', padding: '8px', background: 'var(--accent-purple)', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>Connect Node</button>
        </form>
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse', background: 'var(--bg-panel)', borderRadius: '8px', overflow: 'hidden' }}>
        <thead style={{ background: 'var(--bg-dark)', borderBottom: '1px solid var(--border-muted)' }}>
          <tr>
            <th style={thStyle}>Node IP</th>
            <th style={thStyle}>Status</th>
            <th style={thStyle}>Telemetry</th>
            <th style={thStyle}>Allocation Rules</th>
            <th style={thStyle}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {nodes.map(n => (
            <tr key={n.id} style={{ borderBottom: '1px solid var(--border-muted)' }}>
              <td style={tdStyle}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Network size={16} color="var(--text-muted)" /> {n.ip}
                </div>
              </td>
              <td style={tdStyle}>
                <span style={{ color: n.status === 'Online' ? 'var(--status-green)' : 'var(--status-red)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: n.status === 'Online' ? 'var(--status-green)' : 'var(--status-red)' }}></span>
                  {n.status}
                </span>
              </td>
              <td style={tdStyle}>
                <div style={{ fontSize: '12px', display: 'flex', gap: '12px' }}>
                  <span>CPU: {n.cpu.toFixed(1)}%</span>
                  <span>RAM: {n.ram.toFixed(1)}%</span>
                </div>
              </td>
              <td style={tdStyle}>
                <span style={{ fontSize: '12px', background: 'var(--bg-dark)', padding: '4px 8px', borderRadius: '4px' }}>{n.rules}</span>
              </td>
              <td style={tdStyle}>
                <button type="button" onClick={() => handleToggleRule(n.id, n.rules)} style={{ background: 'none', border: 'none', color: 'var(--text-primary)', cursor: 'pointer', marginRight: '8px' }} title="Toggle Rule">
                  <Settings2 size={16} />
                </button>
                <button type="button" onClick={() => handleDelete(n.id)} style={{ background: 'none', border: 'none', color: 'var(--status-red)', cursor: 'pointer' }}>
                  <Trash2 size={16} />
                </button>
              </td>
            </tr>
          ))}
          {nodes.length === 0 && (
            <tr><td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>No Swarm nodes connected.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

const inputStyle = { padding: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-muted)', color: 'var(--text-primary)', borderRadius: '4px' };
const thStyle = { padding: '12px 16px', textAlign: 'left' as const, color: 'var(--text-muted)', fontWeight: 'normal', fontSize: '14px' };
const tdStyle = { padding: '12px 16px', fontSize: '14px' };
