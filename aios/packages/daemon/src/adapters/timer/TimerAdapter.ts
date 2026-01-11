/**
 * 定时器适配器
 * 跨平台定时器/闹钟功能
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// 动态导入 node-schedule
let schedule: {
    scheduleJob: (date: Date, callback: () => void) => { cancel: () => boolean };
};

interface Timer {
    id: string;
    name: string;
    endTime: Date;
    job: { cancel: () => boolean };
}

export class TimerAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.timer';
    readonly name = '定时器';
    readonly description = '跨平台定时器/闹钟适配器';

    private timers: Map<string, Timer> = new Map();

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'create_timer',
            name: '创建定时器',
            description: '创建一个定时器，到期后发送通知',
            permissionLevel: 'low',
            parameters: [
                { name: 'name', type: 'string', required: true, description: '定时器名称' },
                { name: 'duration', type: 'number', required: true, description: '持续时间（秒）' },
            ],
        },
        {
            id: 'cancel_timer',
            name: '取消定时器',
            description: '取消指定的定时器',
            permissionLevel: 'low',
            parameters: [
                { name: 'id', type: 'string', required: true, description: '定时器 ID' },
            ],
        },
        {
            id: 'list_timers',
            name: '列出定时器',
            description: '列出所有活跃的定时器',
            permissionLevel: 'public',
        },
    ];

    async initialize(): Promise<void> {
        const mod = await import('node-schedule');
        schedule = mod.default || mod;
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
                case 'create_timer':
                    return this.createTimer(args.name as string, args.duration as number);
                case 'cancel_timer':
                    return this.cancelTimer(args.id as string);
                case 'list_timers':
                    return this.listTimers();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private createTimer(name: string, duration: number): AdapterResult {
        if (!name || !duration || duration <= 0) {
            return this.failure('INVALID_ARGS', '名称和有效的持续时间是必需的');
        }

        const id = `timer_${Date.now()}`;
        const endTime = new Date(Date.now() + duration * 1000);

        const job = schedule.scheduleJob(endTime, () => {
            console.log(`[TimerAdapter] Timer "${name}" completed`);
            this.timers.delete(id);
            // 可以在这里触发通知
        });

        this.timers.set(id, { id, name, endTime, job });

        return this.success({
            id,
            name,
            endTime: endTime.toISOString(),
            duration,
        });
    }

    private cancelTimer(id: string): AdapterResult {
        const timer = this.timers.get(id);
        if (!timer) {
            return this.failure('TIMER_NOT_FOUND', `定时器 ${id} 不存在`);
        }

        timer.job.cancel();
        this.timers.delete(id);

        return this.success({ id, cancelled: true });
    }

    private listTimers(): AdapterResult {
        const timers = Array.from(this.timers.values()).map((t) => ({
            id: t.id,
            name: t.name,
            endTime: t.endTime.toISOString(),
            remaining: Math.max(0, (t.endTime.getTime() - Date.now()) / 1000),
        }));

        return this.success({ timers, count: timers.length });
    }

    async shutdown(): Promise<void> {
        // 取消所有定时器
        for (const timer of this.timers.values()) {
            timer.job.cancel();
        }
        this.timers.clear();
    }
}

export const timerAdapter = new TimerAdapter();
