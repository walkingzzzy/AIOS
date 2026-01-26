import React from 'react';
import PermissionGuide from '../PermissionGuide';
import { ToolStatusIndicator, type ToolStatus } from './ToolStatusIndicator';
import type { ToolAdapter, ToolCapability } from './types';

interface ToolCardProps {
    adapter: ToolAdapter;
    icon: string;
    status: ToolStatus;
    selectedCapabilityId?: string | null;
    onSelectCapability: (adapter: ToolAdapter, capability: ToolCapability) => void;
    onQuickTest: (adapter: ToolAdapter, capability: ToolCapability) => void;
    hasQuickTest: (adapterId: string, capabilityId: string) => boolean;
}

export const ToolCard: React.FC<ToolCardProps> = ({
    adapter,
    icon,
    status,
    selectedCapabilityId,
    onSelectCapability,
    onQuickTest,
    hasQuickTest,
}) => {
    return (
        <div className={`adapter-card ${adapter.available === false ? 'unavailable' : ''}`}>
            <div className="adapter-header">
                <span className="adapter-icon">{icon}</span>
                <div className="adapter-info">
                    <h3>
                        {adapter.name}
                        <ToolStatusIndicator status={status} />
                    </h3>
                    <p>{adapter.description}</p>
                </div>
            </div>
            <div className="capabilities-list">
                {adapter.capabilities.map((capability) => (
                    <button
                        key={capability.id}
                        className={`capability-btn ${selectedCapabilityId === capability.id ? 'active' : ''}`}
                        onClick={() => onSelectCapability(adapter, capability)}
                    >
                        <span className="cap-name">{capability.name}</span>
                        <span className={`cap-permission ${capability.permissionLevel}`}>
                            {capability.permissionLevel}
                        </span>
                        {hasQuickTest(adapter.id, capability.id) && (
                            <span
                                className="quick-test-icon"
                                onClick={(event) => {
                                    event.stopPropagation();
                                    onQuickTest(adapter, capability);
                                }}
                                title="快速测试"
                            >
                                ⚡
                            </span>
                        )}
                    </button>
                ))}
            </div>
            {adapter.available === false && (
                <PermissionGuide
                    adapterId={adapter.id}
                    adapterName={adapter.name}
                    available={adapter.available}
                />
            )}
        </div>
    );
};
