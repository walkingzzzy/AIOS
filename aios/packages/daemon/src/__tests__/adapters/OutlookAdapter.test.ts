/**
 * OutlookAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { OutlookAdapter } from '../../adapters/productivity/OutlookAdapter';
import type { OAuthManager } from '../../auth';

describe('OutlookAdapter', () => {
    let adapter: OutlookAdapter;
    let oauth: OAuthManager;

    beforeEach(() => {
        adapter = new OutlookAdapter();
        oauth = {
            isAuthenticated: vi.fn(() => true),
            getAccessToken: vi.fn(async () => 'test-token'),
        } as unknown as OAuthManager;
        adapter.setOAuthManager(oauth);

        const fetchMock = vi.fn(async (url: RequestInfo, init?: RequestInit) => {
            const target = typeof url === 'string' ? url : url.toString();
            const method = init?.method ?? 'GET';

            if (target.endsWith('/me/sendMail') && method === 'POST') {
                return { ok: true, status: 202, json: async () => ({}) } as Response;
            }

            if (target.includes('/messages?$top=') && method === 'GET') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({
                        value: [
                            {
                                id: 'msg-1',
                                subject: 'Hello',
                                from: { emailAddress: { address: 'a@example.com', name: 'Alice' } },
                                receivedDateTime: '2024-01-01T00:00:00Z',
                                isRead: false,
                                bodyPreview: 'Preview',
                            },
                        ],
                    }),
                } as Response;
            }

            if (target.includes('/messages/msg-1/reply') && method === 'POST') {
                return { ok: true, status: 202, json: async () => ({}) } as Response;
            }

            if (target.endsWith('/messages/msg-1') && method === 'DELETE') {
                return { ok: true, status: 204, json: async () => ({}) } as Response;
            }

            if (target.endsWith('/messages/msg-1') && method === 'GET') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({
                        id: 'msg-1',
                        subject: 'Hello',
                        from: { emailAddress: { address: 'a@example.com', name: 'Alice' } },
                        toRecipients: [{ emailAddress: { address: 'b@example.com' } }],
                        receivedDateTime: '2024-01-01T00:00:00Z',
                        isRead: true,
                        body: { content: 'Body', contentType: 'Text' },
                    }),
                } as Response;
            }

            return {
                ok: false,
                status: 500,
                json: async () => ({ error: { message: 'fail' } }),
            } as Response;
        });

        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.outlook');
            expect(adapter.name).toBe('Outlook');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('send_email');
            expect(capabilityIds).toContain('list_messages');
            expect(capabilityIds).toContain('get_message');
            expect(capabilityIds).toContain('reply_email');
            expect(capabilityIds).toContain('delete_message');
        });
    });

    describe('邮件操作', () => {
        it('应该能发送邮件', async () => {
            const result = await adapter.invoke('send_email', {
                to: 'b@example.com',
                subject: 'Hi',
                body: 'Test',
            });

            expect(result.success).toBe(true);
            expect((result.data as { sent?: boolean }).sent).toBe(true);
        });

        it('应该能列出邮件', async () => {
            const result = await adapter.invoke('list_messages', {
                folder: 'inbox',
                top: 1,
            });

            expect(result.success).toBe(true);
            const messages = (result.data as { messages?: unknown[] }).messages;
            expect(Array.isArray(messages)).toBe(true);
        });

        it('应该能获取邮件详情', async () => {
            const result = await adapter.invoke('get_message', { id: 'msg-1' });

            expect(result.success).toBe(true);
            expect((result.data as { id?: string }).id).toBe('msg-1');
        });

        it('应该能回复邮件', async () => {
            const result = await adapter.invoke('reply_email', {
                id: 'msg-1',
                body: 'Reply',
            });

            expect(result.success).toBe(true);
            expect((result.data as { replied?: boolean }).replied).toBe(true);
        });

        it('应该能删除邮件', async () => {
            const result = await adapter.invoke('delete_message', { id: 'msg-1' });

            expect(result.success).toBe(true);
            expect((result.data as { deleted?: boolean }).deleted).toBe(true);
        });
    });

    describe('权限检查', () => {
        it('未配置 OAuth 时应该失败', async () => {
            const noAuthAdapter = new OutlookAdapter();
            const result = await noAuthAdapter.invoke('list_messages', {});

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('NO_OAUTH');
        });
    });
});
