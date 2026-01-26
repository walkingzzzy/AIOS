/**
 * NotificationAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotificationAdapter } from '../../adapters/notification/NotificationAdapter';

vi.mock('node-notifier', () => ({
    default: {
        notify: vi.fn((_options: unknown, cb?: (err: Error | null) => void) => cb?.(null)),
    },
}));

describe('NotificationAdapter', () => {
    let adapter: NotificationAdapter;

    beforeEach(async () => {
        adapter = new NotificationAdapter();
        await adapter.initialize();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.notification');
            expect(adapter.name).toBe('桌面通知');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('notify');
        });
    });

    describe('通知发送', () => {
        it('应该能发送基本通知', async () => {
            const result = await adapter.invoke('notify', {
                title: 'Test Notification',
                message: 'This is a test message',
            });

            expect(result.success).toBe(true);
            expect((result.data as { sent?: boolean }).sent).toBe(true);
        });

        it('应该拒绝空标题', async () => {
            const result = await adapter.invoke('notify', {
                title: '',
                message: 'Test',
            });

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('INVALID_ARGS');
        });

        it('应该拒绝空消息', async () => {
            const result = await adapter.invoke('notify', {
                title: 'Test',
                message: '',
            });

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('INVALID_ARGS');
        });
    });
});
