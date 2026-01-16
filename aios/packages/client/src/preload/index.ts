/**
 * AIOS Client - Preload 脚本
 * 为渲染进程暴露安全的 API
 */

import { contextBridge, ipcRenderer } from 'electron';

// 暴露给渲染进程的 API
const api = {
    /** 发送消息到 daemon */
    sendMessage: async (message: string): Promise<unknown> => {
        return ipcRenderer.invoke('daemon:send', message);
    },

    /** 获取所有适配器列表 */
    getAdapters: async (): Promise<unknown> => {
        return ipcRenderer.invoke('daemon:getAdapters');
    },

    /** 获取所有适配器列表（含可用状态） */
    getAdaptersWithStatus: async (): Promise<unknown> => {
        return ipcRenderer.invoke('daemon:getAdaptersWithStatus');
    },

    /** 调用适配器能力 */
    invoke: async (adapterId: string, capability: string, args: Record<string, unknown>): Promise<unknown> => {
        return ipcRenderer.invoke('daemon:invoke', { adapterId, capability, args });
    },

    /** AI 对话 */
    chat: async (messages: Array<{ role: string; content: string }>): Promise<unknown> => {
        return ipcRenderer.invoke('daemon:chat', { messages });
    },

    /** 智能对话 (三层 AI 协调) */
    smartChat: async (message: string, hasScreenshot = false): Promise<{
        success: boolean;
        response: string;
        tier: 'direct' | 'fast' | 'vision' | 'smart';
        executionTime: number;
        model?: string;
    }> => {
        return ipcRenderer.invoke('daemon:smartChat', { message, hasScreenshot });
    },

    /** 获取 AI 配置 */
    getAIConfig: async (): Promise<unknown> => {
        return ipcRenderer.invoke('daemon:getAIConfig');
    },

    /** 设置 AI 配置 */
    setAIConfig: async (config: {
        fast?: { baseUrl: string; model: string; apiKey?: string };
        vision?: { baseUrl: string; model: string; apiKey?: string };
        smart?: { baseUrl: string; model: string; apiKey?: string };
    }): Promise<unknown> => {
        return ipcRenderer.invoke('daemon:setAIConfig', config);
    },

    /** 获取模型列表 */
    fetchModels: async (params: { baseUrl: string; apiKey?: string }): Promise<unknown> => {
        return ipcRenderer.invoke('daemon:fetchModels', params);
    },

    /** 测试 AI 连接 */
    testAIConnection: async (params: { baseUrl: string; apiKey?: string; model: string }): Promise<unknown> => {
        return ipcRenderer.invoke('daemon:testAIConnection', params);
    },

    /** 检查权限 */
    checkPermission: async (level: 'public' | 'low' | 'medium' | 'high' | 'critical'): Promise<{
        granted: boolean;
        level: string;
        platform: string;
        details?: string;
    }> => {
        return ipcRenderer.invoke('daemon:checkPermission', { level });
    },

    /** 请求权限 */
    requestPermission: async (level: 'public' | 'low' | 'medium' | 'high' | 'critical'): Promise<{
        success: boolean;
        granted: boolean;
        message: string;
    }> => {
        return ipcRenderer.invoke('daemon:requestPermission', { level });
    },

    /** 监听导航事件 */
    onNavigate: (callback: (path: string) => void): void => {
        ipcRenderer.on('navigate', (_event, path) => callback(path));
    },

    /** 监听快速启动器事件 */
    onShowQuickLauncher: (callback: () => void): void => {
        ipcRenderer.on('show-quick-launcher', () => callback());
    },

    /** 获取系统信息 */
    getSystemInfo: async (): Promise<{ platform: string; version: string }> => {
        return ipcRenderer.invoke('system:info');
    },

    /** 关闭窗口 */
    closeWindow: (): void => {
        ipcRenderer.send('window:close');
    },

    /** 最小化窗口 */
    minimizeWindow: (): void => {
        ipcRenderer.send('window:minimize');
    },

    // ============ Task API ============

    /** 提交任务 */
    submitTask: async (prompt: string, options?: {
        priority?: 'critical' | 'high' | 'normal' | 'low' | 'background';
        type?: 'simple' | 'visual' | 'complex';
        metadata?: Record<string, unknown>;
    }): Promise<{ taskId: string; status: string; position: number }> => {
        return ipcRenderer.invoke('task:submit', { prompt, ...options });
    },

    /** 取消任务 */
    cancelTask: async (taskId: string): Promise<{ success: boolean; message: string }> => {
        return ipcRenderer.invoke('task:cancel', { taskId });
    },

    /** 获取任务状态 */
    getTaskStatus: async (taskId: string): Promise<{
        taskId: string;
        status: string;
        prompt: string;
        createdAt: number;
        startedAt?: number;
        completedAt?: number;
        executionTime?: number;
        response?: string;
        error?: string;
    } | null> => {
        return ipcRenderer.invoke('task:getStatus', { taskId });
    },

    /** 获取队列状态 */
    getTaskQueue: async (): Promise<{
        pending: number;
        running: number;
        completed: number;
        failed: number;
        tasks: Array<{ taskId: string; status: string; prompt: string; priority: number }>;
    }> => {
        return ipcRenderer.invoke('task:getQueue');
    },

    /** 获取任务历史 */
    getTaskHistory: async (options?: {
        sessionId?: string;
        status?: string;
        page?: number;
        pageSize?: number;
    }): Promise<{
        items: Array<unknown>;
        total: number;
        page: number;
        pageSize: number;
    }> => {
        return ipcRenderer.invoke('task:getHistory', options);
    },

    // ============ Progress Events ============

    /** 监听任务进度 */
    onTaskProgress: (callback: (event: {
        taskId: string;
        percentage: number;
        currentStep: number;
        totalSteps: number;
        stepDescription?: string;
    }) => void): (() => void) => {
        const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data as any);
        ipcRenderer.on('task:progress', handler);
        return () => ipcRenderer.removeListener('task:progress', handler);
    },

    /** 监听任务完成 */
    onTaskComplete: (callback: (event: {
        taskId: string;
        success: boolean;
        response: string;
        executionTime: number;
    }) => void): (() => void) => {
        const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data as any);
        ipcRenderer.on('task:complete', handler);
        return () => ipcRenderer.removeListener('task:complete', handler);
    },

    /** 监听任务错误 */
    onTaskError: (callback: (event: {
        taskId: string;
        error: string;
        recoverable: boolean;
    }) => void): (() => void) => {
        const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data as any);
        ipcRenderer.on('task:error', handler);
        return () => ipcRenderer.removeListener('task:error', handler);
    },

    // ============ Confirmation ============

    /** 监听确认请求 */
    onConfirmationRequest: (callback: (request: {
        id: string;
        operation: string;
        riskLevel: 'medium' | 'high' | 'critical';
        description: string;
        details: Record<string, unknown>;
        createdAt: number;
        timeout: number;
    }) => void): (() => void) => {
        const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data as any);
        ipcRenderer.on('confirmation:request', handler);
        return () => ipcRenderer.removeListener('confirmation:request', handler);
    },

    /** 响应确认请求 */
    respondConfirmation: async (requestId: string, confirmed: boolean, reason?: string): Promise<{ success: boolean }> => {
        return ipcRenderer.invoke('confirmation:respond', { requestId, confirmed, reason });
    },
};

// 暴露 API 到渲染进程
contextBridge.exposeInMainWorld('aios', api);

// TypeScript 类型声明
declare global {
    interface Window {
        aios: typeof api;
    }
}

