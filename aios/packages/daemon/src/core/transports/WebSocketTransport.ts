/**
 * WebSocket 传输层
 * 支持网络 IPC 的 WebSocket 服务器
 */

import { WebSocketServer, WebSocket, type RawData } from 'ws';
import type { JSONRPCRequest, JSONRPCResponse } from '@aios/shared';

export interface WebSocketTransportOptions {
    port?: number;
    host?: string;
}

export interface MessageHandler {
    (request: JSONRPCRequest): Promise<JSONRPCResponse>;
}

export class WebSocketTransport {
    private wss: WebSocketServer | null = null;
    private clients: Set<WebSocket> = new Set();
    private messageHandler: MessageHandler | null = null;
    private options: Required<WebSocketTransportOptions>;

    constructor(options: WebSocketTransportOptions = {}) {
        this.options = {
            port: options.port ?? 8765,
            host: options.host ?? '127.0.0.1',
        };
    }

    /** 设置消息处理器 */
    setMessageHandler(handler: MessageHandler): void {
        this.messageHandler = handler;
    }

    /** 启动 WebSocket 服务器 */
    async start(): Promise<void> {
        return new Promise((resolve, reject) => {
            try {
                this.wss = new WebSocketServer({
                    port: this.options.port,
                    host: this.options.host,
                });

                this.wss.on('connection', (ws: WebSocket) => {
                    this.handleConnection(ws);
                });

                this.wss.on('listening', () => {
                    console.log(`[WebSocket] Server listening on ws://${this.options.host}:${this.options.port}`);
                    resolve();
                });

                this.wss.on('error', (error: Error) => {
                    console.error('[WebSocket] Server error:', error);
                    reject(error);
                });
            } catch (error) {
                reject(error);
            }
        });
    }

    /** 处理客户端连接 */
    private handleConnection(ws: WebSocket): void {
        console.log('[WebSocket] Client connected');
        this.clients.add(ws);

        ws.on('message', async (data: RawData) => {
            await this.handleMessage(ws, data);
        });

        ws.on('close', () => {
            console.log('[WebSocket] Client disconnected');
            this.clients.delete(ws);
        });

        ws.on('error', (error: Error) => {
            console.error('[WebSocket] Client error:', error);
            this.clients.delete(ws);
        });

        // 发送欢迎消息
        this.sendNotification(ws, 'connected', { message: 'AIOS Daemon WebSocket connected' });
    }

    /** 处理接收到的消息 */
    private async handleMessage(ws: WebSocket, data: RawData): Promise<void> {
        try {
            const message = data.toString();
            const request: JSONRPCRequest = JSON.parse(message);

            if (!this.messageHandler) {
                this.sendError(ws, request.id, -32603, 'No message handler registered');
                return;
            }

            const response = await this.messageHandler(request);
            this.send(ws, response);
        } catch (error) {
            console.error('[WebSocket] Message handling error:', error);
            this.sendError(ws, null, -32700, 'Parse error');
        }
    }

    /** 发送响应 */
    private send(ws: WebSocket, response: JSONRPCResponse): void {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(response));
        }
    }

    /** 发送错误响应 */
    private sendError(ws: WebSocket, id: number | string | null, code: number, message: string): void {
        const response: JSONRPCResponse = {
            jsonrpc: '2.0',
            id: id ?? 0,
            error: { code, message },
        };
        this.send(ws, response);
    }

    /** 发送通知 (无需响应的消息) */
    private sendNotification(ws: WebSocket, method: string, params: unknown): void {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                jsonrpc: '2.0',
                method,
                params,
            }));
        }
    }

    /** 广播消息给所有客户端 */
    broadcast(method: string, params: unknown): void {
        const message = JSON.stringify({
            jsonrpc: '2.0',
            method,
            params,
        });

        for (const client of this.clients) {
            if (client.readyState === WebSocket.OPEN) {
                client.send(message);
            }
        }
    }

    /** 获取连接的客户端数量 */
    getClientCount(): number {
        return this.clients.size;
    }

    /** 停止服务器 */
    async stop(): Promise<void> {
        return new Promise((resolve) => {
            if (!this.wss) {
                resolve();
                return;
            }

            // 关闭所有客户端连接
            for (const client of this.clients) {
                client.close(1000, 'Server shutting down');
            }
            this.clients.clear();

            this.wss.close(() => {
                console.log('[WebSocket] Server stopped');
                this.wss = null;
                resolve();
            });
        });
    }
}

/** 创建并导出默认实例 */
export const webSocketTransport = new WebSocketTransport();
