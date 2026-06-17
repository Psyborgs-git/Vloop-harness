import { Search, ToggleLeft, ToggleRight, DollarSign } from 'lucide-react';

interface HeaderProps {
  devMode: boolean;
  setDevMode: (val: boolean) => void;
}

export default function Header({ devMode, setDevMode }: HeaderProps) {
  return (
    <header style={{
      height: '60px',
      borderBottom: '1px solid var(--border-muted)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 24px',
      justifyContent: 'space-between',
      background: 'var(--bg-dark)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <h1 style={{ fontSize: '18px', fontWeight: 600, margin: 0, letterSpacing: '-0.5px' }}>VLoop</h1>
        
        {/* Omnibar Placeholder */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--bg-panel)',
          border: '1px solid var(--border-muted)',
          borderRadius: '6px',
          padding: '6px 12px',
          width: '300px',
          gap: '8px'
        }}>
          <Search size={14} color="var(--text-muted)" />
          <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Search or dispatch task (Cmd+K)</span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
        {/* Cost Metric */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '13px', color: 'var(--text-muted)' }}>
          <DollarSign size={14} />
          <span>Session: $0.42</span>
        </div>

        {/* Developer Mode Toggle */}
        <div 
          onClick={() => setDevMode(!devMode)}
          style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}
        >
          <span style={{ color: devMode ? 'var(--accent-purple)' : 'var(--text-muted)' }}>Developer Mode</span>
          {devMode ? <ToggleRight size={20} color="var(--accent-purple)" /> : <ToggleLeft size={20} color="var(--text-muted)" />}
        </div>
      </div>
    </header>
  );
}
