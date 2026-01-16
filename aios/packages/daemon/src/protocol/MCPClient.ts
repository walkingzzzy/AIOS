import { spawn, ChildProcess } from 'child_process';
import { EventEmitter } from 'events';
import WebSocket from 'ws';

export interface MCPTool {
    name: string;
    description: string;
    inputSchema: object;
}

export interface MCPClientConfig {
    command?: string;
    args?: string[];
    url?: string;
}

export class MCPClient extends EventEmitter {
    private process: ChildProcess | null = null;
    private ws: WebSocket | null = null;
    private requestId = 0;
    private pendingRequests = new Map<number, { resolve: Function; reject: Function }>();
    private tools: MCPTool[] = [];

    async connect(config: MCPClientConfig): Promise<void> {
        if (config.command) {
            await this.connectStdio(config.command, config.args || []);
        } else if (config.url) {
            await this.connectWebSocket(config.url);
        } else {
            throw new Error('Must provide command or url');
        }
        await this.initialize();
    }

    private async connectStdio(command: string, args: string[]): Promise<void> {
        this.process = spawn(command, args, { stdio: ['pipe', 'pipe', 'inherit'] });

        let buffer = '';
        this.process.stdout!.on('data', (data) => {
            buffer += data.toString();
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                if (line.trim()) this.handleMessage(JSON.parse(line));
            }
        });
    }

    private async connectWebSocket(url: string): Promise<void> {
        return new Promise((resolve, reject) => {
            this.ws = new WebSocket(url);
            this.ws.on('open', () => resolve());
            this.ws.on('error', (e) => reject(e));
            this.ws.on('message', (data) => this.handleMessage(JSON.parse(data.toString())));
        });
    }

    private async initialize(): Promise<void> {
        await this.request('initialize', {
            protocolVersion: '2024-11-05',
            capabilities: {},
            clientInfo: { name: 'aios', version: '1.0.0' }
        });
        await this.request('notifications/initialized', {});
        const result = await this.request('tools/list', {});
        this.tools = result.tools || [];
    }

    private handleMessage(msg: any): void {
        if (msg.id !== undefined && this.pendingRequests.has(msg.id)) {
            const { resolve, reject } = this.pendingRequests.get(msg.id)!;
            this.pendingRequests.delete(msg.id);
            if (msg.error) reject(new Error(msg.error.message));
            else resolve(msg.result);
        }
    }

    private async request(method: string, params: object): Promise<any> {
        const id = ++this.requestId;
        const msg = JSON.stringify({ jsonrpc: '2.0', id, method, params });

        return new Promise((resolve, reject) => {
            this.pendingRequests.set(id, { resolve, reject });
            if (this.process) this.process.stdin!.write(msg + '\n');
            else if (this.ws) this.ws.send(msg);
        });
    }

    getTools(): MCPTool[] {
        return this.tools;
    }

    async callTool(name: string, args: object): Promise<any> {
        const result = await this.request('tools/call', { name, arguments: args });
        return result.content;
    }

    disconnect(): void {
        if (this.process) {
            this.process.kill();
            this.process = null;
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.pendingRequests.clear();
        this.tools = [];
    }
}