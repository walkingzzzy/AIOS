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
};

// 暴露 API 到渲染进程
contextBridge.exposeInMainWorld('aios', api);

// TypeScript 类型声明
declare global {
    interface Window {
        aios: typeof api;
    }
}

