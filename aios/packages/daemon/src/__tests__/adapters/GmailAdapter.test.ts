/**
 * GmailAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { GmailAdapter } from '../../adapters/productivity/GmailAdapter';
import type { OAuthManager } from '../../auth';

describe('GmailAdapter', () => {
    let adapter: GmailAdapter;
    let oauth: OAuthManager;

    beforeEach(() => {
        adapter = new GmailAdapter();
        oauth = {
            isAuthenticated: vi.fn(() => true),
            getAccessToken: vi.fn(async () => 'test-token'),
        } as unknown as OAuthManager;
        adapter.setOAuthManager(oauth);

        const fetchMock = vi.fn(async (url: RequestInfo, init?: RequestInit) => {
            const target = typeof url === 'string' ? url : url.toString();
            const method = init?.method ?? 'GET';

            if (target.includes('/messages/send') && method === 'POST') {
                return { ok: true, status: 200, json: async () => ({ id: 'msg-1' }) } as Response;
            }

            if (target.includes('/messages?') && method === 'GET') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ messages: [{ id: 'msg-1', threadId: 't1' }] }),
                } as Response;
            }

            if (target.includes('/messages/msg-1') && method === 'GET') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ id: 'msg-1', threadId: 't1' }),
                } as Response;
            }

            return { ok: false, status: 500, json: async () => ({}) } as Response;
        });

        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.gmail');
            expect(adapter.name).toBe('Gmail');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('send_email');
            expect(capabilityIds).toContain('list_messages');
            expect(capabilityIds).toContain('get_message');
        });
    });

    describe('邮件操作', () => {
        it('应该能发送邮件', async () => {
            const result = await adapter.invoke('send_email', {
                to: 'test@example.com',
                subject: 'Test Email',
                body: 'Hello',
            });

            expect(result.success).toBe(true);
            expect((result.data as { id?: string }).id).toBe('msg-1');
        });

        it('应该能列出邮件', async () => {
            const result = await adapter.invoke('list_messages', { maxResults: 5 });

            expect(result.success).toBe(true);
            const messages = (result.data as { messages?: unknown[] }).messages;
            expect(Array.isArray(messages)).toBe(true);
        });

        it('应该能读取邮件', async () => {
            const result = await adapter.invoke('get_message', { id: 'msg-1' });

            expect(result.success).toBe(true);
            expect((result.data as { message?: { id?: string } }).message?.id).toBe('msg-1');
        });
    });

    describe('权限检查', () => {
        it('未配置 OAuth 时应该失败', async () => {
            const noAuthAdapter = new GmailAdapter();
            const result = await noAuthAdapter.invoke('list_messages', {});

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('NO_OAUTH');
        });
    });
});
