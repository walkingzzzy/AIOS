/**
 * 日历适配器
 * 使用 Google Calendar API 管理事件
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import type { OAuthManager } from '../../auth/index.js';

interface GoogleCalendarEventTime {
    dateTime?: string;
    date?: string;
}

interface GoogleCalendarEvent {
    id: string;
    summary?: string;
    description?: string;
    location?: string;
    start?: GoogleCalendarEventTime;
    end?: GoogleCalendarEventTime;
    htmlLink?: string;
}

interface GoogleCalendarEventsResponse {
    items?: GoogleCalendarEvent[];
}

export class CalendarAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.calendar';
    readonly name = '日历';
    readonly description = 'Google Calendar 事件管理适配器';

    private oauth: OAuthManager | null = null;
    private readonly providerId = 'google';

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
                { name: 'calendarId', type: 'string', required: false, description: '日历 ID (默认 primary)' },
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
                { name: 'calendarId', type: 'string', required: false, description: '日历 ID (默认 primary)' },
            ],
        },
        {
            id: 'delete_event',
            name: '删除事件',
            description: '删除指定事件',
            permissionLevel: 'low',
            parameters: [
                { name: 'id', type: 'string', required: true, description: '事件ID' },
                { name: 'calendarId', type: 'string', required: false, description: '日历 ID (默认 primary)' },
            ],
        },
        {
            id: 'get_next_event',
            name: '获取下一个事件',
            description: '获取最近的即将发生的事件',
            permissionLevel: 'public',
        },
    ];

    setOAuthManager(oauth: OAuthManager): void {
        this.oauth = oauth;
    }

    async checkAvailability(): Promise<boolean> {
        return this.oauth?.isAuthenticated(this.providerId) ?? false;
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        if (!this.oauth) {
            return this.failure('NO_OAUTH', 'OAuth manager not configured');
        }

        try {
            const token = await this.oauth.getAccessToken(this.providerId);
            switch (capability) {
                case 'create_event':
                    return this.createEvent(token, args);
                case 'list_events':
                    return this.listEvents(token, args);
                case 'delete_event':
                    return this.deleteEvent(token, args.id as string, args.calendarId as string | undefined);
                case 'get_next_event':
                    return this.getNextEvent(token, args.calendarId as string | undefined);
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private resolveCalendarId(input?: string): string {
        if (typeof input === 'string' && input.trim()) {
            return input.trim();
        }
        return 'primary';
    }

    private normalizeDateTime(value: string): string | null {
        const dt = new Date(value);
        if (Number.isNaN(dt.getTime())) {
            return null;
        }
        return dt.toISOString();
    }

    private parseEventTime(time?: GoogleCalendarEventTime): string | null {
        if (!time) return null;
        return time.dateTime ?? time.date ?? null;
    }

    private async createEvent(token: string, args: Record<string, unknown>): Promise<AdapterResult> {
        const title = args.title as string;
        const startTimeStr = args.startTime as string;

        if (!title || !startTimeStr) {
            return this.failure('INVALID_ARGS', '标题和开始时间是必需的');
        }

        const startTime = this.normalizeDateTime(startTimeStr);
        if (!startTime) {
            return this.failure('INVALID_ARGS', '无效的开始时间格式');
        }

        const endTimeStr = args.endTime as string | undefined;
        const resolvedEnd = endTimeStr ? this.normalizeDateTime(endTimeStr) : new Date(new Date(startTime).getTime() + 60 * 60 * 1000).toISOString();
        if (!resolvedEnd) {
            return this.failure('INVALID_ARGS', '无效的结束时间格式');
        }

        const calendarId = this.resolveCalendarId(args.calendarId as string | undefined);
        const res = await fetch(`https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(calendarId)}/events`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({
                summary: title,
                description: args.description as string | undefined,
                location: args.location as string | undefined,
                start: { dateTime: startTime },
                end: { dateTime: resolvedEnd },
            }),
        });

        if (!res.ok) {
            return this.failure('CALENDAR_ERROR', `API error: ${res.status}`);
        }

        const data = await res.json() as GoogleCalendarEvent;
        return this.success({
            id: data.id,
            title: data.summary,
            startTime,
            endTime: resolvedEnd,
            link: data.htmlLink,
        });
    }

    private async listEvents(token: string, args: Record<string, unknown>): Promise<AdapterResult> {
        const dateStr = args.date as string | undefined;
        const days = (args.days as number) || 1;
        const calendarId = this.resolveCalendarId(args.calendarId as string | undefined);

        const baseDate = dateStr ? new Date(dateStr) : new Date();
        baseDate.setHours(0, 0, 0, 0);
        const endDate = new Date(baseDate);
        endDate.setDate(endDate.getDate() + days);

        const params = new URLSearchParams({
            timeMin: baseDate.toISOString(),
            timeMax: endDate.toISOString(),
            singleEvents: 'true',
            orderBy: 'startTime',
        });

        const res = await fetch(`https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(calendarId)}/events?${params}`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });

        if (!res.ok) {
            return this.failure('CALENDAR_ERROR', `API error: ${res.status}`);
        }

        const data = await res.json() as GoogleCalendarEventsResponse;
        const events = (data.items ?? []).map((event) => ({
            id: event.id,
            title: event.summary,
            startTime: this.parseEventTime(event.start),
            endTime: this.parseEventTime(event.end),
            description: event.description,
            location: event.location,
            link: event.htmlLink,
        }));

        return this.success({ events, count: events.length });
    }

    private async deleteEvent(token: string, id: string, calendarIdInput?: string): Promise<AdapterResult> {
        if (!id) {
            return this.failure('INVALID_ARGS', '事件ID是必需的');
        }

        const calendarId = this.resolveCalendarId(calendarIdInput);
        const res = await fetch(`https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(calendarId)}/events/${encodeURIComponent(id)}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` },
        });

        if (!res.ok) {
            return this.failure('CALENDAR_ERROR', `API error: ${res.status}`);
        }

        return this.success({ id, deleted: true });
    }

    private async getNextEvent(token: string, calendarIdInput?: string): Promise<AdapterResult> {
        const calendarId = this.resolveCalendarId(calendarIdInput);
        const params = new URLSearchParams({
            timeMin: new Date().toISOString(),
            maxResults: '1',
            singleEvents: 'true',
            orderBy: 'startTime',
        });

        const res = await fetch(`https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(calendarId)}/events?${params}`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });

        if (!res.ok) {
            return this.failure('CALENDAR_ERROR', `API error: ${res.status}`);
        }

        const data = await res.json() as GoogleCalendarEventsResponse;
        const next = data.items?.[0];
        if (!next) {
            return this.success({ event: null, message: '没有即将发生的事件' });
        }

        return this.success({
            event: {
                id: next.id,
                title: next.summary,
                startTime: this.parseEventTime(next.start),
                endTime: this.parseEventTime(next.end),
                description: next.description,
                location: next.location,
                link: next.htmlLink,
            },
        });
    }
}

export const calendarAdapter = new CalendarAdapter();
