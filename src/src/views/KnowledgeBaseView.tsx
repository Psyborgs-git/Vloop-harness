import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Database, Plus, Trash2, RefreshCw } from 'lucide-react';

interface WatchPath {
  id: string;
  path: string;
  type: 'Local' | 'Git';
  chunks: number;
  last_indexed: string;
  status: 'Syncing' | 'Synced' | 'Error';
}

export default function KnowledgeBaseView() {
  const [paths, setPaths] = useState<WatchPath[]>([]);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [formData, setFormData] = useState({ path: '', type: 'Local' as 'Local'|'Git' });

  const loadData = async () => {
    try {
      const val = await invoke<WatchPath[]>('get_kb_paths');
      setPaths(val);
    } catch (e) {
      console.error("Failed to load KB paths:", e);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const newPath = {
      id: Date.now().toString(),
      ...formData,
      chunks: Math.floor(Math.random() * 5000),
      last_indexed: new Date().toLocaleString(),
      status: 'Syncing'
    };

    try {
      await invoke('add_kb_path', { path: newPath });
      setIsFormOpen(false);
      loadData();
      
      // Simulate indexing finish polling/refresh
      setTimeout(() => {
        loadData();
      }, 3000);
    } catch (e) {
      alert("Failed to add watch path: " + e);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await invoke('delete_kb_path', { id });
      loadData();
    } catch (e) {
      alert("Failed to delete watch path: " + e);
    }
  };

  return (
    <div style={{ padding: '24px', height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px', margin: 0 }}>Knowledge Base (RAG)</h2>
        <button onClick={() => setIsFormOpen(!isFormOpen)} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', background: 'var(--accent-purple)', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
          <Plus size={16} /> Add Watch Path
        </button>
      </div>

      {isFormOpen && (
        <form onSubmit={handleSubmit} style={{ background: 'var(--bg-panel)', padding: '16px', borderRadius: '8px', marginBottom: '24px', border: '1px solid var(--border-muted)', display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '16px' }}>
          <select value={formData.type} onChange={e => setFormData({...formData, type: e.target.value as any})} style={inputStyle}>
            <option>Local</option>
            <option>Git</option>
          </select>
          <input required placeholder={formData.type === 'Git' ? "https://github.com/..." : "/path/to/local/dir"} value={formData.path} onChange={e => setFormData({...formData, path: e.target.value})} style={inputStyle} />
          <button type="submit" style={{ gridColumn: 'span 2', padding: '8px', background: 'var(--accent-purple)', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>Start Indexing</button>
        </form>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {paths.map(p => (
          <div key={p.id} style={{ background: 'var(--bg-panel)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-muted)', display: 'flex', alignItems: 'center', gap: '16px' }}>
            <Database size={24} color="var(--text-muted)" />
            <div style={{ flexGrow: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '12px', background: 'var(--bg-dark)', padding: '2px 6px', borderRadius: '4px' }}>{p.type}</span>
                <strong style={{ fontSize: '14px' }}>{p.path}</strong>
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                {p.chunks} chunks • Last indexed: {p.last_indexed}
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {p.status === 'Syncing' && <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--accent-purple)', fontSize: '12px' }}><RefreshCw size={12} /> Syncing...</span>}
              {p.status === 'Synced' && <span style={{ color: 'var(--status-green)', fontSize: '12px' }}>Synced</span>}
              <button onClick={() => handleDelete(p.id)} style={{ background: 'none', border: 'none', color: 'var(--status-red)', cursor: 'pointer', padding: '8px' }} title="Purge from Vector Store">
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
        {paths.length === 0 && (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', border: '1px dashed var(--border-muted)', borderRadius: '8px' }}>No directories or repos are currently being watched.</div>
        )}
      </div>
    </div>
  );
}

const inputStyle = { padding: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-muted)', color: 'var(--text-primary)', borderRadius: '4px' };
