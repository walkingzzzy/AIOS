/**
 * QQNTAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { QQNTAdapter } from '../../adapters/cn/QQNTAdapter';

const createPageMock = () => {
    const keyboard = { press: vi.fn(async () => undefined) };
    return {
        url: () => 'https://qq.com',
        title: vi.fn(async () => 'QQ NT'),
        evaluate: vi.fn(async () => 'ok'),
        waitForSelector: vi.fn(async () => undefined),
        fill: vi.fn(async () => undefined),
        click: vi.fn(async () => undefined),
        keyboard,
        $$eval: vi.fn(async (_selector: string, handler: (nodes: unknown[]) => unknown) => {
            const nodes = [{ innerText: '消息1' }, { innerText: '消息2' }];
            return handler(nodes as unknown[]);
        }),
    };
};

const pageMock = createPageMock();
const contextMock = {
    pages: () => [pageMock],
};
const browserMock = {
    contexts: () => [contextMock],
    close: vi.fn(async () => undefined),
};

vi.mock('playwright', () => ({
    chromium: {
        connectOverCDP: vi.fn(async () => browserMock),
    },
}));

describe('QQNTAdapter', () => {
    let adapter: QQNTAdapter;

    beforeEach(() => {
        adapter = new QQNTAdapter();
    });

    describe('基本属性', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.qqnt');
            expect(adapter.name).toBe('QQ NT');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });
    });

    describe('连接与页面管理', () => {
        it('未连接时应返回失败', async () => {
            const result = await adapter.invoke('qqnt_list_pages', {});
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('NOT_CONNECTED');
        });

        it('连接后应返回页面列表', async () => {
            const result = await adapter.invoke('qqnt_connect', {});
            expect(result.success).toBe(true);

            const list = await adapter.invoke('qqnt_list_pages', {});
            expect(list.success).toBe(true);
            const pages = (list.data as { pages?: unknown[] }).pages;
            expect(Array.isArray(pages)).toBe(true);
        });

        it('切换不存在页面应失败', async () => {
            await adapter.invoke('qqnt_connect', {});
            const result = await adapter.invoke('qqnt_set_active_page', { page_id: 'missing' });
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('PAGE_NOT_FOUND');
        });
    });

    describe('脚本与消息', () => {
        it('应该执行脚本', async () => {
            await adapter.invoke('qqnt_connect', {});
            const list = await adapter.invoke('qqnt_list_pages', {});
            const pageId = (list.data as { pages: { id: string }[] }).pages[0].id;
            const result = await adapter.invoke('qqnt_eval', { expression: '1+1', page_id: pageId });
            expect(result.success).toBe(true);
        });

        it('应该发送文本并读取消息', async () => {
            await adapter.invoke('qqnt_connect', {});
            const list = await adapter.invoke('qqnt_list_pages', {});
            const pageId = (list.data as { pages: { id: string }[] }).pages[0].id;

            const sendResult = await adapter.invoke('qqnt_send_text', {
                input_selector: '#input',
                text: '你好',
                send: true,
                page_id: pageId,
            });
            expect(sendResult.success).toBe(true);

            const messages = await adapter.invoke('qqnt_get_messages', {
                message_selector: '.msg',
                page_id: pageId,
                limit: 1,
            });
            expect(messages.success).toBe(true);
            const data = messages.data as { messages?: string[] };
            expect(data.messages?.length).toBe(1);
        });
    });
});
