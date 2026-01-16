/**
 * NotificationAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotificationAdapter } from '../../adapters/notification/NotificationAdapter';

describe('NotificationAdapter', () => {
    let adapter: NotificationAdapter;

    beforeEach(() => {
        adapter = new NotificationAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('notification');
            expect(adapter.name).toBe('System Notifications');
            expect(adapter.permissionLevel).toBe('low');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('notification_send');
        });
    });

    describe('通知发送', () => {
        it('应该能发送基本通知', async () => {
            const result = await adapter.execute('notification_send', {
                title: 'Test Notification',
                message: 'This is a test message'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能发送带图标的通知', async () => {
            const result = await adapter.execute('notification_send', {
                title: 'Test',
                message: 'Test message',
                icon: 'info'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该拒绝空标题', async () => {
            await expect(
                adapter.execute('notification_send', {
                    title: '',
                    message: 'Test'
                })
            ).rejects.toThrow();
        });

        it('应该拒绝空消息', async () => {
            await expect(
                adapter.execute('notification_send', {
                    title: 'Test',
                    message: ''
                })
            ).rejects.toThrow();
        });
    });
});
