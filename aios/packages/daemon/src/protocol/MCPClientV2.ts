/**
 * MCPClientV2 - 基于官方 @modelcontextprotocol/sdk 的 MCP 客户端
 * 替代旧的自实现 MCPClient
 */

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { WebSocketClientTransport } from '@modelcontextprotocol/sdk/client/websocket.js';
import { z } from 'zod';
import { spawn, ChildProcess } from 'child_process';
import WebSocket from 'ws';

export interface MCPToolV2 {
    name: string;
    description?: string;
    inputSchema: z.ZodType<unknown>;
}

export interface MCPClientV2Config {
    /** stdio 模式：执行命令 */
    command?: string;
    /** stdio 模式：命令参数 */
    args?: string[];
    /** WebSocket 模式：服务端 URL */
    url?: string;
    /** 客户端名称 */
    clientName?: string;
    /** 客户端版本 */
    clientVersion?: string;
}

/**
 * MCP 客户端 V2 - 使用官方 SDK
 */
export class MCPClientV2 {
    private client: Client;
    private transport: StdioClientTransport | WebSocketClientTransport | null = null;
    private tools: MCPToolV2[] = [];
    private connected = false;
    private process: ChildProcess | null = null;

    constructor(config?: { clientName?: string; clientVersion?: string }) {
        this.client = new Client({
            name: config?.clientName ?? 'aios-mcp-client',
            version: config?.clientVersion ?? '1.0.0',
        }, {
            capabilities: {},
        });
    }

    /**
     * 连接到 MCP 服务端
     */
    async connect(config: MCPClientV2Config): Promise<void> {
        if (this.connected) {
            console.warn('[MCPClientV2] Already connected');
            return;
        }

        if (config.command) {
            await this.connectStdio(config.command, config.args || []);
        } else if (config.url) {
            await this.connectWebSocket(config.url);
        } else {
            throw new Error('Must provide command or url');
        }

        // 连接后获取工具列表
        await this.refreshTools();
        this.connected = true;
        console.log(`[MCPClientV2] Connected, found ${this.tools.length} tools`);
    }

    /**
     * 通过 stdio 连接
     */
    private async connectStdio(command: string, args: string[]): Promise<void> {
        // 启动子进程
        this.process = spawn(command, args, {
            stdio: ['pipe', 'pipe', 'inherit'],
        });

        this.transport = new StdioClientTransport({
            command,
            args,
        });

        await this.client.connect(this.transport);
    }

    /**
     * 通过 WebSocket 连接
     */
    private async connectWebSocket(url: string): Promise<void> {
        // 使用 ws 库创建 WebSocket
        const ws = new WebSocket(url);

        this.transport = new WebSocketClientTransport(ws as any);
        await this.client.connect(this.transport);
    }

    /**
     * 刷新工具列表
     */
    async refreshTools(): Promise<void> {
        const result = await this.client.listTools();
        this.tools = (result.tools || []).map(tool => ({
            name: tool.name,
            description: tool.description,
            inputSchema: z.any(), // SDK 返回的是 JSON Schema，这里简化处理
        }));
    }

    /**
     * 获取可用工具列表
     */
    getTools(): MCPToolV2[] {
        return [...this.tools];
    }

    /**
     * 调用工具
     */
    async callTool(name: string, args: Record<string, unknown>): Promise<unknown> {
        const result = await this.client.callTool({
            name,
            arguments: args,
        });

        // 提取文本内容
        if (result.content && Array.isArray(result.content)) {
            const textContents = result.content
                .filter((c): c is { type: 'text'; text: string } => c.type === 'text')
                .map(c => c.text);
            return textContents.length === 1 ? textContents[0] : textContents;
        }

        return result.content;
    }

    /**
     * 列出可用资源
     */
    async listResources(): Promise<Array<{ uri: string; name: string; description?: string }>> {
        const result = await this.client.listResources();
        return (result.resources || []).map(r => ({
            uri: r.uri,
            name: r.name,
            description: r.description,
        }));
    }

    /**
     * 读取资源内容
     */
    async readResource(uri: string): Promise<string> {
        const result = await this.client.readResource({ uri });

        if (result.contents && Array.isArray(result.contents)) {
            const textContents = result.contents
                .filter((c): c is { uri: string; text: string } => 'text' in c)
                .map(c => c.text);
            return textContents.join('\n');
        }

        return '';
    }

    /**
     * 列出可用提示模板
     */
    async listPrompts(): Promise<Array<{ name: string; description?: string }>> {
        const result = await this.client.listPrompts();
        return (result.prompts || []).map(p => ({
            name: p.name,
            description: p.description,
        }));
    }

    /**
     * 获取提示模板
     */
    async getPrompt(name: string, args?: Record<string, string>): Promise<string> {
        const result = await this.client.getPrompt({
            name,
            arguments: args,
        });

        if (result.messages && Array.isArray(result.messages)) {
            return result.messages
                .map(m => {
                    if (typeof m.content === 'string') return m.content;
                    if (m.content && 'text' in m.content) return m.content.text;
                    return '';
                })
                .join('\n');
        }

        return '';
    }

    /**
     * 断开连接
     */
    async disconnect(): Promise<void> {
        if (!this.connected) return;

        try {
            await this.client.close();
        } catch {
            // ignore close errors
        }

        if (this.process) {
            this.process.kill();
            this.process = null;
        }

        this.transport = null;
        this.connected = false;
        this.tools = [];
        console.log('[MCPClientV2] Disconnected');
    }

    /**
     * 检查是否已连接
     */
    isConnected(): boolean {
        return this.connected;
    }
}
