/**
 * DiscordAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { DiscordAdapter } from '../../adapters/messaging/DiscordAdapter';

describe('DiscordAdapter', () => {
    let adapter: DiscordAdapter;

    beforeEach(() => {
        adapter = new DiscordAdapter();
        adapter.setToken('test-token');

        const fetchMock = vi.fn(async (url: RequestInfo) => {
            const target = typeof url === 'string' ? url : url.toString();

            if (target.includes('/messages')) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ id: 'msg-1', channel_id: 'C1' }),
                } as Response;
            }

            if (target.includes('/guilds')) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ([{ id: 'G1', name: 'Guild' }]),
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
            expect(adapter.id).toBe('com.aios.adapter.discord');
            expect(adapter.name).toBe('Discord');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('send_message');
            expect(capabilityIds).toContain('list_guilds');
        });
    });

    describe('消息与服务器', () => {
        it('应该能发送消息', async () => {
            const result = await adapter.invoke('send_message', {
                channelId: 'C1',
                content: 'Test message',
            });

            expect(result.success).toBe(true);
            expect((result.data as { id?: string }).id).toBeDefined();
        });

        it('应该能列出服务器', async () => {
            const result = await adapter.invoke('list_guilds', {});

            expect(result.success).toBe(true);
            const guilds = (result.data as { guilds?: unknown[] }).guilds;
            expect(Array.isArray(guilds)).toBe(true);
        });
    });

    describe('权限检查', () => {
        it('缺少 token 时应该失败', async () => {
            adapter.setToken('');
            const result = await adapter.invoke('list_guilds', {});

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('NO_TOKEN');
        });
    });
});
