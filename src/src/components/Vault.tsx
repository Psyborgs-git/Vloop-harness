import { useState, useEffect } from 'react';
import { load } from '@tauri-apps/plugin-store';
import { X } from 'lucide-react';

interface VaultProps {
  onClose: () => void;
}

export default function Vault({ onClose }: VaultProps) {
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {
    async function loadKey() {
      const store = await load('.vloop-vault.dat');
      const val = await store.get<{ value: string }>('openai_api_key');
      if (val) {
        setApiKey(val.value);
        setStatus('Loaded from secure vault.');
      }
    }
    loadKey();
  }, []);

  const saveKey = async () => {
    try {
      const store = await load('.vloop-vault.dat');
      await store.set('openai_api_key', { value: apiKey });
      await store.save();
      setStatus('Key securely saved to vault.');
    } catch (err) {
      console.error(err);
      setStatus('Failed to save key.');
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div style={{ 
        background: 'var(--bg-panel)', 
        border: '1px solid var(--border-muted)', 
        padding: '24px', 
        borderRadius: '8px', 
        width: '400px',
        position: 'relative'
      }}>
        <button 
          onClick={onClose}
          style={{ position: 'absolute', top: '16px', right: '16px', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
        >
          <X size={20} />
        </button>

        <h2 style={{ marginTop: 0, marginBottom: '8px', fontSize: '18px' }}>Security Vault</h2>
        <p style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '16px' }}>
          Keys are stored natively and injected into the Control Plane at runtime.
        </p>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <input 
            type="password" 
            value={apiKey} 
            onChange={(e) => setApiKey(e.target.value)} 
            placeholder="sk-..." 
            style={{ 
              padding: '8px', 
              flexGrow: 1, 
              background: 'var(--bg-dark)', 
              border: '1px solid var(--border-muted)',
              color: 'var(--text-primary)',
              borderRadius: '4px'
            }}
          />
          <button onClick={saveKey} style={{ 
            padding: '8px 16px', 
            background: 'var(--accent-purple)', 
            color: 'white', 
            border: 'none', 
            borderRadius: '4px',
            cursor: 'pointer'
          }}>Save</button>
        </div>
        {status && <p style={{ fontSize: '12px', color: 'var(--status-green)', marginTop: '12px', marginBottom: 0 }}>{status}</p>}
      </div>
    </div>
  );
}
