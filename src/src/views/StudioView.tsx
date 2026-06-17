import React, { Suspense } from 'react';

const WorkflowCanvas = React.lazy(() => import('../components/WorkflowCanvas'));

interface StudioViewProps {
  workflowState: any;
}

export default function StudioView({ workflowState }: StudioViewProps) {
  return (
    <Suspense fallback={<div style={{ padding: '24px', color: 'var(--text-muted)' }}>Loading Canvas...</div>}>
      <WorkflowCanvas workflowState={workflowState} />
    </Suspense>
  );
}
