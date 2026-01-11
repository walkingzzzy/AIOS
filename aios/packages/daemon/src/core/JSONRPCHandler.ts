/**
 * JSON-RPC 2.0 处理器
 */

import type { JSONRPCRequest, JSONRPCResponse } from '@aios/shared';

export type MethodHandler = (params: Record<string, unknown>) => Promise<unknown>;

export class JSONRPCHandler {
    private methods: Map<string, MethodHandler> = new Map();

    /** 注册方法 */
    registerMethod(name: string, handler: MethodHandler): void {
        this.methods.set(name, handler);
    }

    /** 处理请求 */
    async handleRequest(request: JSONRPCRequest): Promise<JSONRPCResponse> {
        const { id, method, params } = request;

        // 检查 jsonrpc 版本
        if (request.jsonrpc !== '2.0') {
            return {
                jsonrpc: '2.0',
                id,
                error: {
                    code: -32600,
                    message: 'Invalid Request: jsonrpc must be "2.0"',
                },
            };
        }

        // 查找方法处理器
        const handler = this.methods.get(method);
        if (!handler) {
            return {
                jsonrpc: '2.0',
                id,
                error: {
                    code: -32601,
                    message: `Method not found: ${method}`,
                },
            };
        }

        try {
            const result = await handler((params as Record<string, unknown>) || {});
            return {
                jsonrpc: '2.0',
                id,
                result,
            };
        } catch (error) {
            return {
                jsonrpc: '2.0',
                id,
                error: {
                    code: -32603,
                    message: error instanceof Error ? error.message : String(error),
                },
            };
        }
    }

    /** 解析并处理 JSON 字符串 */
    async handleJSON(json: string): Promise<string> {
        try {
            const request = JSON.parse(json) as JSONRPCRequest;
            const response = await this.handleRequest(request);
            return JSON.stringify(response);
        } catch (error) {
            const response: JSONRPCResponse = {
                jsonrpc: '2.0',
                id: null,
                error: {
                    code: -32700,
                    message: 'Parse error',
                },
            };
            return JSON.stringify(response);
        }
    }
}
