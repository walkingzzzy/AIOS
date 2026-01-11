#!/usr/bin/env node
/**
 * AIOS CLI 客户端
 * 简单的交互式命令行界面
 */

import * as readline from 'readline';
import { spawn, type ChildProcess } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));

class AIOSClient {
    private daemon: ChildProcess | null = null;
    private requestId = 0;
    private pendingRequests: Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }> = new Map();
    private buffer = '';

    /** 启动 daemon 进程 */
    async start(): Promise<void> {
        const daemonPath = join(__dirname, '../../daemon/dist/index.js');

        console.log('🚀 Starting AIOS Daemon...');

        this.daemon = spawn('node', [daemonPath], {
            stdio: ['pipe', 'pipe', 'inherit'],
        });

        this.daemon.stdout?.on('data', (data: Buffer) => {
            this.buffer += data.toString();
            this.processBuffer();
        });

        this.daemon.on('error', (error) => {
            console.error('❌ Daemon error:', error.message);
        });

        this.daemon.on('exit', (code) => {
            console.log(`Daemon exited with code ${code}`);
            process.exit(code || 0);
        });

        // 等待 daemon 就绪
        await this.waitForReady();
    }

    private async waitForReady(): Promise<void> {
        return new Promise((resolve) => {
            setTimeout(resolve, 1000);
        });
    }

    private processBuffer(): void {
        const lines = this.buffer.split('\n');
        this.buffer = lines.pop() || '';

        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const response = JSON.parse(line);
                const pending = this.pendingRequests.get(response.id);
                if (pending) {
                    this.pendingRequests.delete(response.id);
                    if (response.error) {
                        pending.reject(new Error(response.error.message));
                    } else {
                        pending.resolve(response.result);
                    }
                }
            } catch {
                // Ignore parse errors
            }
        }
    }

    /** 发送 JSON-RPC 请求 */
    async call(method: string, params?: Record<string, unknown>): Promise<unknown> {
        const id = ++this.requestId;
        const request = {
            jsonrpc: '2.0',
            id,
            method,
            params,
        };

        return new Promise((resolve, reject) => {
            this.pendingRequests.set(id, { resolve, reject });
            this.daemon?.stdin?.write(JSON.stringify(request) + '\n');

            // 超时
            setTimeout(() => {
                if (this.pendingRequests.has(id)) {
                    this.pendingRequests.delete(id);
                    reject(new Error('Request timeout'));
                }
            }, 30000);
        });
    }

    /** 停止 daemon */
    stop(): void {
        this.daemon?.kill();
    }
}

async function main() {
    console.log('╔═══════════════════════════════════════╗');
    console.log('║         AIOS Protocol CLI             ║');
    console.log('║    AI-Powered System Control          ║');
    console.log('╚═══════════════════════════════════════╝');
    console.log('');

    const client = new AIOSClient();

    try {
        await client.start();
    } catch (error) {
        console.error('❌ Failed to start daemon. Run `pnpm build` first.');
        process.exit(1);
    }

    // 检查连接
    try {
        const ping = await client.call('ping');
        console.log('✅ Connected to daemon');
        console.log('');
    } catch {
        console.error('❌ Failed to connect to daemon');
        process.exit(1);
    }

    // 显示可用适配器
    try {
        const adapters = await client.call('getAdapters') as any[];
        console.log('📦 Available adapters:');
        for (const adapter of adapters) {
            console.log(`   • ${adapter.name} (${adapter.id})`);
        }
        console.log('');
    } catch (error) {
        console.error('Failed to get adapters:', error);
    }

    console.log('Commands:');
    console.log('  volume <0-100>    Set volume');
    console.log('  brightness <0-100> Set brightness');
    console.log('  lock              Lock screen');
    console.log('  battery           Get battery info');
    console.log('  adapters          List adapters');
    console.log('  quit              Exit');
    console.log('');

    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });

    rl.setPrompt('aios> ');
    rl.prompt();

    rl.on('line', async (line) => {
        const input = line.trim().toLowerCase();
        const [command, ...args] = input.split(/\s+/);

        try {
            switch (command) {
                case 'quit':
                case 'exit':
                case 'q':
                    client.stop();
                    process.exit(0);
                    break;

                case 'volume':
                    if (args[0]) {
                        const result = await client.call('invoke', {
                            adapterId: 'com.aios.adapter.audio',
                            capability: 'set_volume',
                            args: { volume: parseInt(args[0]) },
                        });
                        console.log('✅ Volume set:', result);
                    } else {
                        const result = await client.call('invoke', {
                            adapterId: 'com.aios.adapter.audio',
                            capability: 'get_volume',
                            args: {},
                        });
                        console.log('🔊 Current volume:', result);
                    }
                    break;

                case 'brightness':
                    if (args[0]) {
                        const result = await client.call('invoke', {
                            adapterId: 'com.aios.adapter.display',
                            capability: 'set_brightness',
                            args: { brightness: parseInt(args[0]) },
                        });
                        console.log('✅ Brightness set:', result);
                    } else {
                        const result = await client.call('invoke', {
                            adapterId: 'com.aios.adapter.display',
                            capability: 'get_brightness',
                            args: {},
                        });
                        console.log('☀️ Current brightness:', result);
                    }
                    break;

                case 'lock':
                    await client.call('invoke', {
                        adapterId: 'com.aios.adapter.power',
                        capability: 'lock_screen',
                        args: {},
                    });
                    console.log('🔒 Screen locked');
                    break;

                case 'battery':
                    const battery = await client.call('invoke', {
                        adapterId: 'com.aios.adapter.systeminfo',
                        capability: 'get_battery',
                        args: {},
                    });
                    console.log('🔋 Battery:', battery);
                    break;

                case 'adapters':
                    const adapters = await client.call('getAdapters') as any[];
                    for (const adapter of adapters) {
                        console.log(`\n${adapter.name} (${adapter.id})`);
                        for (const cap of adapter.capabilities) {
                            console.log(`  • ${cap.id}: ${cap.description}`);
                        }
                    }
                    break;

                case '':
                    break;

                default:
                    console.log('Unknown command. Type "quit" to exit.');
            }
        } catch (error) {
            console.error('❌ Error:', error instanceof Error ? error.message : error);
        }

        rl.prompt();
    });

    rl.on('close', () => {
        client.stop();
        process.exit(0);
    });
}

main().catch(console.error);
