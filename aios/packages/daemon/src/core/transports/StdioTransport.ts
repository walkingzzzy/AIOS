/**
 * stdio 传输层
 * 通过标准输入输出进行 IPC 通信
 */

import * as readline from 'readline';
import { JSONRPCHandler } from '../JSONRPCHandler.js';

export class StdioTransport {
    private handler: JSONRPCHandler;
    private rl: readline.Interface;

    constructor(handler: JSONRPCHandler) {
        this.handler = handler;
        this.rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout,
            terminal: false,
        });
    }

    /** 启动监听 */
    start(): void {
        console.error('[StdioTransport] Started');

        this.rl.on('line', async (line) => {
            if (!line.trim()) return;

            try {
                const response = await this.handler.handleJSON(line);
                // 输出响应到 stdout
                process.stdout.write(response + '\n');
            } catch (error) {
                console.error('[StdioTransport] Error:', error);
            }
        });

        this.rl.on('close', () => {
            console.error('[StdioTransport] Closed');
            process.exit(0);
        });
    }

    /** 停止监听 */
    stop(): void {
        this.rl.close();
    }
}
