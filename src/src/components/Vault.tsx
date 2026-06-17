import { useState, useEffect } from 'react';
import { load } from '@tauri-apps/plugin-store';

export default function Vault() {
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
    <div style={{ border: '1px solid #ccc', padding: '16px', borderRadius: '8px', marginBottom: '16px' }}>
      <h2>Secure Vault</h2>
      <p style={{ fontSize: '14px', color: '#666' }}>
        Keys are stored natively and injected into the Control Plane at runtime.
      </p>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <input 
          type="password" 
          value={apiKey} 
          onChange={(e) => setApiKey(e.target.value)} 
          placeholder="sk-..." 
          style={{ padding: '8px', flexGrow: 1 }}
        />
        <button onClick={saveKey} style={{ padding: '8px 16px' }}>Save</button>
      </div>
      {status && <p style={{ fontSize: '12px', color: 'green', marginTop: '8px' }}>{status}</p>}
    </div>
  );
}
