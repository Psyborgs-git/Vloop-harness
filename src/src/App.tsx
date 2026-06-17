import Vault from './components/Vault';
import AuditLog from './components/AuditLog';

function App() {
  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '24px', fontFamily: 'system-ui, sans-serif' }}>
      <h1 style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        🚀 VLoop Mission Control
      </h1>
      <p style={{ color: '#555', marginBottom: '32px' }}>
        Local-first orchestration engine. Rust Microkernel + Python Control Plane.
      </p>

      <Vault />
      <AuditLog />
    </div>
  );
}

export default App;
