/**
 * MCPServerV2 - 基于官方 @modelcontextprotocol/sdk 的 MCP 服务端
 * 替代旧的自实现 MCPServer，支持 Resources 和 Prompts
 */

import { McpServer, ResourceTemplate } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { createServer, Server } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import type { AdapterRegistry } from '../core/AdapterRegistry.js';
import type { IncomingMessage } from 'http';
import { ToolExecutor } from '../core/ToolExecutor.js';

export interface MCPServerV2Config {
    port?: number;
    host?: string;
    stdio?: boolean;
    authToken?: string;
}

/**
 * MCP 服务端 V2 - 使用官方 SDK
 * 支持 Tools, Resources, Prompts
 */
export class MCPServerV2 {
    private server: McpServer;
    private httpServer: Server | null = null;
    private wss: WebSocketServer | null = null;
    private registry: AdapterRegistry;
    private clients = new Set<WebSocket>();
    private toolExecutor: ToolExecutor;

    constructor(registry: AdapterRegistry, toolExecutor?: ToolExecutor) {
        this.registry = registry;
        this.toolExecutor = toolExecutor ?? new ToolExecutor(registry);

        // 创建 MCP Server 实例
        this.server = new McpServer({
            name: 'aios-mcp-server',
            version: '1.0.0',
        });

        // 注册工具
        this.registerTools();

        // 注册资源
        this.registerResources();

        // 注册提示模板
        this.registerPrompts();
    }

    /**
     * 注册所有适配器能力为 MCP 工具
     */
    private registerTools(): void {
        for (const adapter of this.registry.getAll()) {
            for (const cap of adapter.capabilities) {
                const toolName = `${adapter.id}_${cap.id}`;

                // 构建参数 schema
                const paramSchema: Record<string, z.ZodType<unknown>> = {};
                for (const param of cap.parameters || []) {
                    switch (param.type) {
                        case 'string':
                            paramSchema[param.name] = param.required
                                ? z.string().describe(param.description || '')
                                : z.string().optional().describe(param.description || '');
                            break;
                        case 'number':
                            paramSchema[param.name] = param.required
                                ? z.number().describe(param.description || '')
                                : z.number().optional().describe(param.description || '');
                            break;
                        case 'boolean':
                            paramSchema[param.name] = param.required
                                ? z.boolean().describe(param.description || '')
                                : z.boolean().optional().describe(param.description || '');
                            break;
                        default:
                            paramSchema[param.name] = z.any().describe(param.description || '');
                    }
                }

                const inputSchema = Object.keys(paramSchema).length > 0
                    ? z.object(paramSchema)
                    : z.object({});

                // 注册工具 - 使用原始 schema shape
                this.server.tool(
                    toolName,
                    cap.description || `${adapter.name} - ${cap.id}`,
                    paramSchema as Record<string, z.ZodType<unknown>>,
                    async (args) => {
                        const result = await this.toolExecutor.execute({
                            tool: adapter.id,
                            action: cap.id,
                            params: args as Record<string, unknown>,
                        });
                        return {
                            content: [{
                                type: 'text' as const,
                                text: JSON.stringify(result, null, 2),
                            }],
                        };
                    }
                );
            }
        }

        console.log(`[MCPServerV2] Registered ${this.registry.getAll().reduce((acc, a) => acc + a.capabilities.length, 0)} tools`);
    }

    /**
     * 注册资源 - 暴露系统信息等
     */
    private registerResources(): void {
        // 适配器列表资源
        this.server.resource(
            'adapters://list',
            'adapters://list',
            async () => ({
                contents: [{
                    uri: 'adapters://list',
                    text: JSON.stringify(
                        this.registry.getAll().map(a => ({
                            id: a.id,
                            name: a.name,
                            description: a.description,
                            capabilities: a.capabilities.map(c => c.id),
                        })),
                        null,
                        2
                    ),
                }],
            })
        );

        // 单个适配器详情资源模板
        this.server.resource(
            'adapters://{adapterId}',
            new ResourceTemplate('adapters://{adapterId}', { list: undefined }),
            async (uri) => {
                const match = uri.href.match(/adapters:\/\/(.+)/);
                const adapterId = match?.[1];
                if (!adapterId) throw new Error('Invalid adapter URI');

                const adapter = this.registry.get(adapterId);
                if (!adapter) throw new Error(`Adapter not found: ${adapterId}`);

                return {
                    contents: [{
                        uri: uri.href,
                        text: JSON.stringify({
                            id: adapter.id,
                            name: adapter.name,
                            description: adapter.description,
                            capabilities: adapter.capabilities,
                        }, null, 2),
                    }],
                };
            }
        );

        console.log('[MCPServerV2] Registered resources');
    }

