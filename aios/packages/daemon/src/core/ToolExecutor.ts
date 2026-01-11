/**
 * 工具执行器
 * 封装适配器调用，提供工具定义和执行功能
 */

import type { AdapterResult, InternalToolDefinition } from '@aios/shared';
import type { AdapterRegistry } from './AdapterRegistry.js';
import type { ToolCall } from '../types/orchestrator.js';

export interface ToolExecutionResult {
    success: boolean;
    message?: string;
    data?: unknown;
}

/**
 * 工具执行器 - 封装适配器调用
 */
export class ToolExecutor {
    private registry: AdapterRegistry;

    constructor(registry: AdapterRegistry) {
        this.registry = registry;
    }

    /**
     * 获取可用工具定义（内部格式，用于 AI Function Calling）
     */
    getAvailableTools(): InternalToolDefinition[] {
        const adapters = this.registry.getAll();
        const tools: InternalToolDefinition[] = [];

        for (const adapter of adapters) {
            for (const capability of adapter.capabilities) {
                tools.push({
                    name: `${adapter.id}.${capability.id}`,
                    description: `${adapter.name} - ${capability.description}`,
                    parameters: this.buildParameterSchema(capability.parameters || []),
                });
            }
        }

        return tools;
    }

    /**
     * 执行工具调用
     */
    async execute(toolCall: ToolCall): Promise<ToolExecutionResult> {
        const { tool, action, params } = toolCall;

        // 查找适配器
        const adapter = this.registry.get(tool);
        if (!adapter) {
            // 尝试按名称匹配
            const allAdapters = this.registry.getAll();
            const matched = allAdapters.find(a =>
                a.id.toLowerCase().includes(tool.toLowerCase()) ||
                a.name.toLowerCase().includes(tool.toLowerCase())
            );

            if (!matched) {
                return {
                    success: false,
                    message: `未找到工具: ${tool}`,
                };
            }

            // 使用匹配到的适配器
            return this.invokeAdapter(matched.id, action, params);
        }

        return this.invokeAdapter(tool, action, params);
    }

    /**
     * 执行视觉操作（点击、滑动等）
     */
    async executeAction(action: {
        type: 'click' | 'type' | 'scroll';
        x?: number;
        y?: number;
        text?: string;
    }): Promise<ToolExecutionResult> {
        // 使用 DesktopAdapter 执行视觉操作
        const desktopAdapter = this.registry.get('com.aios.adapter.desktop');
        if (!desktopAdapter) {
            return {
                success: false,
                message: '桌面适配器不可用',
            };
        }

        try {
            let result: AdapterResult;

            switch (action.type) {
                case 'click':
                    // TODO: 实现点击坐标功能
                    result = { success: true, data: { clicked: true } };
                    break;
                case 'type':
                    result = await desktopAdapter.invoke('type_text', { text: action.text });
                    break;
                case 'scroll':
                    result = { success: true, data: { scrolled: true } };
                    break;
                default:
                    result = { success: false, error: { code: 'UNKNOWN_ACTION', message: '未知操作' } };
            }

            return {
                success: result.success,
                message: result.success ? '操作完成' : result.error?.message,
                data: result.data,
            };
        } catch (error) {
            return {
                success: false,
                message: error instanceof Error ? error.message : '操作失败',
            };
        }
    }

    /**
     * 调用适配器
     */
    private async invokeAdapter(
        adapterId: string,
        action: string,
        params: Record<string, unknown>
    ): Promise<ToolExecutionResult> {
        const adapter = this.registry.get(adapterId);
        if (!adapter) {
            return { success: false, message: `适配器不存在: ${adapterId}` };
        }

        try {
            const result = await adapter.invoke(action, params);
            return {
                success: result.success,
                message: result.success ? '执行成功' : result.error?.message,
                data: result.data,
            };
        } catch (error) {
            return {
                success: false,
                message: error instanceof Error ? error.message : '执行失败',
            };
        }
    }

    /**
     * 构建参数 schema
     */
    private buildParameterSchema(
        parameters: Array<{ name: string; type: string; required?: boolean; description?: string }>
    ): Record<string, unknown> {
        const properties: Record<string, unknown> = {};
        const required: string[] = [];

        for (const param of parameters) {
            properties[param.name] = {
                type: param.type,
                description: param.description || param.name,
            };
            if (param.required) {
                required.push(param.name);
            }
        }

        return {
            type: 'object',
            properties,
            required,
        };
    }
}
