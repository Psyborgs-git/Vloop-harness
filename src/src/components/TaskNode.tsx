import { Handle, Position } from '@xyflow/react';
import { Play, CheckCircle2, RotateCcw, AlertTriangle } from 'lucide-react';

interface TaskNodeProps {
  data: {
    label: string;
    status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
    summary?: string;
    onRewind?: () => void;
  };
}

export default function TaskNode({ data }: TaskNodeProps) {
  let statusColor = 'var(--text-muted)';
  let StatusIcon = Play;

  if (data.status === 'RUNNING') {
    statusColor = 'var(--accent-blue)';
    StatusIcon = Play;
  } else if (data.status === 'COMPLETED') {
    statusColor = 'var(--status-green)';
    StatusIcon = CheckCircle2;
  } else if (data.status === 'FAILED') {
    statusColor = 'var(--status-red)';
    StatusIcon = AlertTriangle;
  }

  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: `1px solid ${data.status === 'RUNNING' ? 'var(--accent-blue)' : 'var(--border-muted)'}`,
      borderRadius: '8px',
      padding: '12px 16px',
      width: '240px',
      color: 'var(--text-primary)',
      boxShadow: data.status === 'RUNNING' ? '0 0 0 2px rgba(59, 130, 246, 0.2)' : 'none',
    }}>
      <Handle type="target" position={Position.Top} style={{ background: 'var(--border-muted)' }} />
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <StatusIcon size={16} color={statusColor} />
          <strong style={{ fontSize: '14px' }}>{data.label}</strong>
        </div>
        
        {/* Time Travel Rewind Button */}
        {(data.status === 'COMPLETED' || data.status === 'FAILED') && (
          <button 
            onClick={(e) => {
              e.stopPropagation();
              if (data.onRewind) data.onRewind();
            }}
            title="Rewind to this node"
            style={{ 
              background: 'transparent', 
              border: 'none', 
              color: 'var(--text-muted)', 
              padding: 0,
              cursor: 'pointer'
            }}>
            <RotateCcw size={14} />
          </button>
        )}
      </div>
      
      {data.summary && (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px', lineHeight: '1.4' }}>
          {data.summary}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} style={{ background: 'var(--border-muted)' }} />
    </div>
  );
}