    /**
     * 注册提示模板
     */
    private registerPrompts(): void {
        // 系统操作提示模板
        this.server.prompt(
            'system_control',
            '系统控制操作提示模板',
            { action: z.string().describe('要执行的操作类型') },
            async (args) => ({
                messages: [{
                    role: 'user',
                    content: {
                        type: 'text' as const,
                        text: `请帮我执行系统操作: ${args.action}。可用的适配器包括音频控制、显示器调节、文件管理等。`,
                    },
                }],
            })
        );

        // 文件操作提示模板
        this.server.prompt(
            'file_operation',
            '文件操作提示模板',
            {
                operation: z.enum(['read', 'write', 'list', 'search']).describe('操作类型'),
                path: z.string().optional().describe('文件或目录路径'),
            },
            async (args) => ({
                messages: [{
                    role: 'user',
                    content: {
                        type: 'text' as const,
                        text: `请执行文件${args.operation === 'read' ? '读取' : args.operation === 'write' ? '写入' : args.operation === 'list' ? '列表' : '搜索'}操作${args.path ? `，路径: ${args.path}` : ''}`,
                    },
                }],
            })
        );

        console.log('[MCPServerV2] Registered prompts');
    }

    /**
     * 启动服务端
     */
    async start(config: MCPServerV2Config = {}): Promise<void> {
        if (config.stdio) {
            await this.startStdio();
        } else {
            await this.startWebSocket(
                config.port || 3001,
                config.host ?? '127.0.0.1',
                config.authToken
            );
        }
    }

    /**
     * stdio 模式启动
     */
    private async startStdio(): Promise<void> {
        const transport = new StdioServerTransport();
        await this.server.connect(transport);
        console.log('[MCPServerV2] Started in stdio mode');
    }

    /**
     * WebSocket 模式启动
     */
    private async startWebSocket(port: number, host: string, authToken?: string): Promise<void> {
        return new Promise((resolve) => {
            this.httpServer = createServer();
            this.wss = new WebSocketServer({ server: this.httpServer });

            this.wss.on('connection', async (ws, req) => {
                if (authToken && !this.isAuthorized(req, authToken)) {
                    ws.close(1008, 'Unauthorized');
                    return;
                }

                this.clients.add(ws);
                console.log('[MCPServerV2] Client connected');

                // 处理消息
                ws.on('message', async (data) => {
                    try {
                        const message = JSON.parse(data.toString());
                        // 使用 server 的内部处理逻辑
                        // 注意：官方 SDK 的 WebSocket 支持仍在开发中
                        // 这里使用简化的实现
                        const response = await this.handleMessage(message);
                        ws.send(JSON.stringify(response));
                    } catch (error) {
                        ws.send(JSON.stringify({
                            jsonrpc: '2.0',
                            id: null,
                            error: { code: -32000, message: (error as Error).message },
                        }));
                    }
                });

                ws.on('close', () => {
                    this.clients.delete(ws);
                    console.log('[MCPServerV2] Client disconnected');
                });
            });

            this.httpServer.listen(port, host, () => {
                console.log(`[MCPServerV2] WebSocket server listening on ws://${host}:${port}`);
                resolve();
            });
        });
    }

    /**
     * 验证授权
     */
    private isAuthorized(req: IncomingMessage, authToken: string): boolean {
        const header = req.headers.authorization;
        if (typeof header === 'string') {
            const match = header.match(/^Bearer\s+(.+)$/i);
            if (match && match[1] === authToken) {
                return true;
            }
        }

        try {
            const url = new URL(req.url || '/', 'http://localhost');
            const tokenFromQuery = url.searchParams.get('token') ?? url.searchParams.get('authToken');
            if (tokenFromQuery && tokenFromQuery === authToken) {
                return true;
            }
        } catch {
            // ignore
        }

        return false;
    }

