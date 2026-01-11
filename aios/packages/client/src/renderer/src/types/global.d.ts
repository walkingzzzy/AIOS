/**
 * 全局类型声明
 */

/** AIOS API 接口 */
interface AiosAPI {
    /** 发送消息到 daemon */
    sendMessage: (message: string) => Promise<unknown>;

    /** 获取所有适配器列表 */
    getAdapters: () => Promise<unknown>;

    /** 获取所有适配器列表（含可用状态） */
    getAdaptersWithStatus: () => Promise<unknown>;

    /** 调用适配器能力 */
    invoke: (adapterId: string, capability: string, args: Record<string, unknown>) => Promise<unknown>;

    /** AI 对话 */
    chat: (messages: Array<{ role: string; content: string }>) => Promise<unknown>;

    /** 智能对话 (三层 AI 协调) */
    smartChat: (message: string, hasScreenshot?: boolean) => Promise<{
        success: boolean;
        response: string;
        tier: 'direct' | 'fast' | 'vision' | 'smart';
        executionTime: number;
        model?: string;
    }>;

    /** 获取 AI 配置 */
    getAIConfig: () => Promise<unknown>;

    /** 设置 AI 配置 */
    setAIConfig: (config: {
        fast?: { baseUrl: string; model: string; apiKey?: string };
        vision?: { baseUrl: string; model: string; apiKey?: string };
        smart?: { baseUrl: string; model: string; apiKey?: string };
    }) => Promise<unknown>;

    /** 获取模型列表 */
    fetchModels: (params: { baseUrl: string; apiKey?: string }) => Promise<unknown>;

    /** 测试 AI 连接 */
    testAIConnection: (params: { baseUrl: string; apiKey?: string; model: string }) => Promise<unknown>;

    /** 监听导航事件 */
    onNavigate: (callback: (path: string) => void) => void;

    /** 监听快速启动器事件 */
    onShowQuickLauncher: (callback: () => void) => void;

    /** 获取系统信息 */
    getSystemInfo: () => Promise<{ platform: string; version: string }>;

    /** 关闭窗口 */
    closeWindow: () => void;

    /** 最小化窗口 */
    minimizeWindow: () => void;
}

declare global {
    interface Window {
        aios?: AiosAPI;
    }
}

export {};
