/**
 * 应用管理适配器
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// 动态导入
let open: (target: string) => Promise<unknown>;
let psList: () => Promise<Array<{ pid: number; name: string; cpu: number; memory: number }>>;

export class AppsAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.apps';
    readonly name = '应用管理';
    readonly description = '应用启动、关闭和进程管理';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'open_app',
            name: '打开应用',
            description: '启动指定应用程序',
            permissionLevel: 'low',
            parameters: [
                { name: 'name', type: 'string', required: true, description: '应用名称' },
            ],
        },
        {
            id: 'open_url',
            name: '打开网址',
            description: '在默认浏览器中打开网址',
            permissionLevel: 'low',
            parameters: [
                { name: 'url', type: 'string', required: true, description: 'URL 地址' },
            ],
        },
        {
            id: 'list_processes',
            name: '进程列表',
            description: '获取运行中的进程列表',
            permissionLevel: 'public',
        },
        {
            id: 'kill_process',
            name: '结束进程',
            description: '终止指定进程',
            permissionLevel: 'medium',
            parameters: [
                { name: 'pid', type: 'number', required: true, description: '进程 ID' },
            ],
        },
    ];

    async initialize(): Promise<void> {
        const openMod = await import('open');
        open = openMod.default;
        const psListMod = await import('ps-list');
        psList = psListMod.default;
    }

    async checkAvailability(): Promise<boolean> {
        try {
            await this.initialize();
            return true;
        } catch {
            return false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'open_app':
                    return this.openApp(args.name as string);
                case 'open_url':
                    return this.openUrl(args.url as string);
                case 'list_processes':
                    return this.listProcesses();
                case 'kill_process':
                    return this.killProcess(args.pid as number);
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async openApp(name: string): Promise<AdapterResult> {
        await open(name);
        return this.success({ app: name });
    }

    private async openUrl(url: string): Promise<AdapterResult> {
        await open(url);
        return this.success({ url });
    }

    private async listProcesses(): Promise<AdapterResult> {
        const processes = await psList();
        // 返回前 50 个进程
        const topProcesses = processes.slice(0, 50).map((p) => ({
            pid: p.pid,
            name: p.name,
            cpu: p.cpu,
            memory: p.memory,
        }));
        return this.success({ processes: topProcesses, count: processes.length });
    }

    private async killProcess(pid: number): Promise<AdapterResult> {
        try {
            process.kill(pid);
            return this.success({ pid, killed: true });
        } catch {
            return this.failure('KILL_FAILED', `无法终止进程 ${pid}`);
        }
    }
}

export const appsAdapter = new AppsAdapter();
