/**
 * FeishuAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('@larksuiteoapi/node-sdk', () => {
    class Client {
        im = {
            message: {
                create: vi.fn(() => ({
                    withTenantToken: async () => ({ code: 0, data: { message_id: 'msg-1' } }),
                })),
            },
        };
        docx = {
            document: {
                create: vi.fn(() => ({
                    withTenantToken: async () => ({ code: 0, data: { document_id: 'doc-1' } }),
                })),
            },
        };
        constructor(_options: Record<string, unknown>) {}
    }

    return { Client };
}, { virtual: true });

describe('FeishuAdapter', () => {
    let adapter: import('../../adapters/cn/FeishuAdapter').FeishuAdapter;
    let FeishuAdapter: typeof import('../../adapters/cn/FeishuAdapter').FeishuAdapter;

    beforeEach(async () => {
        ({ FeishuAdapter } = await import('../../adapters/cn/FeishuAdapter'));
        adapter = new FeishuAdapter();
    });

    it('缺少凭证应失败', async () => {
        const result = await adapter.invoke('feishu_send_text', {
            receive_id: 'chat123',
            text: '你好',
        });
        expect(result.success).toBe(false);
        expect(result.error?.code).toBe('NO_CREDENTIALS');
    });

    it('应发送文本消息', async () => {
        adapter.setCredentials('app', 'secret', 'tenant');
        const result = await adapter.invoke('feishu_send_text', {
            receive_id: 'chat123',
            text: '你好',
        });
        expect(result.success).toBe(true);
    });

    it('应发送卡片消息', async () => {
        adapter.setCredentials('app', 'secret', 'tenant');
        const result = await adapter.invoke('feishu_send_card', {
            receive_id: 'chat123',
            card: { header: { title: { tag: 'plain_text', content: '测试' } } },
        });
        expect(result.success).toBe(true);
    });

    it('应创建文档', async () => {
        adapter.setCredentials('app', 'secret', 'tenant');
        const result = await adapter.invoke('feishu_create_doc', {
            title: '测试文档',
        });
        expect(result.success).toBe(true);
    });
});
