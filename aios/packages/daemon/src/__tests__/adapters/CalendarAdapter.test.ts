/**
 * CalendarAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { CalendarAdapter } from '../../adapters/calendar/CalendarAdapter';

describe('CalendarAdapter', () => {
    let adapter: CalendarAdapter;

    beforeEach(() => {
        adapter = new CalendarAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('calendar');
            expect(adapter.name).toBe('Calendar');
            expect(adapter.permissionLevel).toBe('low');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('calendar_create_event');
            expect(toolNames).toContain('calendar_list_events');
            expect(toolNames).toContain('calendar_delete_event');
        });
    });

    describe('日历事件管理', () => {
        it('应该能创建事件', async () => {
            const result = await adapter.execute('calendar_create_event', {
                title: 'Test Meeting',
                startTime: new Date('2026-01-20T10:00:00').toISOString(),
                endTime: new Date('2026-01-20T11:00:00').toISOString(),
                description: 'Test event'
            });

            expect(result).toBeDefined();
            expect(result.eventId).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能列出事件', async () => {
            const result = await adapter.execute('calendar_list_events', {
                startDate: new Date('2026-01-01').toISOString(),
                endDate: new Date('2026-01-31').toISOString()
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.events)).toBe(true);
        });

        it('应该能删除事件', async () => {
            const createResult = await adapter.execute('calendar_create_event', {
                title: 'Test',
                startTime: new Date('2026-01-20T10:00:00').toISOString(),
                endTime: new Date('2026-01-20T11:00:00').toISOString()
            });

            const deleteResult = await adapter.execute('calendar_delete_event', {
                eventId: createResult.eventId
            });

            expect(deleteResult.success).toBe(true);
        });

        it('应该拒绝无效的时间范围', async () => {
            await expect(
                adapter.execute('calendar_create_event', {
                    title: 'Test',
                    startTime: new Date('2026-01-20T11:00:00').toISOString(),
                    endTime: new Date('2026-01-20T10:00:00').toISOString()
                })
            ).rejects.toThrow();
        });

        it('应该拒绝空标题', async () => {
            await expect(
                adapter.execute('calendar_create_event', {
                    title: '',
                    startTime: new Date().toISOString(),
                    endTime: new Date(Date.now() + 3600000).toISOString()
                })
            ).rejects.toThrow();
        });
    });
});
