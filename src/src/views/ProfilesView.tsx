import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Plus, Trash2, Edit } from 'lucide-react';

interface Profile {
  id: string;
  name: string;
  type: string;
  image: string;
  llm: string;
  budget: number;
}

export default function ProfilesView() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [formData, setFormData] = useState({ name: '', type: 'Aider', image: 'docker.io/aider:latest', llm: 'gpt-4o', budget: 100000 });

  const loadData = async () => {
    try {
      const val = await invoke<Profile[]>('get_profiles');
      setProfiles(val);
    } catch (e) {
      console.error("Failed to load profiles:", e);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const newProfile = {
      id: Date.now().toString(),
      ...formData
    };

    try {
      await invoke('create_profile', { profile: newProfile });
      setIsFormOpen(false);
      loadData();
    } catch (e) {
      alert("Failed to save profile: " + e);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await invoke('delete_profile', { id });
      loadData();
    } catch (e) {
      alert("Failed to delete profile: " + e);
    }
  };

  return (
    <div style={{ padding: '24px', height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px', margin: 0 }}>Harness & Agent Profiles</h2>
        <button onClick={() => setIsFormOpen(!isFormOpen)} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', background: 'var(--accent-purple)', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
          <Plus size={16} /> Create Profile
        </button>
      </div>

      {isFormOpen && (
        <form onSubmit={handleSubmit} style={{ background: 'var(--bg-panel)', padding: '16px', borderRadius: '8px', marginBottom: '24px', border: '1px solid var(--border-muted)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <input required placeholder="Profile Name" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} style={inputStyle} />
          <select value={formData.type} onChange={e => setFormData({...formData, type: e.target.value})} style={inputStyle}>
            <option>Aider</option>
            <option>OpenHands</option>
            <option>Custom DSPy</option>
          </select>
          <input required placeholder="Base Docker Image" value={formData.image} onChange={e => setFormData({...formData, image: e.target.value})} style={inputStyle} />
          <input required placeholder="Default LLM" value={formData.llm} onChange={e => setFormData({...formData, llm: e.target.value})} style={inputStyle} />
          <input type="number" required placeholder="Max Token Budget" value={formData.budget} onChange={e => setFormData({...formData, budget: parseInt(e.target.value)})} style={inputStyle} />
          <button type="submit" style={{ gridColumn: 'span 2', padding: '8px', background: 'var(--accent-purple)', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>Save Profile</button>
        </form>
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse', background: 'var(--bg-panel)', borderRadius: '8px', overflow: 'hidden' }}>
        <thead style={{ background: 'var(--bg-dark)', borderBottom: '1px solid var(--border-muted)' }}>
          <tr>
            <th style={thStyle}>Name</th>
            <th style={thStyle}>Type</th>
            <th style={thStyle}>Image</th>
            <th style={thStyle}>LLM</th>
            <th style={thStyle}>Token Budget</th>
            <th style={thStyle}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {profiles.map(p => (
            <tr key={p.id} style={{ borderBottom: '1px solid var(--border-muted)' }}>
              <td style={tdStyle}>{p.name}</td>
              <td style={tdStyle}>{p.type}</td>
              <td style={tdStyle}>{p.image}</td>
              <td style={tdStyle}>{p.llm}</td>
              <td style={tdStyle}>{p.budget.toLocaleString()}</td>
              <td style={tdStyle}>
                <button style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', marginRight: '8px' }} title="Edit Signatures">
                  <Edit size={16} />
                </button>
                <button onClick={() => handleDelete(p.id)} style={{ background: 'none', border: 'none', color: 'var(--status-red)', cursor: 'pointer' }}>
                  <Trash2 size={16} />
                </button>
              </td>
            </tr>
          ))}
          {profiles.length === 0 && (
            <tr><td colSpan={6} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>No profiles configured.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

const inputStyle = { padding: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-muted)', color: 'var(--text-primary)', borderRadius: '4px' };
const thStyle = { padding: '12px 16px', textAlign: 'left' as const, color: 'var(--text-muted)', fontWeight: 'normal', fontSize: '14px' };
const tdStyle = { padding: '12px 16px', fontSize: '14px' };
