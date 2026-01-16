/**
 * GmailAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { GmailAdapter } from '../../adapters/productivity/GmailAdapter';

describe('GmailAdapter', () => {
    let adapter: GmailAdapter;

    beforeEach(() => {
        adapter = new GmailAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('gmail');
            expect(adapter.name).toBe('Gmail');
            expect(adapter.permissionLevel).toBe('high');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('gmail_send');
            expect(toolNames).toContain('gmail_list');
            expect(toolNames).toContain('gmail_search');
        });
    });

    describe('邮件发送', () => {
        it('应该能发送邮件', async () => {
            const result = await adapter.execute('gmail_send', {
                to: 'test@example.com',
                subject: 'Test Email',
                body: 'This is a test email'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能发送带抄送的邮件', async () => {
            const result = await adapter.execute('gmail_send', {
                to: 'test@example.com',
                cc: 'cc@example.com',
                bcc: 'bcc@example.com',
                subject: 'Test',
                body: 'Test'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该拒绝无效的邮箱地址', async () => {
            await expect(
                adapter.execute('gmail_send', {
                    to: 'invalid-email',
                    subject: 'Test',
                    body: 'Test'
                })
            ).rejects.toThrow();
        });
    });

    describe('邮件管理', () => {
        it('应该能列出邮件', async () => {
            const result = await adapter.execute('gmail_list', {
                maxResults: 10
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.messages)).toBe(true);
        });

        it('应该能搜索邮件', async () => {
            const result = await adapter.execute('gmail_search', {
                query: 'from:test@example.com'
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.messages)).toBe(true);
        });

        it('应该能读取邮件', async () => {
            const result = await adapter.execute('gmail_read', {
                messageId: '123456'
            });

            expect(result).toBeDefined();
            expect(result.message).toBeDefined();
        });

        it('应该能删除邮件', async () => {
            const result = await adapter.execute('gmail_delete', {
                messageId: '123456'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });
    });

    describe('标签管理', () => {
        it('应该能列出标签', async () => {
            const result = await adapter.execute('gmail_list_labels', {});

            expect(result).toBeDefined();
            expect(Array.isArray(result.labels)).toBe(true);
        });

        it('应该能添加标签', async () => {
            const result = await adapter.execute('gmail_add_label', {
                messageId: '123456',
                labelId: 'INBOX'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });
    });
});
