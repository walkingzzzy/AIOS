/**
 * MCPServerRegistry - 管理外部 MCP 服务器连接
 */

import { MCPClientV2, type MCPClientV2Config } from '../protocol/MCPClientV2.js';

export interface ExternalMCPServer {
    name: string;
    type: 'stdio' | 'websocket';
    command?: string;
    args?: string[];
    url?: string;
    status: 'disconnected' | 'connecting' | 'connected' | 'error';
    tools: string[];
    lastError?: string;
    createdAt: number;
}

interface MCPServerRegistryStore {
    servers: ExternalMCPServer[];
}

/**
 * MCP 服务器注册表
 * 管理 AIOS 作为 MCP Client 连接的外部 MCP 服务器
 */
export class MCPServerRegistry {
    private servers = new Map<string, ExternalMCPServer>();
    private clients = new Map<string, MCPClientV2>();
    private storePath: string;

    constructor(storePath?: string) {
        this.storePath = storePath || '';
    }

    /**
     * 初始化，从存储加载配置
     */
    async initialize(): Promise<void> {
        // TODO: 从 SQLite 或配置文件加载已保存的服务器配置
        console.log('[MCPServerRegistry] Initialized');
    }

    /**
     * 列出所有已配置的外部 MCP 服务器
     */
    list(): ExternalMCPServer[] {
        return Array.from(this.servers.values());
    }

    /**
     * 添加外部 MCP 服务器配置
     */
    async add(config: {
        name: string;
        type: 'stdio' | 'websocket';
        command?: string;
        args?: string[];
        url?: string;
    }): Promise<ExternalMCPServer> {
        if (this.servers.has(config.name)) {
            throw new Error(`Server with name '${config.name}' already exists`);
        }

        // 验证配置
        if (config.type === 'stdio' && !config.command) {
            throw new Error('stdio type requires command');
        }
        if (config.type === 'websocket' && !config.url) {
            throw new Error('websocket type requires url');
        }

        const server: ExternalMCPServer = {
            name: config.name,
            type: config.type,
            command: config.command,
            args: config.args || [],
            url: config.url,
            status: 'disconnected',
            tools: [],
            createdAt: Date.now(),
        };

        this.servers.set(config.name, server);

        // TODO: 持久化到存储
        console.log(`[MCPServerRegistry] Added server: ${config.name}`);

        return server;
    }

    /**
     * 移除外部 MCP 服务器配置
     */
    async remove(name: string): Promise<boolean> {
        const server = this.servers.get(name);
        if (!server) {
            return false;
        }

        // 断开连接
        await this.disconnect(name);

        this.servers.delete(name);

        // TODO: 从存储中删除
        console.log(`[MCPServerRegistry] Removed server: ${name}`);

        return true;
    }

    /**
     * 测试 MCP 服务器连接
     */
    async test(name: string): Promise<{ success: boolean; tools?: string[]; error?: string }> {
        const server = this.servers.get(name);
        if (!server) {
            return { success: false, error: `Server '${name}' not found` };
        }

        try {
            // 创建临时客户端进行测试
            const testClient = new MCPClientV2({
                clientName: 'aios-mcp-test',
                clientVersion: '1.0.0',
            });

            const config: MCPClientV2Config = {};
            if (server.type === 'stdio') {
                config.command = server.command;
                config.args = server.args;
            } else {
                config.url = server.url;
            }

            await testClient.connect(config);
            const tools = testClient.getTools().map(t => t.name);
            await testClient.disconnect();

            return { success: true, tools };
        } catch (error: any) {
            return { success: false, error: error.message || 'Connection failed' };
        }
    }

    /**
     * 连接到 MCP 服务器
     */
    async connect(name: string): Promise<void> {
        const server = this.servers.get(name);
        if (!server) {
            throw new Error(`Server '${name}' not found`);
        }

        if (this.clients.has(name)) {
            console.log(`[MCPServerRegistry] Server '${name}' already connected`);
            return;
        }

        server.status = 'connecting';

        try {
            const client = new MCPClientV2({
                clientName: 'aios-mcp-client',
                clientVersion: '1.0.0',
            });

            const config: MCPClientV2Config = {};
            if (server.type === 'stdio') {
                config.command = server.command;
                config.args = server.args;
            } else {
                config.url = server.url;
            }

            await client.connect(config);

            this.clients.set(name, client);
            server.status = 'connected';
            server.tools = client.getTools().map(t => t.name);
            server.lastError = undefined;

            console.log(`[MCPServerRegistry] Connected to server: ${name}, tools: ${server.tools.length}`);
        } catch (error: any) {
            server.status = 'error';
            server.lastError = error.message || 'Connection failed';
            throw error;
        }
    }

    /**
     * 断开 MCP 服务器连接
     */
    async disconnect(name: string): Promise<void> {
        const client = this.clients.get(name);
        if (client) {
            try {
                await client.disconnect();
            } catch (error) {
                console.error(`[MCPServerRegistry] Error disconnecting ${name}:`, error);
            }
            this.clients.delete(name);
        }

        const server = this.servers.get(name);
        if (server) {
            server.status = 'disconnected';
            server.tools = [];
        }

        console.log(`[MCPServerRegistry] Disconnected from server: ${name}`);
    }

    /**
     * 获取指定服务器的客户端
     */
    getClient(name: string): MCPClientV2 | undefined {
        return this.clients.get(name);
    }

    /**
     * 获取所有已连接客户端的工具列表
     */
    getAllTools(): Array<{ serverName: string; toolName: string; description?: string }> {
        const allTools: Array<{ serverName: string; toolName: string; description?: string }> = [];

        for (const [serverName, client] of this.clients) {
            const tools = client.getTools();
            for (const tool of tools) {
                allTools.push({
                    serverName,
                    toolName: tool.name,
                    description: tool.description,
                });
            }
        }

        return allTools;
    }

    /**
     * 调用指定服务器的工具
     */
    async callTool(serverName: string, toolName: string, args: Record<string, unknown>): Promise<unknown> {
        const client = this.clients.get(serverName);
        if (!client) {
            throw new Error(`Server '${serverName}' not connected`);
        }

        return client.callTool(toolName, args);
    }

    /**
     * 断开所有连接
     */
    async disconnectAll(): Promise<void> {
        const names = Array.from(this.clients.keys());
        for (const name of names) {
            await this.disconnect(name);
        }
    }
}

// 单例实例
let registryInstance: MCPServerRegistry | null = null;

export function getMCPServerRegistry(): MCPServerRegistry {
    if (!registryInstance) {
        registryInstance = new MCPServerRegistry();
    }
    return registryInstance;
}

export function initMCPServerRegistry(storePath?: string): MCPServerRegistry {
    registryInstance = new MCPServerRegistry(storePath);
    return registryInstance;
}
