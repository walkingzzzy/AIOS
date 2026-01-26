/**
 * SlackAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { SlackAdapter } from '../../adapters/messaging/SlackAdapter';

describe('SlackAdapter', () => {
    let adapter: SlackAdapter;

    beforeEach(() => {
        adapter = new SlackAdapter();
        adapter.setToken('test-token');

        const fetchMock = vi.fn(async (url: RequestInfo) => {
            const target = typeof url === 'string' ? url : url.toString();

            if (target.includes('chat.postMessage')) {
                return {
                    json: async () => ({ ok: true, ts: '123.456', channel: 'C123' }),
                };
            }

            if (target.includes('conversations.history')) {
                return {
                    json: async () => ({
                        ok: true,
                        messages: [
                            { ts: '1', text: 'hello', user: 'U1', type: 'message' },
                        ],
                    }),
                };
            }

            if (target.includes('conversations.list')) {
                return {
                    json: async () => ({
                        ok: true,
                        channels: [{ id: 'C1', name: 'general' }],
                    }),
                };
            }

            if (target.includes('users.list')) {
                return {
                    json: async () => ({
                        ok: true,
                        members: [{ id: 'U1', name: 'alice', real_name: 'Alice' }],
                    }),
                };
            }

            return {
                json: async () => ({ ok: false, error: 'not_found' }),
            };
        });

        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.slack');
            expect(adapter.name).toBe('Slack');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('send_message');
            expect(capabilityIds).toContain('list_channels');
            expect(capabilityIds).toContain('get_messages');
            expect(capabilityIds).toContain('get_users');
        });
    });

    describe('消息发送', () => {
        it('应该能发送消息', async () => {
            const result = await adapter.invoke('send_message', {
                channel: '#general',
                text: 'Test message',
            });

            expect(result.success).toBe(true);
            expect((result.data as { ts?: string }).ts).toBeDefined();
        });
    });

    describe('频道与用户', () => {
        it('应该能列出频道', async () => {
            const result = await adapter.invoke('list_channels', {});

            expect(result.success).toBe(true);
            const channels = (result.data as { channels?: unknown[] }).channels;
            expect(Array.isArray(channels)).toBe(true);
        });

        it('应该能获取频道消息', async () => {
            const result = await adapter.invoke('get_messages', { channel: 'C1', limit: 1 });

            expect(result.success).toBe(true);
            const messages = (result.data as { messages?: unknown[] }).messages;
            expect(Array.isArray(messages)).toBe(true);
        });

        it('应该能获取用户列表', async () => {
            const result = await adapter.invoke('get_users', {});

            expect(result.success).toBe(true);
            const users = (result.data as { users?: unknown[] }).users;
            expect(Array.isArray(users)).toBe(true);
        });
    });

    describe('权限检查', () => {
        it('缺少 token 时应该失败', async () => {
            adapter.setToken('');
            const result = await adapter.invoke('list_channels', {});

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('NO_TOKEN');
        });
    });
});
