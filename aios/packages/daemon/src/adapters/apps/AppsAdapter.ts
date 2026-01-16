/**
 * 应用管理适配器
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { SoftwareDiscovery } from '../../core/SoftwareDiscovery.js';

// 进程信息类型（按照 typescript skill 要求，匹配 ps-list 返回类型）
interface ProcessInfo {
    pid: number;
    name: string;
    cpu?: number;
    memory?: number;
}

// 动态导入
let open: (target: string) => Promise<unknown>;
let psList: () => Promise<ProcessInfo[]>;

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
            id: 'list_installed_apps',
            name: '已安装应用列表',
            description: '扫描并列出已安装应用（跨平台）',
            permissionLevel: 'public',
        },
        {
            id: 'search_installed_apps',
            name: '搜索已安装应用',
            description: '按名称搜索已安装应用',
            permissionLevel: 'public',
            parameters: [
                { name: 'query', type: 'string', required: true, description: '搜索关键词' },
            ],
        },
        {
            id: 'find_installed_app',
            name: '按 BundleId/AppId 查找应用',
            description: '按 bundleId（macOS）或 AppID（Windows）查找已安装应用',
            permissionLevel: 'public',
            parameters: [
                { name: 'bundleId', type: 'string', required: true, description: 'bundleId / AppID' },
            ],
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
        {
            id: 'close_app',
            name: '关闭应用',
            description: '按名称关闭应用程序',
            permissionLevel: 'medium',
            parameters: [
                { name: 'name', type: 'string', required: true, description: '应用名称' },
            ],
        },
    ];

    async initialize(): Promise<void> {
        const openMod = await import('open');
        open = openMod.default;
        const psListMod = await import('ps-list');
        psList = psListMod.default;
    }

    private discovery = new SoftwareDiscovery();

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
                case 'list_installed_apps':
                    return this.listInstalledApps();
                case 'search_installed_apps':
                    return this.searchInstalledApps(args.query as string);
                case 'find_installed_app':
                    return this.findInstalledApp(args.bundleId as string);
                case 'kill_process':
                    return this.killProcess(args.pid as number);
                case 'close_app':
                    return this.closeApp(args.name as string);
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

    private async listInstalledApps(): Promise<AdapterResult> {
        const apps = await this.discovery.scan();
        return this.success({ apps, count: apps.length });
    }

    private async searchInstalledApps(query: string): Promise<AdapterResult> {
        const apps = await this.discovery.search(query);
        return this.success({ apps, count: apps.length, query });
    }

    private async findInstalledApp(bundleId: string): Promise<AdapterResult> {
        const app = await this.discovery.findByBundleId(bundleId);
        return this.success({ app: app ?? null });
    }

    private async killProcess(pid: number): Promise<AdapterResult> {
        try {
            process.kill(pid);
            return this.success({ pid, killed: true });
        } catch {
            return this.failure('KILL_FAILED', `无法终止进程 ${pid}`);
        }
    }

    private async closeApp(name: string): Promise<AdapterResult> {
        const processes = await psList();
        const matched = processes.filter(p => p.name.toLowerCase().includes(name.toLowerCase()));
        for (const p of matched) {
            process.kill(p.pid);
        }
        return this.success({ name, killed: matched.length });
    }
}

export const appsAdapter = new AppsAdapter();
