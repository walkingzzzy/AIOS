/**
 * 系统信息适配器
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// 动态导入
let si: typeof import('systeminformation');

export class SystemInfoAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.systeminfo';
    readonly name = '系统信息';
    readonly description = 'CPU、内存、电池等系统信息查询';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'get_cpu',
            name: '获取CPU信息',
            description: '获取 CPU 使用率和信息',
            permissionLevel: 'public',
        },
        {
            id: 'get_memory',
            name: '获取内存信息',
            description: '获取内存使用情况',
            permissionLevel: 'public',
        },
        {
            id: 'get_battery',
            name: '获取电池信息',
            description: '获取电池状态和电量',
            permissionLevel: 'public',
        },
        {
            id: 'get_disk',
            name: '获取磁盘信息',
            description: '获取磁盘使用情况',
            permissionLevel: 'public',
        },
        {
            id: 'get_system',
            name: '获取系统信息',
            description: '获取操作系统信息',
            permissionLevel: 'public',
        },
    ];

    async initialize(): Promise<void> {
        si = await import('systeminformation');
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
                case 'get_cpu':
                    return this.getCpu();
                case 'get_memory':
                    return this.getMemory();
                case 'get_battery':
                    return this.getBattery();
                case 'get_disk':
                    return this.getDisk();
                case 'get_system':
                    return this.getSystem();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async getCpu(): Promise<AdapterResult> {
        const [info, load] = await Promise.all([si.cpu(), si.currentLoad()]);
        return this.success({
            brand: info.brand,
            cores: info.cores,
            speed: info.speed,
            usage: Math.round(load.currentLoad),
        });
    }

    private async getMemory(): Promise<AdapterResult> {
        const mem = await si.mem();
        return this.success({
            total: Math.round(mem.total / 1024 / 1024 / 1024), // GB
            used: Math.round(mem.used / 1024 / 1024 / 1024),
            free: Math.round(mem.free / 1024 / 1024 / 1024),
            usagePercent: Math.round((mem.used / mem.total) * 100),
        });
    }

    private async getBattery(): Promise<AdapterResult> {
        const battery = await si.battery();
        return this.success({
            hasBattery: battery.hasBattery,
            percent: battery.percent,
            isCharging: battery.isCharging,
            timeRemaining: battery.timeRemaining,
        });
    }

    private async getDisk(): Promise<AdapterResult> {
        const disks = await si.fsSize();
        const diskInfo = disks.map((d) => ({
            mount: d.mount,
            size: Math.round(d.size / 1024 / 1024 / 1024), // GB
            used: Math.round(d.used / 1024 / 1024 / 1024),
            usagePercent: Math.round(d.use),
        }));
        return this.success({ disks: diskInfo });
    }

    private async getSystem(): Promise<AdapterResult> {
        const os = await si.osInfo();
        return this.success({
            platform: os.platform,
            distro: os.distro,
            release: os.release,
            arch: os.arch,
            hostname: os.hostname,
        });
    }
}

export const systemInfoAdapter = new SystemInfoAdapter();
