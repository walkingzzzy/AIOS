/**
 * 日历适配器
 * 本地日历事件管理（不依赖外部API）
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

interface CalendarEvent {
    id: string;
    title: string;
    startTime: Date;
    endTime: Date;
    description?: string;
    location?: string;
    reminder?: number; // 分钟
}

export class CalendarAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.calendar';
    readonly name = '日历';
    readonly description = '本地日历事件管理适配器';

    private events: Map<string, CalendarEvent> = new Map();

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'create_event',
            name: '创建事件',
            description: '创建日历事件',
            permissionLevel: 'low',
            parameters: [
                { name: 'title', type: 'string', required: true, description: '事件标题' },
                { name: 'startTime', type: 'string', required: true, description: '开始时间 (ISO格式)' },
                { name: 'endTime', type: 'string', required: false, description: '结束时间 (默认1小时后)' },
                { name: 'description', type: 'string', required: false, description: '描述' },
                { name: 'location', type: 'string', required: false, description: '地点' },
            ],
        },
        {
            id: 'list_events',
            name: '列出事件',
            description: '查询日历事件',
            permissionLevel: 'public',
            parameters: [
                { name: 'date', type: 'string', required: false, description: '查询日期 (默认今天)' },
                { name: 'days', type: 'number', required: false, description: '天数范围 (默认1)' },
            ],
        },
        {
            id: 'delete_event',
            name: '删除事件',
            description: '删除指定事件',
            permissionLevel: 'low',
            parameters: [
                { name: 'id', type: 'string', required: true, description: '事件ID' },
            ],
        },
        {
            id: 'get_next_event',
            name: '获取下一个事件',
            description: '获取最近的即将发生的事件',
            permissionLevel: 'public',
        },
    ];

    async checkAvailability(): Promise<boolean> {
        return true;
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'create_event':
                    return this.createEvent(args);
                case 'list_events':
                    return this.listEvents(args);
                case 'delete_event':
                    return this.deleteEvent(args.id as string);
                case 'get_next_event':
                    return this.getNextEvent();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private createEvent(args: Record<string, unknown>): AdapterResult {
        const title = args.title as string;
        const startTimeStr = args.startTime as string;

        if (!title || !startTimeStr) {
            return this.failure('INVALID_ARGS', '标题和开始时间是必需的');
        }

        const startTime = new Date(startTimeStr);
        if (isNaN(startTime.getTime())) {
            return this.failure('INVALID_ARGS', '无效的开始时间格式');
        }

        const endTimeStr = args.endTime as string | undefined;
        const endTime = endTimeStr
            ? new Date(endTimeStr)
            : new Date(startTime.getTime() + 60 * 60 * 1000); // 默认1小时

        const id = `event_${Date.now()}`;
        const event: CalendarEvent = {
            id,
            title,
            startTime,
            endTime,
            description: args.description as string | undefined,
            location: args.location as string | undefined,
        };

        this.events.set(id, event);

        return this.success({
            id,
            title,
            startTime: startTime.toISOString(),
            endTime: endTime.toISOString(),
        });
    }

    private listEvents(args: Record<string, unknown>): AdapterResult {
        const dateStr = args.date as string | undefined;
        const days = (args.days as number) || 1;

        const baseDate = dateStr ? new Date(dateStr) : new Date();
        baseDate.setHours(0, 0, 0, 0);

        const endDate = new Date(baseDate);
        endDate.setDate(endDate.getDate() + days);

        const events = Array.from(this.events.values())
            .filter(e => e.startTime >= baseDate && e.startTime < endDate)
            .sort((a, b) => a.startTime.getTime() - b.startTime.getTime())
            .map(e => ({
                id: e.id,
                title: e.title,
                startTime: e.startTime.toISOString(),
                endTime: e.endTime.toISOString(),
                description: e.description,
                location: e.location,
            }));

        return this.success({ events, count: events.length });
    }

    private deleteEvent(id: string): AdapterResult {
        if (!id) {
            return this.failure('INVALID_ARGS', '事件ID是必需的');
        }

        if (!this.events.has(id)) {
            return this.failure('EVENT_NOT_FOUND', `事件 ${id} 不存在`);
        }

        this.events.delete(id);
        return this.success({ id, deleted: true });
    }

    private getNextEvent(): AdapterResult {
        const now = new Date();
        const upcoming = Array.from(this.events.values())
            .filter(e => e.startTime > now)
            .sort((a, b) => a.startTime.getTime() - b.startTime.getTime());

        if (upcoming.length === 0) {
            return this.success({ event: null, message: '没有即将发生的事件' });
        }

        const next = upcoming[0];
        return this.success({
            event: {
                id: next.id,
                title: next.title,
                startTime: next.startTime.toISOString(),
                endTime: next.endTime.toISOString(),
                description: next.description,
                location: next.location,
            },
        });
    }
}

export const calendarAdapter = new CalendarAdapter();
