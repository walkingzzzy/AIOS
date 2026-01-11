/**
 * 浏览器控制适配器
 * 使用 Playwright 实现浏览器自动化
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// Playwright 类型
type Browser = import('playwright').Browser;
type Page = import('playwright').Page;

export class BrowserAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.browser';
    readonly name = '浏览器控制';
    readonly description = '浏览器自动化控制 (Playwright)';

    private browser: Browser | null = null;
    private page: Page | null = null;
    private isInitializing = false;
    private headless = true; // 默认无头模式

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'open_url',
            name: '打开网址',
            description: '在浏览器中打开指定网址',
            permissionLevel: 'low',
            parameters: [
                { name: 'url', type: 'string', required: true, description: '要打开的网址' },
                { name: 'headless', type: 'boolean', required: false, description: '是否无头模式 (默认 true)' },
            ],
        },
        {
            id: 'get_current_url',
            name: '获取当前网址',
            description: '获取当前页面的网址',
            permissionLevel: 'public',
        },
        {
            id: 'search',
            name: '搜索',
            description: '使用搜索引擎搜索',
            permissionLevel: 'low',
            parameters: [
                { name: 'query', type: 'string', required: true, description: '搜索关键词' },
                { name: 'engine', type: 'string', required: false, description: '搜索引擎 (google/bing)' },
            ],
        },
        {
            id: 'go_back',
            name: '后退',
            description: '返回上一页',
            permissionLevel: 'low',
        },
        {
            id: 'go_forward',
            name: '前进',
            description: '前进到下一页',
            permissionLevel: 'low',
        },
        {
            id: 'refresh',
            name: '刷新',
            description: '刷新当前页面',
            permissionLevel: 'low',
        },
        {
            id: 'screenshot',
            name: '截图',
            description: '截取当前页面截图',
            permissionLevel: 'low',
            parameters: [
                { name: 'path', type: 'string', required: true, description: '保存路径' },
            ],
        },
        {
            id: 'get_title',
            name: '获取标题',
            description: '获取当前页面标题',
            permissionLevel: 'public',
        },
        {
            id: 'close',
            name: '关闭浏览器',
            description: '关闭浏览器实例',
            permissionLevel: 'low',
        },
    ];

    // 不在 initialize 中启动浏览器，改为懒加载
    async initialize(): Promise<void> {
        // 仅检查 playwright 是否可用
    }

    async checkAvailability(): Promise<boolean> {
        try {
            await import('playwright');
            return true;
        } catch {
            return false;
        }
    }

    /**
     * 懒加载浏览器实例
     */
    private async ensureBrowser(headless?: boolean): Promise<{ browser: Browser; page: Page }> {
        // 如果已有浏览器且 headless 模式匹配，直接返回
        if (this.browser && this.page) {
            return { browser: this.browser, page: this.page };
        }

        // 防止并发初始化
        if (this.isInitializing) {
            // 等待初始化完成
            while (this.isInitializing) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            if (this.browser && this.page) {
                return { browser: this.browser, page: this.page };
            }
        }

        this.isInitializing = true;
        try {
            const { chromium } = await import('playwright');
            const useHeadless = headless ?? this.headless;
            
            this.browser = await chromium.launch({ headless: useHeadless });
            const context = await this.browser.newContext();
            this.page = await context.newPage();
            
            console.log(`[BrowserAdapter] Browser launched (headless: ${useHeadless})`);
            return { browser: this.browser, page: this.page };
        } catch (error) {
            console.error('[BrowserAdapter] Failed to launch browser:', error);
            throw new Error('浏览器启动失败，请确保已安装 Playwright');
        } finally {
            this.isInitializing = false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            // close 不需要浏览器实例
            if (capability === 'close') {
                return this.closeBrowser();
            }

            // 其他操作需要确保浏览器已启动
            const { page } = await this.ensureBrowser(args.headless as boolean | undefined);

            switch (capability) {
                case 'open_url':
                    return this.openURL(page, args.url as string);
                case 'get_current_url':
                    return this.getCurrentURL(page);
                case 'search':
                    return this.search(page, args.query as string, args.engine as string);
                case 'go_back':
                    return this.goBack(page);
                case 'go_forward':
                    return this.goForward(page);
                case 'refresh':
                    return this.refresh(page);
                case 'screenshot':
                    return this.screenshot(page, args.path as string);
                case 'get_title':
                    return this.getTitle(page);
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async openURL(page: Page, url: string): Promise<AdapterResult> {
        await page.goto(url, { waitUntil: 'domcontentloaded' });
        return this.success({ url, title: await page.title() });
    }

    private async getCurrentURL(page: Page): Promise<AdapterResult> {
        return this.success({ url: page.url() });
    }

    private async search(page: Page, query: string, engine = 'google'): Promise<AdapterResult> {
        const searchUrls: Record<string, string> = {
            google: `https://www.google.com/search?q=${encodeURIComponent(query)}`,
            bing: `https://www.bing.com/search?q=${encodeURIComponent(query)}`,
            duckduckgo: `https://duckduckgo.com/?q=${encodeURIComponent(query)}`,
            baidu: `https://www.baidu.com/s?wd=${encodeURIComponent(query)}`,
        };
        const url = searchUrls[engine] || searchUrls.google;
        await page.goto(url, { waitUntil: 'domcontentloaded' });
        return this.success({ query, engine, url });
    }

    private async goBack(page: Page): Promise<AdapterResult> {
        await page.goBack();
        return this.success({ action: 'go_back', url: page.url() });
    }

    private async goForward(page: Page): Promise<AdapterResult> {
        await page.goForward();
        return this.success({ action: 'go_forward', url: page.url() });
    }

    private async refresh(page: Page): Promise<AdapterResult> {
        await page.reload();
        return this.success({ action: 'refresh', url: page.url() });
    }

    private async screenshot(page: Page, path: string): Promise<AdapterResult> {
        await page.screenshot({ path, fullPage: false });
        return this.success({ path, captured: true });
    }

    private async getTitle(page: Page): Promise<AdapterResult> {
        const title = await page.title();
        return this.success({ title, url: page.url() });
    }

    private async closeBrowser(): Promise<AdapterResult> {
        if (this.browser) {
            await this.browser.close();
            this.browser = null;
            this.page = null;
            console.log('[BrowserAdapter] Browser closed');
        }
        return this.success({ closed: true });
    }

    async shutdown(): Promise<void> {
        await this.closeBrowser();
    }
}

export const browserAdapter = new BrowserAdapter();
