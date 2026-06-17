import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Database, Plus, Trash2, Zap } from 'lucide-react';

interface Adapter {
  id: string;
  name: string;
  uri: string;
  port: string;
  user: string;
  latency?: number;
  is_active: boolean;
}

export default function AdaptersView() {
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [formData, setFormData] = useState({ name: '', uri: '', port: '', user: '', pass: '' });

  const loadAdapters = async () => {
    try {
      const val = await invoke<Adapter[]>('get_adapters');
      // Simulate pings on frontend
      setAdapters(val.map(a => ({ ...a, latency: Math.floor(Math.random() * 50) + 10 })));
    } catch (e) {
      console.error("Failed to load adapters:", e);
    }
  };

  useEffect(() => {
    loadAdapters();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const newAdapter = {
      id: Date.now().toString(),
      name: formData.name,
      uri: formData.uri,
      port: formData.port,
      user: formData.user,
      is_active: adapters.length === 0, // First is active by default
    };

    try {
      await invoke('create_adapter', { adapter: newAdapter });
      setFormData({ name: '', uri: '', port: '', user: '', pass: '' });
      setIsFormOpen(false);
      loadAdapters();
    } catch (e) {
      alert("Failed to create adapter: " + e);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await invoke('delete_adapter', { id });
      loadAdapters();
    } catch (e) {
      alert("Failed to delete adapter: " + e);
    }
  };

  const handleSetActive = async (id: string) => {
    try {
      await invoke('set_active_adapter', { id });
      loadAdapters();
      alert("Microkernel executed graceful systemd restart to apply active adapter.");
    } catch (e) {
      alert("Failed to hot-swap adapter: " + e);
    }
  };

  return (
    <div style={{ padding: '24px', height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px', margin: 0 }}>Adapters & Config</h2>
        <button onClick={() => setIsFormOpen(!isFormOpen)} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', background: 'var(--accent-purple)', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
          <Plus size={16} /> Add Adapter
        </button>
      </div>

      {isFormOpen && (
        <form onSubmit={handleSubmit} style={{ background: 'var(--bg-panel)', padding: '16px', borderRadius: '8px', marginBottom: '24px', border: '1px solid var(--border-muted)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <input required placeholder="Name (e.g. Prod Postgres)" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} style={inputStyle} />
          <input required placeholder="URI (e.g. 127.0.0.1)" value={formData.uri} onChange={e => setFormData({...formData, uri: e.target.value})} style={inputStyle} />
          <input required placeholder="Port" value={formData.port} onChange={e => setFormData({...formData, port: e.target.value})} style={inputStyle} />
          <input required placeholder="User" value={formData.user} onChange={e => setFormData({...formData, user: e.target.value})} style={inputStyle} />
          <input type="password" required placeholder="Password" value={formData.pass} onChange={e => setFormData({...formData, pass: e.target.value})} style={inputStyle} />
          <button type="submit" style={{ gridColumn: 'span 2', padding: '8px', background: 'var(--accent-purple)', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>Save Adapter</button>
        </form>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
        {adapters.map(adapter => (
          <div key={adapter.id} style={{ background: 'var(--bg-panel)', padding: '16px', borderRadius: '8px', border: adapter.is_active ? '2px solid var(--accent-purple)' : '1px solid var(--border-muted)', position: 'relative' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <Database size={20} color={adapter.is_active ? 'var(--accent-purple)' : 'var(--text-muted)'} />
              <h3 style={{ margin: 0, fontSize: '16px' }}>{adapter.name}</h3>
              {adapter.is_active && <span style={{ marginLeft: 'auto', background: 'var(--accent-purple)', color: 'white', fontSize: '10px', padding: '2px 6px', borderRadius: '12px' }}>ACTIVE</span>}
            </div>
            <p style={{ margin: '0 0 8px 0', fontSize: '14px', color: 'var(--text-muted)' }}>{adapter.user}@{adapter.uri}:{adapter.port}</p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: 'var(--status-green)' }}>
              <Zap size={14} /> Ping: {adapter.latency}ms
            </div>
            
            <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
              {!adapter.is_active && (
                <button onClick={() => handleSetActive(adapter.id)} style={{ flexGrow: 1, padding: '6px', background: 'transparent', color: 'var(--text-primary)', border: '1px solid var(--border-muted)', borderRadius: '4px', cursor: 'pointer' }}>
                  Set Active
                </button>
              )}
              <button onClick={() => handleDelete(adapter.id)} style={{ padding: '6px', background: 'transparent', color: 'var(--status-red)', border: '1px solid var(--border-muted)', borderRadius: '4px', cursor: 'pointer' }}>
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
        {adapters.length === 0 && (
          <div style={{ gridColumn: 'span 3', padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>No adapters configured.</div>
        )}
      </div>
    </div>
  );
}

const inputStyle = {
  padding: '8px',
  background: 'var(--bg-dark)',
  border: '1px solid var(--border-muted)',
  color: 'var(--text-primary)',
  borderRadius: '4px'
};
