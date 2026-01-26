/**
 * BrowserAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const currentUrl = { value: 'about:blank' };
const locatorMock = {
    screenshot: vi.fn(async () => undefined),
};
const pageMock = {
    goto: vi.fn(async (url: string) => { currentUrl.value = url; }),
    url: vi.fn(() => currentUrl.value),
    title: vi.fn(async () => 'Test Title'),
    goBack: vi.fn(async () => undefined),
    goForward: vi.fn(async () => undefined),
    reload: vi.fn(async () => undefined),
    waitForSelector: vi.fn(async () => undefined),
    waitForLoadState: vi.fn(async () => undefined),
    waitForTimeout: vi.fn(async () => undefined),
    click: vi.fn(async () => undefined),
    fill: vi.fn(async () => undefined),
    type: vi.fn(async () => undefined),
    press: vi.fn(async () => undefined),
    hover: vi.fn(async () => undefined),
    selectOption: vi.fn(async () => undefined),
    screenshot: vi.fn(async () => undefined),
    content: vi.fn(async () => '<html></html>'),
    evaluate: vi.fn(async () => 'Eval Result'),
    $eval: vi.fn(async () => 'Single'),
    $$eval: vi.fn(async () => [{ name: 'A' }]),
    setViewportSize: vi.fn(async () => undefined),
    keyboard: {
        type: vi.fn(async () => undefined),
        press: vi.fn(async () => undefined),
    },
    mouse: {
        click: vi.fn(async () => undefined),
        wheel: vi.fn(async () => undefined),
    },
    locator: vi.fn(() => locatorMock),
    on: vi.fn(),
    close: vi.fn(async () => undefined),
};
const contextMock = {
    newPage: vi.fn(async () => pageMock),
    close: vi.fn(async () => undefined),
};
const browserMock = {
    newContext: vi.fn(async () => contextMock),
    close: vi.fn(async () => undefined),
};
const browserTypeMock = {
    launch: vi.fn(async () => browserMock),
};

vi.mock('playwright', () => ({
    chromium: browserTypeMock,
    firefox: browserTypeMock,
    webkit: browserTypeMock,
}));
vi.mock('../../core/security/index.js', () => ({
    networkGuard: {
        checkUrl: vi.fn(() => ({ blocked: false, allowed: true })),
    },
}));

import { BrowserAdapter } from '../../adapters/browser/BrowserAdapter';

describe('BrowserAdapter', () => {
    let adapter: BrowserAdapter;

    beforeEach(() => {
        adapter = new BrowserAdapter();
        currentUrl.value = 'about:blank';
        vi.clearAllMocks();
        pageMock.$$eval.mockResolvedValue([{ name: 'A' }]);
    });

    describe('基本功能', () => {
        it('应该正确初始化并包含关键能力', () => {
            expect(adapter.id).toBe('com.aios.adapter.browser');
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('launch');
            expect(capabilityIds).toContain('new_page');
            expect(capabilityIds).toContain('open_url');
            expect(capabilityIds).toContain('click');
            expect(capabilityIds).toContain('fill');
            expect(capabilityIds).toContain('extract_list');
            expect(capabilityIds).toContain('search_and_compare');
        });
    });

    describe('浏览器会话', () => {
        it('应该能启动浏览器并创建页面', async () => {
            const result = await adapter.invoke('launch', { headless: true });

            expect(result.success).toBe(true);
            expect(browserTypeMock.launch).toHaveBeenCalled();
        });

        it('应该能新建页面并返回 page_id', async () => {
            const result = await adapter.invoke('new_page', {});

            expect(result.success).toBe(true);
            expect((result.data as { page_id?: string }).page_id).toBeTruthy();
        });
    });

    describe('页面操作', () => {
        it('应该能打开网址并获取标题', async () => {
            const result = await adapter.invoke('open_url', { url: 'https://example.com' });

            expect(result.success).toBe(true);
            expect(pageMock.goto).toHaveBeenCalled();
        });

        it('应该能点击元素', async () => {
            const result = await adapter.invoke('click', { selector: '#btn' });

            expect(result.success).toBe(true);
            expect(pageMock.click).toHaveBeenCalledWith('#btn', expect.any(Object));
        });

        it('应该能填充文本', async () => {
            const result = await adapter.invoke('fill', { selector: '#input', text: 'hello' });

            expect(result.success).toBe(true);
            expect(pageMock.fill).toHaveBeenCalledWith('#input', 'hello', expect.any(Object));
        });

        it('应该能获取内容', async () => {
            const result = await adapter.invoke('get_content', { content_type: 'html' });

            expect(result.success).toBe(true);
            expect(pageMock.content).toHaveBeenCalled();
        });

        it('应该能提取列表', async () => {
            const result = await adapter.invoke('extract_list', {
                list_selector: '.item',
                fields: [{ name: 'title', selector: '.title' }],
            });

            expect(result.success).toBe(true);
            expect(pageMock.$$eval).toHaveBeenCalled();
        });

        it('应该能执行脚本', async () => {
            const result = await adapter.invoke('evaluate', { script: '() => 1' });

            expect(result.success).toBe(true);
            expect(pageMock.evaluate).toHaveBeenCalled();
        });

        it('应该能截图元素', async () => {
            const result = await adapter.invoke('screenshot', { path: '/tmp/test.png', selector: '.card' });

            expect(result.success).toBe(true);
            expect(locatorMock.screenshot).toHaveBeenCalled();
        });

        it('应该能关闭标签页', async () => {
            const newPage = await adapter.invoke('new_page', {});
            const pageId = (newPage.data as { page_id?: string }).page_id;

            const result = await adapter.invoke('close_page', { page_id: pageId });

            expect(result.success).toBe(true);
            expect(pageMock.close).toHaveBeenCalled();
        });
    });

    describe('比价流程', () => {
        it('应该能执行搜索比价流程', async () => {
            pageMock.$$eval.mockResolvedValueOnce([
                { title: 'Item1', price_text: '¥10', link: 'http://a' },
            ]);

            const result = await adapter.invoke('search_and_compare', {
                query: '测试商品',
                sites: [
                    {
                        name: '站点A',
                        url: 'https://shop.example.com',
                        search_input_selector: '#search',
                        result_list_selector: '.item',
                    },
                ],
            });

            expect(result.success).toBe(true);
            expect(pageMock.waitForSelector).toHaveBeenCalled();
            expect(pageMock.fill).toHaveBeenCalled();
        });
    });
});
