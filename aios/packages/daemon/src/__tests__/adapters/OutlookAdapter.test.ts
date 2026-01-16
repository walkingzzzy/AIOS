/**
 * OutlookAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { OutlookAdapter } from '../../adapters/productivity/OutlookAdapter';

describe('OutlookAdapter', () => {
    let adapter: OutlookAdapter;

    beforeEach(() => {
        adapter = new OutlookAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('outlook');
            expect(adapter.name).toBe('Outlook');
            expect(adapter.permissionLevel).toBe('high');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('outlook_send_email');
            expect(toolNames).toContain('outlook_list_emails');
        });
    });

    describe('邮件操作', () => {
        it('应该能发送邮件', async () => {
            const result = await adapter.execute('outlook_send_email', {
                to: 'test@example.com',
                subject: 'Test',
                body: 'Test body'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能列出邮件', async () => {
            const result = await adapter.execute('outlook_list_emails', {
                folder: 'inbox',
                top: 10
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.emails)).toBe(true);
        });

        it('应该能搜索邮件', async () => {
            const result = await adapter.execute('outlook_search_emails', {
                query: 'test'
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.emails)).toBe(true);
        });
    });

    describe('日历操作', () => {
        it('应该能创建日历事件', async () => {
            const result = await adapter.execute('outlook_create_event', {
                subject: 'Meeting',
                start: new Date().toISOString(),
                end: new Date(Date.now() + 3600000).toISOString()
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能列出日历事件', async () => {
            const result = await adapter.execute('outlook_list_events', {
                startDate: new Date().toISOString(),
                endDate: new Date(Date.now() + 86400000).toISOString()
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.events)).toBe(true);
        });
    });
});
