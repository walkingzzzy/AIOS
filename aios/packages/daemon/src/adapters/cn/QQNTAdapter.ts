/**
 * QQ NT 适配器
 * 基于 Electron 调试端口的 CDP 控制
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { randomUUID } from 'node:crypto';

// Playwright 类型
type Browser = import('playwright').Browser;
type BrowserContext = import('playwright').BrowserContext;
type Page = import('playwright').Page;

type PageInfo = {
    id: string;
    url: string;
    title: string;
};

type PageResolveResult =
    | { success: true; pageId: string; page: Page }
    | { success: false; error: AdapterResult };

export class QQNTAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.qqnt';
    readonly name = 'QQ NT';
    readonly description = 'QQ NT 调试端口自动化控制';

    private browser: Browser | null = null;
    private pages: Map<string, Page> = new Map();
    private pageIds: WeakMap<Page, string> = new WeakMap();
    private activePageId: string | null = null;
    private isConnecting = false;

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'qqnt_connect',
            name: '连接调试端口',
            description: '连接 QQ NT Electron 调试端口',
            permissionLevel: 'medium',
            parameters: [
                { name: 'endpoint_url', type: 'string', required: false, description: 'CDP 地址' },
                { name: 'timeout_ms', type: 'number', required: false, description: '连接超时毫秒' },
            ],
        },
        {
            id: 'qqnt_list_pages',
            name: '列出页面',
            description: '列出 QQ NT 已连接页面',
            permissionLevel: 'low',
        },
        {
            id: 'qqnt_set_active_page',
            name: '切换页面',
            description: '切换当前操作页面',
            permissionLevel: 'low',
            parameters: [
                { name: 'page_id', type: 'string', required: true, description: '页面 ID' },
            ],
        },
        {
            id: 'qqnt_eval',
            name: '执行脚本',
            description: '在指定页面执行 JS 表达式',
            permissionLevel: 'medium',
            parameters: [
                { name: 'expression', type: 'string', required: true, description: 'JS 表达式' },
                { name: 'page_id', type: 'string', required: false, description: '页面 ID' },
            ],
        },
        {
            id: 'qqnt_send_text',
            name: '发送文本',
            description: '向指定输入框发送文本并可选触发发送',
            permissionLevel: 'medium',
            parameters: [
                { name: 'input_selector', type: 'string', required: true, description: '输入框选择器' },
                { name: 'text', type: 'string', required: true, description: '文本内容' },
                { name: 'send', type: 'boolean', required: false, description: '是否发送（回车）' },
                { name: 'send_selector', type: 'string', required: false, description: '发送按钮选择器' },
                { name: 'page_id', type: 'string', required: false, description: '页面 ID' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'qqnt_get_messages',
            name: '读取消息',
            description: '读取消息列表文本',
            permissionLevel: 'low',
            parameters: [
                { name: 'message_selector', type: 'string', required: true, description: '消息节点选择器' },
                { name: 'limit', type: 'number', required: false, description: '返回数量' },
                { name: 'page_id', type: 'string', required: false, description: '页面 ID' },
            ],
        },
        {
            id: 'qqnt_disconnect',
            name: '断开连接',
            description: '断开调试端口连接',
            permissionLevel: 'low',
        },
    ];

    async checkAvailability(): Promise<boolean> {
        try {
            await import('playwright');
            return true;
        } catch {
            return false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'qqnt_connect':
                    return this.connect(args.endpoint_url as string | undefined, args.timeout_ms as number | undefined);
                case 'qqnt_list_pages':
                    return this.listPages();
                case 'qqnt_set_active_page':
                    return this.setActivePage(args.page_id as string);
                case 'qqnt_eval':
                    return this.evalExpression(args.expression as string, args.page_id as string | undefined);
                case 'qqnt_send_text':
                    return this.sendText({
                        inputSelector: args.input_selector as string,
                        text: args.text as string,
                        send: args.send as boolean | undefined,
                        sendSelector: args.send_selector as string | undefined,
                        pageId: args.page_id as string | undefined,
                        timeoutMs: args.timeout_ms as number | undefined,
                    });
                case 'qqnt_get_messages':
                    return this.getMessages({
                        messageSelector: args.message_selector as string,
                        limit: args.limit as number | undefined,
                        pageId: args.page_id as string | undefined,
                    });
                case 'qqnt_disconnect':
                    return this.disconnect();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async connect(endpointUrl?: string, timeoutMs?: number): Promise<AdapterResult> {
        if (this.isConnecting) {
            return this.failure('CONNECTING', '正在连接调试端口');
        }

        this.isConnecting = true;
        try {
            const { chromium } = await import('playwright');
            const endpoint = endpointUrl || 'http://127.0.0.1:9222';
            this.browser = await chromium.connectOverCDP(endpoint, {
                timeout: timeoutMs ?? 30000,
            });

            const pages = await this.collectPages();
            return this.success({ connected: true, endpoint, pages });
        } catch (error) {
            this.browser = null;
            this.pages.clear();
            this.activePageId = null;
            return this.failure('CONNECT_FAILED', `连接失败: ${String(error)}`);
        } finally {
            this.isConnecting = false;
        }
    }

    private async listPages(): Promise<AdapterResult> {
        if (!this.browser) {
            return this.failure('NOT_CONNECTED', '尚未连接 QQ NT 调试端口');
        }
        const pages = await this.collectPages();
        return this.success({ pages, active_page_id: this.activePageId });
    }

    private async setActivePage(pageId: string): Promise<AdapterResult> {
        if (!this.browser) {
            return this.failure('NOT_CONNECTED', '尚未连接 QQ NT 调试端口');
        }
        if (!pageId || !this.pages.has(pageId)) {
            return this.failure('PAGE_NOT_FOUND', '未找到对应页面');
        }
        this.activePageId = pageId;
        return this.success({ active_page_id: pageId });
    }

    private async evalExpression(expression: string, pageId?: string): Promise<AdapterResult> {
        if (!expression) {
            return this.failure('INVALID_PARAM', 'expression 不能为空');
        }
        const pageResult = this.resolvePage(pageId);
        if (!pageResult.success) {
            return pageResult.error;
        }
        const result = await pageResult.page.evaluate(expression);
        return this.success({ result, page_id: pageResult.pageId });
    }

    private async sendText(options: {
        inputSelector: string;
        text: string;
        send?: boolean;
        sendSelector?: string;
        pageId?: string;
        timeoutMs?: number;
    }): Promise<AdapterResult> {
        const { inputSelector, text, send, sendSelector, pageId, timeoutMs } = options;
        if (!inputSelector || typeof text !== 'string') {
            return this.failure('INVALID_PARAM', 'input_selector 与 text 为必填参数');
        }

        const pageResult = this.resolvePage(pageId);
        if (!pageResult.success) {
            return pageResult.error;
        }

        const page = pageResult.page;
        const timeout = timeoutMs ?? 10000;
        await page.waitForSelector(inputSelector, { timeout });
        await page.fill(inputSelector, text);

        if (sendSelector) {
            await page.click(sendSelector, { timeout });
        } else if (send) {
            await page.keyboard.press('Enter');
        }

        return this.success({ sent: true, page_id: pageResult.pageId });
    }

    private async getMessages(options: {
        messageSelector: string;
        limit?: number;
        pageId?: string;
    }): Promise<AdapterResult> {
        const { messageSelector, limit, pageId } = options;
        if (!messageSelector) {
            return this.failure('INVALID_PARAM', 'message_selector 不能为空');
        }

        const pageResult = this.resolvePage(pageId);
        if (!pageResult.success) {
            return pageResult.error;
        }

        const messages = await pageResult.page.$$eval(messageSelector, (nodes) =>
            nodes.map((node) => (node as HTMLElement).innerText || '').filter(Boolean)
        );

        const sliced = typeof limit === 'number' ? messages.slice(0, limit) : messages;
        return this.success({ messages: sliced, page_id: pageResult.pageId });
    }

    private async disconnect(): Promise<AdapterResult> {
        if (!this.browser) {
            return this.failure('NOT_CONNECTED', '尚未连接 QQ NT 调试端口');
        }
        await this.browser.close();
        this.browser = null;
        this.pages.clear();
        this.activePageId = null;
        return this.success({ disconnected: true });
    }

    private resolvePage(pageId?: string): PageResolveResult {
        if (!this.browser) {
            return { success: false, error: this.failure('NOT_CONNECTED', '尚未连接 QQ NT 调试端口') };
        }

        const resolvedId = pageId || this.activePageId;
        if (!resolvedId) {
            return { success: false, error: this.failure('PAGE_NOT_FOUND', '未指定页面') };
        }

        const page = this.pages.get(resolvedId);
        if (!page) {
            return { success: false, error: this.failure('PAGE_NOT_FOUND', '未找到对应页面') };
        }

        return { success: true, pageId: resolvedId, page };
    }

    private async collectPages(): Promise<PageInfo[]> {
        if (!this.browser) {
            return [];
        }

        this.pages.clear();
        const pages: PageInfo[] = [];
        const contexts = this.browser.contexts();
        for (const context of contexts) {
            pages.push(...await this.collectContextPages(context));
        }

        if (!this.activePageId && pages[0]) {
            this.activePageId = pages[0].id;
        }

        return pages;
    }

    private async collectContextPages(context: BrowserContext): Promise<PageInfo[]> {
        const pages: PageInfo[] = [];
        for (const page of context.pages()) {
            const id = this.getPageId(page);
            this.pages.set(id, page);
            const url = page.url();
            let title = '';
            try {
                title = await page.title();
            } catch {
                title = '';
            }
            pages.push({ id, url, title });
        }
        return pages;
    }

    private getPageId(page: Page): string {
        const existing = this.pageIds.get(page);
        if (existing) {
            return existing;
        }
        const id = randomUUID();
        this.pageIds.set(page, id);
        return id;
    }
}

export const qqntAdapter = new QQNTAdapter();
