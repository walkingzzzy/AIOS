/**
 * EmailAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { EmailAdapter } from '../../adapters/messaging/EmailAdapter';

describe('EmailAdapter', () => {
    let adapter: EmailAdapter;

    beforeEach(() => {
        adapter = new EmailAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('email');
            expect(adapter.name).toBe('Email');
            expect(adapter.permissionLevel).toBe('medium');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('email_send');
            expect(toolNames).toContain('email_list');
        });
    });

    describe('邮件发送', () => {
        it('应该能发送邮件', async () => {
            const result = await adapter.execute('email_send', {
                to: 'test@example.com',
                subject: 'Test Email',
                body: 'This is a test email'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能发送带附件的邮件', async () => {
            const result = await adapter.execute('email_send', {
                to: 'test@example.com',
                subject: 'Test',
                body: 'Test',
                attachments: ['/path/to/file.pdf']
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该拒绝无效的邮箱地址', async () => {
            await expect(
                adapter.execute('email_send', {
                    to: 'invalid-email',
                    subject: 'Test',
                    body: 'Test'
                })
            ).rejects.toThrow();
        });

        it('应该拒绝空主题', async () => {
            await expect(
                adapter.execute('email_send', {
                    to: 'test@example.com',
                    subject: '',
                    body: 'Test'
                })
            ).rejects.toThrow();
        });
    });

    describe('邮件列表', () => {
        it('应该能列出邮件', async () => {
            const result = await adapter.execute('email_list', {
                folder: 'inbox',
                limit: 10
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.emails)).toBe(true);
        });

        it('应该能搜索邮件', async () => {
            const result = await adapter.execute('email_search', {
                query: 'test',
                folder: 'inbox'
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.emails)).toBe(true);
        });
    });
});
