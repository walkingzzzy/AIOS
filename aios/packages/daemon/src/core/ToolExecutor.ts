/**
 * 工具执行器
 * 封装适配器调用，提供工具定义和执行功能
 */

import type { AdapterResult, InternalToolDefinition } from '@aios/shared';
import type { AdapterRegistry } from './AdapterRegistry.js';
import type { ToolCall } from '../types/orchestrator.js';
import type { HookManager } from './hooks/index.js';
import { traceContextManager } from './trace/index.js';
import { randomUUID } from 'node:crypto';
import { permissionManager } from './PermissionManager.js';
import { confirmationManager } from './orchestration/confirmation/index.js';

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
    /** 工具名称到适配器和action的映射 */
    private toolNameMap: Map<string, { adapterId: string; actionId: string }> = new Map();
    private hookManager?: HookManager;

    constructor(registry: AdapterRegistry) {
        this.registry = registry;
    }

    setHookManager(hookManager?: HookManager): void {
        this.hookManager = hookManager;
    }

    /**
     * 从适配器ID中提取简短名称
     *例如: "com.aios.adapter.audio" -> "audio"
     */
    private extractShortName(adapterId: string): string {
        const parts = adapterId.split('.');
        return parts[parts.length - 1];
    }

    /**
     * 获取可用工具定义（内部格式，用于 AI Function Calling）
     *每个action生成一个独立的tool，工具名称格式为{adapter}_{action}
     */
    getAvailableTools(): InternalToolDefinition[] {
        const adapters = this.registry.getAll();
        const tools: InternalToolDefinition[] = [];
        // 清空工具名称映射
        this.toolNameMap.clear();

        for (const adapter of adapters) {
            const shortName = this.extractShortName(adapter.id);
            
            for (const capability of adapter.capabilities) {
                // 生成工具名称: {adapter_short_name}_{action_name}
                const toolName = `${shortName}_${capability.id}`;
                
                // 记录工具名称到适配器和action的映射
                this.toolNameMap.set(toolName, {
                    adapterId: adapter.id,
                    actionId: capability.id,
                });
                
                tools.push({
                    name: toolName,
                    description: capability.description,
                    parameters: this.buildParameterSchema(capability.parameters || []),
                });
            }
        }

        return tools;
    }

    /**
     * 执行工具调用
     *支持两种格式:
     * 1. 新格式: toolCall.tool为{adapter}_{action} 格式 (如"audio_set_volume")
     * 2. 旧格式: toolCall.tool 为适配器ID, toolCall.action 为action名称
     */
    async execute(
        toolCall: ToolCall,
        context?: { taskId?: string; sessionId?: string }
    ): Promise<ToolExecutionResult> {
        const { tool, action, params } = toolCall;

        // 首先检查是否为新格式的工具名称 (如 "audio_set_volume")
        const mapping = this.toolNameMap.get(tool);
        if (mapping) {
            return this.invokeAdapter(mapping.adapterId, mapping.actionId, params, context);
        }

        // 直接匹配适配器 ID（兼容包含 "_" 的适配器 ID）
        const directAdapter = this.registry.get(tool);
        if (directAdapter) {
            return this.invokeAdapter(directAdapter.id, action, params, context);
        }

        // 尝试解析 {adapter}_{action} 格式
        const underscoreIndex = tool.indexOf('_');
        if (underscoreIndex > 0) {
            const adapterShortName = tool.substring(0, underscoreIndex);
            const actionName = tool.substring(underscoreIndex + 1);
            
            // 查找匹配的适配器
            const allAdapters = this.registry.getAll();
            const matched = allAdapters.find(a => 
                this.extractShortName(a.id).toLowerCase() === adapterShortName.toLowerCase()
            );
            
            if (matched) {
                return this.invokeAdapter(matched.id, actionName, params, context);
            }
        }

        // 回退到旧逻辑：按名称模糊匹配适配器
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
            return this.invokeAdapter(matched.id, action, params, context);
        }

        return this.invokeAdapter(tool, action, params, context);
    }

    /**
     * 执行视觉操作（点击、滑动等）
     */
    async executeAction(action: {
        type: 'click' | 'type' | 'scroll';
        x?: number;
        y?: number;
        text?: string;
    }, context?: { taskId?: string; sessionId?: string }): Promise<ToolExecutionResult> {
        // 使用 DesktopAdapter 执行视觉操作
        const desktopAdapter = this.registry.get('com.aios.adapter.desktop');
        if (!desktopAdapter) {
            return {
                success: false,
                message: '桌面适配器不可用',
            };
        }

        try {
            switch (action.type) {
                case 'click':
                    return this.invokeAdapter(desktopAdapter.id, 'click', { x: action.x, y: action.y }, context);
                case 'type':
                    return this.invokeAdapter(desktopAdapter.id, 'type_text', { text: action.text }, context);
                case 'scroll':
                    return this.invokeAdapter(desktopAdapter.id, 'scroll', { direction: 'down', amount: 3 }, context);
                default:
                    return {
                        success: false,
                        message: '未知操作',
                    };
            }
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
        params: Record<string, unknown>,
        context?: { taskId?: string; sessionId?: string }
    ): Promise<ToolExecutionResult> {
        const adapter = this.registry.get(adapterId);
        if (!adapter) {
            return { success: false, message: `适配器不存在: ${adapterId}` };
        }
        const capabilityDef = adapter.capabilities.find(c => c.id === action);
        if (!capabilityDef) {
            return { success: false, message: `能力不存在: ${adapterId}.${action}` };
        }

        if (capabilityDef.permissionLevel !== 'public') {
            const permCheck = await permissionManager.checkPermission(capabilityDef.permissionLevel);
            if (!permCheck.granted) {
                return {
                    success: false,
                    message: `Permission denied: ${capabilityDef.permissionLevel} level required. ${permCheck.details || ''}`.trim(),
                };
            }
        }

        if (capabilityDef.permissionLevel === 'high' || capabilityDef.permissionLevel === 'critical') {
            const approved = await confirmationManager.requestConfirmation({
                taskId: context?.taskId ?? `tool-${adapterId}-${action}`,
                sessionId: context?.sessionId,
                action: `${adapterId}.${action}`,
                riskLevel: capabilityDef.permissionLevel,
                details: {
                    adapterId,
                    action,
                    params,
                },
            });
            if (!approved) {
                return { success: false, message: '用户拒绝执行此高危操作' };
            }
        }

        const toolId = randomUUID();
        const timestamp = Date.now();
        await this.hookManager?.triggerToolCall({
            toolId,
            adapterId,
            capabilityId: action,
            params,
            timestamp,
            sessionId: context?.sessionId,
            taskId: context?.taskId,
            traceId: traceContextManager.getTraceId(),
        });

        try {
            const startTime = Date.now();
            const result = await adapter.invoke(action, params);
            const duration = Date.now() - startTime;

            await this.hookManager?.triggerToolResult({
                toolId,
                adapterId,
                capabilityId: action,
                params,
                timestamp,
                sessionId: context?.sessionId,
                taskId: context?.taskId,
                traceId: traceContextManager.getTraceId(),
                success: result.success,
                result: result.data,
                error: result.success ? undefined : new Error(result.error?.message ?? '执行失败'),
                duration,
            });

            return {
                success: result.success,
                message: result.success ? '执行成功' : result.error?.message,
                data: result.data,
            };
        } catch (error) {
            const err = error instanceof Error ? error : new Error(String(error));
            await this.hookManager?.triggerToolResult({
                toolId,
                adapterId,
                capabilityId: action,
                params,
                timestamp,
                sessionId: context?.sessionId,
                taskId: context?.taskId,
                traceId: traceContextManager.getTraceId(),
                success: false,
                error: err,
                duration: Date.now() - timestamp,
            });

            return {
                success: false,
                message: err.message,
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
