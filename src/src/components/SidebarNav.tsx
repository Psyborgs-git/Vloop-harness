import { Link, useLocation } from 'react-router-dom';
import { Home, Plug, Users, Database, Network, Key } from 'lucide-react';

interface SidebarNavProps {
  onOpenVault: () => void;
}

export default function SidebarNav({ onOpenVault }: SidebarNavProps) {
  const location = useLocation();

  const getLinkStyle = (path: string) => ({
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '12px 0',
    color: location.pathname === path ? 'var(--accent-purple)' : 'var(--text-muted)',
    borderLeft: location.pathname === path ? '2px solid var(--accent-purple)' : '2px solid transparent',
    textDecoration: 'none'
  });

  return (
    <nav style={{
      width: '100%',
      height: '100%',
      background: 'var(--bg-panel)',
      borderRight: '1px solid var(--border-muted)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      paddingTop: '16px',
      paddingBottom: '16px'
    }}>
      <div style={{ flexGrow: 1, width: '100%', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <Link to="/" style={getLinkStyle('/')} title="Studio">
          <Home size={20} />
        </Link>
        <Link to="/adapters" style={getLinkStyle('/adapters')} title="Adapters">
          <Plug size={20} />
        </Link>
        <Link to="/profiles" style={getLinkStyle('/profiles')} title="Profiles">
          <Users size={20} />
        </Link>
        <Link to="/kb" style={getLinkStyle('/kb')} title="Knowledge Base">
          <Database size={20} />
        </Link>
        <Link to="/swarm" style={getLinkStyle('/swarm')} title="Swarm Fleet">
          <Network size={20} />
        </Link>
      </div>

      <button
        onClick={onOpenVault}
        title="Security Vault"
        style={{
          background: 'none',
          border: 'none',
          color: 'var(--text-muted)',
          cursor: 'pointer',
          padding: '12px 0'
        }}
      >
        <Key size={20} />
      </button>
    </nav>
  );
}
