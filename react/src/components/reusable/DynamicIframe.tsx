import React, { useRef, useEffect } from 'react';
import { Box } from '@mui/material';

interface DynamicIframeProps {
    pipelineId: string;
    baseUrl: string;
}

export const DynamicIframe: React.FC<DynamicIframeProps> = ({ pipelineId, baseUrl }) => {
    const iframeRef = useRef<HTMLIFrameElement>(null);

    useEffect(() => {
        if (iframeRef.current) {
            iframeRef.current.src = `${baseUrl}/ui/${pipelineId}`;
        }
    }, [pipelineId, baseUrl]);

    return (
        <Box sx={{ width: '100%', height: '100%', border: 'none' }}>
            <iframe
                ref={iframeRef}
                sandbox="allow-scripts allow-same-origin allow-forms"
                style={{ width: '100%', height: '100%', border: 'none' }}
                title={`Dynamic Component ${pipelineId}`}
            />
        </Box>
    );
};
