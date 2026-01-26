export interface ToolCapability {
    id: string;
    name: string;
    description: string;
    permissionLevel: string;
    parameters?: Array<{
        name: string;
        type: string;
        required: boolean;
        description: string;
        enum?: string[];
    }>;
}

export interface ToolAdapter {
    id: string;
    name: string;
    description: string;
    capabilities: ToolCapability[];
    available?: boolean;
}

export interface ToolTestResult {
    success: boolean;
    result?: unknown;
    error?: string;
}

export interface ToolTestHistoryItem {
    id: string;
    adapterId: string;
    capabilityId: string;
    capabilityName: string;
    params: Record<string, unknown>;
    result: ToolTestResult;
    timestamp: Date;
}