    /**
     * 处理 JSON-RPC 消息 (WebSocket 模式兼容层)
     */
    private async handleMessage(msg: { id?: number; method: string; params?: unknown }): Promise<unknown> {
        const { id, method, params } = msg;

        try {
            let result: unknown;

            switch (method) {
                case 'initialize':
                    result = {
                        protocolVersion: '2024-11-05',
                        capabilities: { tools: {}, resources: {}, prompts: {} },
                        serverInfo: { name: 'aios-mcp-server', version: '1.0.0' },
                    };
                    break;

                case 'notifications/initialized':
                    result = {};
                    break;

                case 'tools/list':
                    result = { tools: this.getTools() };
                    break;

                case 'tools/call': {
                    const p = params as { name: string; arguments: Record<string, unknown> };
                    result = await this.callTool(p.name, p.arguments);
                    break;
                }

                case 'resources/list':
                    result = { resources: this.getResources() };
                    break;

                case 'prompts/list':
                    result = { prompts: this.getPrompts() };
                    break;

                default:
                    return { jsonrpc: '2.0', id, error: { code: -32601, message: 'Method not found' } };
            }

            return { jsonrpc: '2.0', id, result };
        } catch (error) {
            return { jsonrpc: '2.0', id, error: { code: -32000, message: (error as Error).message } };
        }
    }

    /**
     * 获取工具列表
     */
    private getTools(): Array<{ name: string; description: string; inputSchema: unknown }> {
        const tools: Array<{ name: string; description: string; inputSchema: unknown }> = [];
        for (const adapter of this.registry.getAll()) {
            for (const cap of adapter.capabilities) {
                tools.push({
                    name: `${adapter.id}_${cap.id}`,
                    description: cap.description || `${adapter.name} - ${cap.id}`,
                    inputSchema: cap.parameters ? {
                        type: 'object',
                        properties: Object.fromEntries(
                            cap.parameters.map(p => [p.name, { type: p.type, description: p.description }])
                        ),
                    } : { type: 'object', properties: {} },
                });
            }
        }
        return tools;
    }

    /**
     * 获取资源列表
     */
    private getResources(): Array<{ uri: string; name: string; description?: string }> {
        return [
            { uri: 'adapters://list', name: 'Adapter List', description: '所有可用适配器列表' },
        ];
    }

    /**
     * 获取提示模板列表
     */
    private getPrompts(): Array<{ name: string; description?: string }> {
        return [
            { name: 'system_control', description: '系统控制操作提示模板' },
            { name: 'file_operation', description: '文件操作提示模板' },
        ];
    }

    /**
     * 调用工具
     */
    private async callTool(name: string, args: Record<string, unknown>): Promise<{ content: Array<{ type: string; text: string }> }> {
        const { adapterId, capabilityId } = this.resolveToolName(name);
        const result = await this.toolExecutor.execute({
            tool: adapterId,
            action: capabilityId,
            params: args,
        });
        return { content: [{ type: 'text', text: JSON.stringify(result) }] };
    }

    /**
     * 解析工具名称
     */
    private resolveToolName(name: string): { adapterId: string; capabilityId: string } {
        const matchingAdapterIds = this.registry
            .getAll()
            .map(adapter => adapter.id)
            .filter(adapterId => name.startsWith(`${adapterId}_`))
            .sort((a, b) => b.length - a.length);

        const adapterId = matchingAdapterIds[0];
        if (!adapterId) {
            const [fallbackAdapterId, ...capParts] = name.split('_');
            return { adapterId: fallbackAdapterId, capabilityId: capParts.join('_') };
        }

        return {
            adapterId,
            capabilityId: name.slice(adapterId.length + 1),
        };
    }

    /**
     * 停止服务端
     */
    stop(): void {
        for (const client of this.clients) client.close();
        this.wss?.close();
        this.httpServer?.close();
        console.log('[MCPServerV2] Stopped');
    }
}
