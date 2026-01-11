/**
 * 适配器相关类型定义
 */

/** 适配器执行结果 */
export interface AdapterResult {
    success: boolean;
    data?: Record<string, unknown>;
    error?: {
        code: string;
        message: string;
    };
}

/** 权限级别 */
export type PermissionLevel = 'public' | 'low' | 'medium' | 'high' | 'critical';

/** 能力参数定义 */
export interface CapabilityParameter {
    name: string;
    type: 'string' | 'number' | 'boolean' | 'object' | 'array';
    required: boolean;
    description: string;
    enum?: string[];
    default?: unknown;
}

/** 适配器能力定义 */
export interface AdapterCapability {
    id: string;
    name: string;
    description: string;
    permissionLevel: PermissionLevel;
    parameters?: CapabilityParameter[];
    returns?: CapabilityParameter[];
}

/** 适配器信息 */
export interface AdapterInfo {
    id: string;
    name: string;
    description: string;
    version: string;
    capabilities: AdapterCapability[];
    platforms?: ('darwin' | 'win32' | 'linux')[];
}

/** 适配器接口 */
export interface IAdapter {
    readonly id: string;
    readonly name: string;
    readonly description: string;
    readonly capabilities: AdapterCapability[];

    /** 初始化适配器 */
    initialize(): Promise<void>;

    /** 检查适配器可用性 */
    checkAvailability(): Promise<boolean>;

    /** 调用能力 */
    invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult>;

    /** 关闭适配器 */
    shutdown(): Promise<void>;
}
