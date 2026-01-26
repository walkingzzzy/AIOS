import React from 'react';
import { ToolCard } from './ToolCard';
import type { ToolAdapter, ToolCapability } from './types';
import type { ToolStatus } from './ToolStatusIndicator';

interface ToolCardsPanelProps {
    adapters: ToolAdapter[];
    selectedAdapterId?: string | null;
    selectedCapabilityId?: string | null;
    adapterIcons: Record<string, string>;
    onSelectCapability: (adapter: ToolAdapter, capability: ToolCapability) => void;
    onQuickTest: (adapter: ToolAdapter, capability: ToolCapability) => void;
    hasQuickTest: (adapterId: string, capabilityId: string) => boolean;
}

function getStatus(adapter: ToolAdapter): ToolStatus {
    if (adapter.available === false) {
        return 'unavailable';
    }
    const needsPermission = adapter.capabilities.some(
        (cap) => cap.permissionLevel !== 'public'
    );
    return needsPermission ? 'needs-permission' : 'available';
}

export const ToolCardsPanel: React.FC<ToolCardsPanelProps> = ({
    adapters,
    selectedAdapterId,
    selectedCapabilityId,
    adapterIcons,
    onSelectCapability,
    onQuickTest,
    hasQuickTest,
}) => {
    return (
        <div className="adapters-grid">
            {adapters.map((adapter) => (
                <ToolCard
                    key={adapter.id}
                    adapter={adapter}
                    icon={adapterIcons[adapter.id] || '🔧'}
                    status={getStatus(adapter)}
                    selectedCapabilityId={
                        selectedAdapterId === adapter.id ? selectedCapabilityId : null
                    }
                    onSelectCapability={onSelectCapability}
                    onQuickTest={onQuickTest}
                    hasQuickTest={hasQuickTest}
                />
            ))}
        </div>
    );
};
