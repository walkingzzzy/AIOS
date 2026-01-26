import React from 'react';

export type ToolStatus = 'available' | 'unavailable' | 'needs-permission';

const STATUS_LABELS: Record<ToolStatus, string> = {
    available: '可用',
    unavailable: '不可用',
    'needs-permission': '需授权',
};

export const ToolStatusIndicator: React.FC<{ status: ToolStatus }> = ({ status }) => {
    return (
        <span className={`status-badge ${status}`}>
            {STATUS_LABELS[status]}
        </span>
    );
};
