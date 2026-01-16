/**
 * DiscordAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { DiscordAdapter } from '../../adapters/messaging/DiscordAdapter';

describe('DiscordAdapter', () => {
    let adapter: DiscordAdapter;

    beforeEach(() => {
        adapter = new DiscordAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('discord');
            expect(adapter.name).toBe('Discord');
            expect(adapter.permissionLevel).toBe('medium');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('discord_send_message');
            expect(toolNames).toContain('discord_list_channels');
        });
    });

    describe('消息发送', () => {
        it('应该能发送消息', async () => {
            const result = await adapter.execute('discord_send_message', {
                channel: 'general',
                content: 'Test message'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能发送嵌入消息', async () => {
            const result = await adapter.execute('discord_send_message', {
                channel: 'general',
                embeds: [{
                    title: 'Test Embed',
                    description: 'Test description',
                    color: 0x00ff00
                }]
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该拒绝空消息', async () => {
            await expect(
                adapter.execute('discord_send_message', {
                    channel: 'general',
                    content: ''
                })
            ).rejects.toThrow();
        });
    });

    describe('频道管理', () => {
        it('应该能列出频道', async () => {
            const result = await adapter.execute('discord_list_channels', {
                guildId: '123456789'
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.channels)).toBe(true);
        });

        it('应该能获取频道信息', async () => {
            const result = await adapter.execute('discord_get_channel_info', {
                channelId: '123456789'
            });

            expect(result).toBeDefined();
            expect(result.channel).toBeDefined();
        });
    });
});
