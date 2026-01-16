import type { IncomingMessage } from 'http';
import { createServer, Server } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import { AdapterRegistry } from '../core/AdapterRegistry.js';

export interface MCPServerConfig {
    port?: number;
    host?: string;
    stdio?: boolean;
    authToken?: string;
}

export class MCPServer {
    private httpServer: Server | null = null;
    private wss: WebSocketServer | null = null;
    private registry: AdapterRegistry;
    private clients = new Set<WebSocket>();

    constructor(registry: AdapterRegistry) {
        this.registry = registry;
    }

    async start(config: MCPServerConfig = {}): Promise<void> {
        if (config.stdio) {
            this.startStdio();
        } else {
            await this.startWebSocket(
                config.port || 3001,
                config.host ?? '127.0.0.1',
                config.authToken
            );
        }
    }

    private startStdio(): void {
        let buffer = '';
        process.stdin.setEncoding('utf8');
        process.stdin.on('data', (data) => {
            buffer += data;
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                if (line.trim()) {
                    this.handleMessage(JSON.parse(line))
                        .then((response) => {
                            process.stdout.write(JSON.stringify(response) + '\n');
                        })
                        .catch((error) => {
                            process.stdout.write(
                                JSON.stringify({
                                    jsonrpc: '2.0',
                                    id: null,
                                    error: { code: -32000, message: (error as Error).message },
                                }) + '\n'
                            );
                        });
                }
            }
        });
    }

    private async startWebSocket(port: number, host: string, authToken?: string): Promise<void> {
        return new Promise((resolve) => {
            this.httpServer = createServer();
            this.wss = new WebSocketServer({ server: this.httpServer });

            this.wss.on('connection', (ws, req) => {
                if (authToken && !this.isAuthorized(req, authToken)) {
                    ws.close(1008, 'Unauthorized');
                    return;
                }

                this.clients.add(ws);
                ws.on('message', async (data) => {
                    const response = await this.handleMessage(JSON.parse(data.toString()));
                    ws.send(JSON.stringify(response));
                });
                ws.on('close', () => this.clients.delete(ws));
            });

            this.httpServer.listen(port, host, () => resolve());
        });
    }

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

    private async handleMessage(msg: any): Promise<any> {
        const { id, method, params } = msg;

        try {
            let result;
            switch (method) {
                case 'initialize':
                    result = {
                        protocolVersion: '2024-11-05',
                        capabilities: { tools: {} },
                        serverInfo: { name: 'aios-mcp-server', version: '1.0.0' }
                    };
                    break;
                case 'notifications/initialized':
                    result = {};
                    break;
                case 'tools/list':
                    result = { tools: this.getTools() };
                    break;
                case 'tools/call':
                    result = await this.callTool(params.name, params.arguments);
                    break;
                default:
                    return { jsonrpc: '2.0', id, error: { code: -32601, message: 'Method not found' } };
            }
            return { jsonrpc: '2.0', id, result };
        } catch (error) {
            return { jsonrpc: '2.0', id, error: { code: -32000, message: (error as Error).message } };
        }
    }

    private getTools(): any[] {
        const tools: any[] = [];
        for (const adapter of this.registry.getAll()) {
            for (const cap of adapter.capabilities) {
                tools.push({
                    name: `${adapter.id}_${cap.id}`,
                    description: cap.description,
                    inputSchema: cap.parameters ? {
                        type: 'object',
                        properties: Object.fromEntries(
                            cap.parameters.map(p => [p.name, { type: p.type, description: p.description }])
                        )
                    } : { type: 'object', properties: {} }
                });
            }
        }
        return tools;
    }

    private resolveToolName(name: string): { adapterId: string; capabilityId: string } {
        const matchingAdapterIds = this.registry
            .getAll()
            .map(adapter => adapter.id)
            .filter(adapterId => name.startsWith(`${adapterId}_`))
            .sort((a, b) => b.length - a.length);

        const adapterId = matchingAdapterIds[0];
        if (!adapterId) {
            // 回退：尽量兼容旧逻辑（adapterId 不含 "_" 的场景）
            const [fallbackAdapterId, ...capParts] = name.split('_');
            return { adapterId: fallbackAdapterId, capabilityId: capParts.join('_') };
        }

        return {
            adapterId,
            capabilityId: name.slice(adapterId.length + 1),
        };
    }

    private async callTool(name: string, args: Record<string, unknown>): Promise<any> {
        const { adapterId, capabilityId } = this.resolveToolName(name);
        const adapter = this.registry.get(adapterId);
        if (!adapter) {
            throw new Error(`Adapter not found: ${adapterId}`);
        }
        const result = await adapter.invoke(capabilityId, args);
        return { content: [{ type: 'text', text: JSON.stringify(result) }] };
    }

    stop(): void {
        for (const client of this.clients) client.close();
        this.wss?.close();
        this.httpServer?.close();
    }
}
