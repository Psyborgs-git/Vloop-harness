import { useState, useEffect } from 'react';
import { load } from '@tauri-apps/plugin-store';

export default function Settings() {
  const [litefsUrl, setLitefsUrl] = useState('');
  const [litefsToken, setLitefsToken] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {
    async function loadConfig() {
      const store = await load('.vloop-vault.dat');
      const url = await store.get<{ value: string }>('litefs_url');
      const token = await store.get<{ value: string }>('litefs_token');
      if (url) setLitefsUrl(url.value);
      if (token) setLitefsToken(token.value);
    }
    loadConfig();
  }, []);

  const saveConfig = async () => {
    try {
      const store = await load('.vloop-vault.dat');
      await store.set('litefs_url', { value: litefsUrl });
      await store.set('litefs_token', { value: litefsToken });
      await store.save();
      setStatus('LiteFS configuration saved.');
    } catch (err) {
      console.error(err);
      setStatus('Failed to save config.');
    }
  };

  return (
    <div style={{ border: '1px solid #ccc', padding: '16px', borderRadius: '8px', marginBottom: '16px', marginTop: '16px' }}>
      <h2>State Sync (LiteFS)</h2>
      <p style={{ fontSize: '14px', color: '#666' }}>
        Configure an S3-compatible bucket or LiteFS Cloud URL to sync DAG state across machines.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <input 
          type="text" 
          value={litefsUrl} 
          onChange={(e) => setLitefsUrl(e.target.value)} 
          placeholder="consul URL or S3 Bucket" 
          style={{ padding: '8px' }}
        />
        <input 
          type="password" 
          value={litefsToken} 
          onChange={(e) => setLitefsToken(e.target.value)} 
          placeholder="Access Token" 
          style={{ padding: '8px' }}
        />
        <button onClick={saveConfig} style={{ padding: '8px 16px', alignSelf: 'flex-start' }}>Save Sync Config</button>
      </div>
      {status && <p style={{ fontSize: '12px', color: 'green', marginTop: '8px' }}>{status}</p>}
    </div>
  );
}
