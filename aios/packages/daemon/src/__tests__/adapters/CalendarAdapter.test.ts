/**
 * CalendarAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { CalendarAdapter } from '../../adapters/calendar/CalendarAdapter';

describe('CalendarAdapter', () => {
    let adapter: CalendarAdapter;

    beforeEach(() => {
        adapter = new CalendarAdapter();
        adapter.setOAuthManager({
            isAuthenticated: () => true,
            getAccessToken: async () => 'mock-token',
        } as any);
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2024-01-01T00:00:00Z'));

        vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString();
            if (init?.method === 'DELETE') {
                return { ok: true, status: 204 } as Response;
            }
            if (init?.method === 'POST') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({
                        id: 'event_1',
                        summary: 'Meeting',
                        htmlLink: 'https://calendar.google.com/event?id=event_1',
                    }),
                } as Response;
            }
            if (url.includes('maxResults=1')) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({
                        items: [
                            {
                                id: 'event_next',
                                summary: 'Soon',
                                start: { dateTime: '2024-01-01T01:00:00.000Z' },
                                end: { dateTime: '2024-01-01T02:00:00.000Z' },
                            },
                        ],
                    }),
                } as Response;
            }
            return {
                ok: true,
                status: 200,
                json: async () => ({
                    items: [
                        {
                            id: 'event_1',
                            summary: 'Meeting',
                            start: { dateTime: '2024-01-01T10:00:00.000Z' },
                            end: { dateTime: '2024-01-01T11:00:00.000Z' },
                        },
                    ],
                }),
            } as Response;
        }));
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.calendar');
            expect(adapter.name).toBe('日历');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('create_event');
            expect(capabilityIds).toContain('list_events');
            expect(capabilityIds).toContain('delete_event');
            expect(capabilityIds).toContain('get_next_event');
        });
    });

    describe('事件管理', () => {
        it('应该能创建并列出事件', async () => {
            const createResult = await adapter.invoke('create_event', {
                title: 'Meeting',
                startTime: '2024-01-01T10:00:00Z',
                endTime: '2024-01-01T11:00:00Z',
            });

            expect(createResult.success).toBe(true);

            const listResult = await adapter.invoke('list_events', {
                date: '2024-01-01',
                days: 1,
            });

            expect(listResult.success).toBe(true);
            const events = (listResult.data as { events?: unknown[] }).events;
            expect(Array.isArray(events)).toBe(true);
            expect(events?.length).toBe(1);
        });

        it('应该能删除事件', async () => {
            const createResult = await adapter.invoke('create_event', {
                title: 'To delete',
                startTime: '2024-01-01T12:00:00Z',
            });
            const id = (createResult.data as { id?: string }).id as string;

            const deleteResult = await adapter.invoke('delete_event', { id });
            expect(deleteResult.success).toBe(true);
        });

        it('应该返回最近事件', async () => {
            await adapter.invoke('create_event', {
                title: 'Soon',
                startTime: '2024-01-01T01:00:00Z',
            });

            const result = await adapter.invoke('get_next_event', {});
            expect(result.success).toBe(true);
            expect((result.data as { event?: { title?: string } }).event?.title).toBe('Soon');
        });

        it('应该拒绝无效参数', async () => {
            const result = await adapter.invoke('create_event', { title: '' });
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('INVALID_ARGS');
        });
    });
});
