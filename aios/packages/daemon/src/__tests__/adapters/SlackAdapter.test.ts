/**
 * SlackAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SlackAdapter } from '../../adapters/messaging/SlackAdapter';

describe('SlackAdapter', () => {
    let adapter: SlackAdapter;

    beforeEach(() => {
        adapter = new SlackAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('slack');
            expect(adapter.name).toBe('Slack');
            expect(adapter.permissionLevel).toBe('medium');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('slack_send_message');
            expect(toolNames).toContain('slack_list_channels');
        });
    });

    describe('消息发送', () => {
        it('应该能发送消息', async () => {
            const result = await adapter.execute('slack_send_message', {
                channel: '#general',
                text: 'Test message'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能发送带附件的消息', async () => {
            const result = await adapter.execute('slack_send_message', {
                channel: '#general',
                text: 'Test',
                attachments: [{
                    title: 'Attachment',
                    text: 'Attachment text'
                }]
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该拒绝空消息', async () => {
            await expect(
                adapter.execute('slack_send_message', {
                    channel: '#general',
                    text: ''
                })
            ).rejects.toThrow();
        });
    });

    describe('频道管理', () => {
        it('应该能列出频道', async () => {
            const result = await adapter.execute('slack_list_channels', {});

            expect(result).toBeDefined();
            expect(Array.isArray(result.channels)).toBe(true);
        });

        it('应该能获取频道信息', async () => {
            const result = await adapter.execute('slack_get_channel_info', {
                channel: '#general'
            });

            expect(result).toBeDefined();
            expect(result.channel).toBeDefined();
        });
    });
});
