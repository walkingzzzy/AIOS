/**
 * 浏览器控制适配器
 * 使用 Playwright 实现浏览器自动化
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { networkGuard } from '../../core/security/index.js';
import { randomUUID } from 'node:crypto';

// Playwright 类型
type Browser = import('playwright').Browser;
type BrowserContext = import('playwright').BrowserContext;
type Page = import('playwright').Page;
type BrowserContextOptions = import('playwright').BrowserContextOptions;

type BrowserTypeName = 'chromium' | 'firefox' | 'webkit';
type WaitUntilState = 'load' | 'domcontentloaded' | 'networkidle';
type WaitForSelectorState = 'attached' | 'detached' | 'visible' | 'hidden';

type ExtractContentType = 'text' | 'html' | 'attribute';

type ExtractField = {
    name: string;
    selector?: string;
    type?: ExtractContentType;
    attribute?: string;
};

type SearchSiteConfig = {
    name?: string;
    url: string;
    search_input_selector: string;
    search_button_selector?: string;
    result_list_selector: string;
    title_selector?: string;
    price_selector?: string;
    link_selector?: string;
    price_attribute?: string;
    link_attribute?: string;
    timeout_ms?: number;
    limit?: number;
    keep_page?: boolean;
};

export class BrowserAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.browser';
    readonly name = '浏览器控制';
    readonly description = '浏览器自动化控制 (Playwright)';

    private browser: Browser | null = null;
    private context: BrowserContext | null = null;
    private pages: Map<string, Page> = new Map();
    private activePageId: string | null = null;
    private isInitializing = false;
    private headless = true;
    private browserType: BrowserTypeName = 'chromium';
    private contextOptions: BrowserContextOptions = {};

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'launch',
            name: '启动浏览器',
            description: '启动浏览器并初始化上下文',
            permissionLevel: 'medium',
            parameters: [
                { name: 'browser_type', type: 'string', required: false, description: '浏览器类型 chromium/firefox/webkit' },
                { name: 'headless', type: 'boolean', required: false, description: '是否无头模式 (默认 true)' },
                { name: 'viewport', type: 'object', required: false, description: '视窗大小 { width, height }' },
                { name: 'user_agent', type: 'string', required: false, description: 'User-Agent 字符串' },
                { name: 'locale', type: 'string', required: false, description: '语言区域 (如 zh-CN)' },
                { name: 'timezone_id', type: 'string', required: false, description: '时区 ID (如 Asia/Shanghai)' },
                { name: 'accept_downloads', type: 'boolean', required: false, description: '是否允许下载' },
            ],
        },
        {
            id: 'new_page',
            name: '新建标签页',
            description: '新建标签页并可选打开网址',
            permissionLevel: 'medium',
            parameters: [
                { name: 'url', type: 'string', required: false, description: '要打开的网址' },
                { name: 'wait_until', type: 'string', required: false, description: '等待状态 load/domcontentloaded/networkidle' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'list_pages',
            name: '列出标签页',
            description: '列出当前浏览器中的标签页',
            permissionLevel: 'public',
        },
        {
            id: 'set_active_page',
            name: '切换标签页',
            description: '切换当前活动标签页',
            permissionLevel: 'low',
            parameters: [
                { name: 'page_id', type: 'string', required: true, description: '标签页 ID' },
            ],
        },
        {
            id: 'close_page',
            name: '关闭标签页',
            description: '关闭指定标签页',
            permissionLevel: 'medium',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID，默认关闭当前页' },
            ],
        },
        {
            id: 'open_url',
            name: '打开网址',
            description: '在浏览器中打开指定网址',
            permissionLevel: 'medium',
            parameters: [
                { name: 'url', type: 'string', required: true, description: '要打开的网址' },
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'wait_until', type: 'string', required: false, description: '等待状态 load/domcontentloaded/networkidle' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'get_current_url',
            name: '获取当前网址',
            description: '获取当前页面的网址',
            permissionLevel: 'public',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
            ],
        },
        {
            id: 'search',
            name: '搜索',
            description: '使用搜索引擎搜索',
            permissionLevel: 'medium',
            parameters: [
                { name: 'query', type: 'string', required: true, description: '搜索关键词' },
                { name: 'engine', type: 'string', required: false, description: '搜索引擎 (google/bing/duckduckgo/baidu)' },
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'wait_until', type: 'string', required: false, description: '等待状态 load/domcontentloaded/networkidle' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'go_back',
            name: '后退',
            description: '返回上一页',
            permissionLevel: 'low',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
            ],
        },
        {
            id: 'go_forward',
            name: '前进',
            description: '前进到下一页',
            permissionLevel: 'low',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
            ],
        },
        {
            id: 'refresh',
            name: '刷新',
            description: '刷新当前页面',
            permissionLevel: 'low',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
            ],
        },
        {
            id: 'wait_for',
            name: '等待条件',
            description: '等待选择器或加载状态满足',
            permissionLevel: 'low',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'selector', type: 'string', required: false, description: 'CSS 选择器' },
                { name: 'state', type: 'string', required: false, description: '等待状态 attached/detached/visible/hidden' },
                { name: 'load_state', type: 'string', required: false, description: '加载状态 load/domcontentloaded/networkidle' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'click',
            name: '点击元素',
            description: '点击指定元素或坐标',
            permissionLevel: 'medium',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'selector', type: 'string', required: false, description: 'CSS 选择器' },
                { name: 'x', type: 'number', required: false, description: '点击 X 坐标' },
                { name: 'y', type: 'number', required: false, description: '点击 Y 坐标' },
                { name: 'button', type: 'string', required: false, description: '鼠标按钮 (left/right/middle)' },
                { name: 'click_count', type: 'number', required: false, description: '点击次数' },
                { name: 'delay_ms', type: 'number', required: false, description: '点击延迟毫秒' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'fill',
            name: '填充输入',
            description: '填充输入框内容',
            permissionLevel: 'medium',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'selector', type: 'string', required: true, description: 'CSS 选择器' },
                { name: 'text', type: 'string', required: true, description: '输入文本' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'type_text',
            name: '键入文本',
            description: '模拟键盘逐字输入',
            permissionLevel: 'medium',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'selector', type: 'string', required: false, description: 'CSS 选择器（为空则输入到当前焦点）' },
                { name: 'text', type: 'string', required: true, description: '输入文本' },
                { name: 'delay_ms', type: 'number', required: false, description: '每字符延迟毫秒' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'press_key',
            name: '按键',
            description: '按下键盘按键',
            permissionLevel: 'medium',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'key', type: 'string', required: true, description: '按键名称 (如 Enter)' },
                { name: 'selector', type: 'string', required: false, description: 'CSS 选择器（为空则按当前焦点）' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'hover',
            name: '悬停',
            description: '鼠标悬停到指定元素',
            permissionLevel: 'medium',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'selector', type: 'string', required: true, description: 'CSS 选择器' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'select_option',
            name: '选择下拉项',
            description: '选择下拉框选项',
            permissionLevel: 'medium',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'selector', type: 'string', required: true, description: 'CSS 选择器' },
                { name: 'values', type: 'array', required: true, description: '选项值数组' },
                { name: 'timeout_ms', type: 'number', required: false, description: '等待超时毫秒' },
            ],
        },
        {
            id: 'scroll',
            name: '滚动页面',
            description: '滚动页面或容器',
            permissionLevel: 'low',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'delta_x', type: 'number', required: false, description: '水平滚动量' },
                { name: 'delta_y', type: 'number', required: false, description: '垂直滚动量' },
                { name: 'to', type: 'string', required: false, description: '滚动方向 top/bottom' },
                { name: 'selector', type: 'string', required: false, description: '容器选择器' },
            ],
        },
        {
            id: 'screenshot',
            name: '截图',
            description: '截取当前页面截图',
            permissionLevel: 'low',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'path', type: 'string', required: true, description: '保存路径' },
                { name: 'full_page', type: 'boolean', required: false, description: '是否全页面截图' },
                { name: 'selector', type: 'string', required: false, description: '元素选择器' },
                { name: 'type', type: 'string', required: false, description: '图片格式 png/jpeg' },
            ],
        },
        {
            id: 'get_title',
            name: '获取标题',
            description: '获取当前页面标题',
            permissionLevel: 'public',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
            ],
        },
        {
            id: 'set_viewport',
            name: '设置视窗',
            description: '设置当前页面视窗大小',
            permissionLevel: 'low',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'width', type: 'number', required: true, description: '视窗宽度' },
                { name: 'height', type: 'number', required: true, description: '视窗高度' },
            ],
        },
        {
            id: 'get_content',
            name: '获取内容',
            description: '提取页面内容或属性',
            permissionLevel: 'medium',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'selector', type: 'string', required: false, description: 'CSS 选择器' },
                { name: 'content_type', type: 'string', required: false, description: 'text/html/attribute' },
                { name: 'attribute', type: 'string', required: false, description: '属性名' },
                { name: 'multiple', type: 'boolean', required: false, description: '是否提取多个元素' },
                { name: 'trim', type: 'boolean', required: false, description: '是否裁剪空白' },
            ],
        },
        {
            id: 'extract_list',
            name: '提取列表',
            description: '从列表节点提取结构化数据',
            permissionLevel: 'medium',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'list_selector', type: 'string', required: true, description: '列表容器选择器' },
                { name: 'fields', type: 'array', required: true, description: '字段配置数组' },
                { name: 'limit', type: 'number', required: false, description: '最大条数' },
            ],
        },
        {
            id: 'evaluate',
            name: '执行脚本',
            description: '在页面上下文执行脚本',
            permissionLevel: 'medium',
            parameters: [
                { name: 'page_id', type: 'string', required: false, description: '标签页 ID' },
                { name: 'script', type: 'string', required: true, description: '脚本字符串（函数或表达式）' },
                { name: 'args', type: 'object', required: false, description: '传入脚本的参数' },
            ],
        },
        {
            id: 'search_and_compare',
            name: '搜索比价',
            description: '在多个网站搜索并比较价格',
            permissionLevel: 'medium',
            parameters: [
                { name: 'query', type: 'string', required: true, description: '搜索关键词' },
                { name: 'sites', type: 'array', required: true, description: '站点配置数组' },
                { name: 'parallel', type: 'boolean', required: false, description: '是否并行执行' },
                { name: 'limit', type: 'number', required: false, description: '每站点最大条数' },
            ],
        },
        {
            id: 'close',
            name: '关闭浏览器',
            description: '关闭浏览器实例',
            permissionLevel: 'low',
        },
    ];

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

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'launch':
                    return this.launchBrowser(args);
                case 'new_page':
                    return this.newPage(args);
                case 'list_pages':
                    return this.listPages();
                case 'set_active_page':
                    return this.setActivePage(args.page_id as string);
                case 'close_page':
                    return this.closePage(args.page_id as string | undefined);
                case 'open_url':
                    return this.openURL(args);
                case 'get_current_url':
                    return this.getCurrentURL(args.page_id as string | undefined);
                case 'search':
                    return this.search(args);
                case 'go_back':
                    return this.goBack(args.page_id as string | undefined);
                case 'go_forward':
                    return this.goForward(args.page_id as string | undefined);
                case 'refresh':
                    return this.refresh(args.page_id as string | undefined);
                case 'wait_for':
                    return this.waitFor(args);
                case 'click':
                    return this.click(args);
                case 'fill':
                    return this.fill(args);
                case 'type_text':
                    return this.typeText(args);
                case 'press_key':
                    return this.pressKey(args);
                case 'hover':
                    return this.hover(args);
                case 'select_option':
                    return this.selectOption(args);
                case 'scroll':
                    return this.scroll(args);
                case 'screenshot':
                    return this.screenshot(args);
                case 'get_title':
                    return this.getTitle(args.page_id as string | undefined);
                case 'set_viewport':
                    return this.setViewport(args);
                case 'get_content':
                    return this.getContent(args);
                case 'extract_list':
                    return this.extractList(args);
                case 'evaluate':
                    return this.evaluate(args);
                case 'search_and_compare':
                    return this.searchAndCompare(args);
                case 'close':
                    return this.closeBrowser();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private asString(value: unknown): string | null {
        if (typeof value !== 'string') return null;
        const trimmed = value.trim();
        return trimmed ? trimmed : null;
    }

    private asOptionalString(value: unknown): string | undefined {
        return typeof value === 'string' ? value : undefined;
    }

    private asNumber(value: unknown): number | null {
        if (value === undefined || value === null) return null;
        const num = Number(value);
        if (!Number.isFinite(num)) return null;
        return num;
    }

    private asBoolean(value: unknown): boolean | null {
        if (value === undefined || value === null) return null;
        if (typeof value === 'boolean') return value;
        return null;
    }

    private asStringArray(value: unknown): string[] | null {
        if (!Array.isArray(value)) return null;
        const list = value.filter((item) => typeof item === 'string') as string[];
        if (list.length !== value.length) return null;
        return list;
    }

    private asObject(value: unknown): Record<string, unknown> | null {
        if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
        return value as Record<string, unknown>;
    }

    private parseBrowserType(input: unknown): BrowserTypeName | null {
        if (input === undefined || input === null) return null;
        if (typeof input !== 'string') return null;
        const normalized = input.toLowerCase();
        if (normalized === 'chromium' || normalized === 'firefox' || normalized === 'webkit') {
            return normalized as BrowserTypeName;
        }
        return null;
    }

    private parseWaitUntil(input: unknown): WaitUntilState | undefined {
        if (input === undefined || input === null) return undefined;
        if (typeof input !== 'string') return undefined;
        const normalized = input.toLowerCase();
        if (normalized === 'load' || normalized === 'domcontentloaded' || normalized === 'networkidle') {
            return normalized as WaitUntilState;
        }
        return undefined;
    }

    private parseSelectorState(input: unknown): WaitForSelectorState | undefined {
        if (input === undefined || input === null) return undefined;
        if (typeof input !== 'string') return undefined;
        const normalized = input.toLowerCase();
        if (normalized === 'attached' || normalized === 'detached' || normalized === 'visible' || normalized === 'hidden') {
            return normalized as WaitForSelectorState;
        }
        return undefined;
    }

    private parseViewport(input: unknown): { width: number; height: number } | null {
        const obj = this.asObject(input);
        if (!obj) return null;
        const width = this.asNumber(obj.width);
        const height = this.asNumber(obj.height);
        if (width === null || height === null) return null;
        return { width, height };
    }

    private buildContextOptions(args: Record<string, unknown>): BrowserContextOptions {
        const options: BrowserContextOptions = {};
        const viewport = this.parseViewport(args.viewport);
        if (viewport) {
            options.viewport = viewport;
        }
        const userAgent = this.asOptionalString(args.user_agent);
        if (userAgent) {
            options.userAgent = userAgent;
        }
        const locale = this.asOptionalString(args.locale);
        if (locale) {
            options.locale = locale;
        }
        const timezoneId = this.asOptionalString(args.timezone_id);
        if (timezoneId) {
            options.timezoneId = timezoneId;
        }
        const acceptDownloads = this.asBoolean(args.accept_downloads);
        if (acceptDownloads !== null) {
            options.acceptDownloads = acceptDownloads;
        }
        return options;
    }

    private async ensureBrowser(options?: { force?: boolean }): Promise<void> {
        if (this.browser && this.context && !options?.force) {
            return;
        }

        if (this.isInitializing) {
            while (this.isInitializing) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            if (this.browser && this.context) {
                return;
            }
        }

        this.isInitializing = true;
        try {
            if (options?.force) {
                await this.closeBrowserInternal();
            }
            const { chromium, firefox, webkit } = await import('playwright');
            const browserType = this.browserType === 'firefox'
                ? firefox
                : this.browserType === 'webkit'
                    ? webkit
                    : chromium;

            this.browser = await browserType.launch({ headless: this.headless });
            this.context = await this.browser.newContext(this.contextOptions);
            this.pages.clear();
            this.activePageId = null;
            console.log(`[BrowserAdapter] Browser launched (${this.browserType}, headless: ${this.headless})`);
        } catch (error) {
            console.error('[BrowserAdapter] Failed to launch browser:', error);
            throw new Error('浏览器启动失败，请确保已安装 Playwright');
        } finally {
            this.isInitializing = false;
        }
    }

    private async createPage(url?: string, waitUntil?: WaitUntilState, timeoutMs?: number): Promise<{ pageId: string; page: Page }> {
        if (!this.context) {
            throw new Error('浏览器上下文未初始化');
        }
        const page = await this.context.newPage();
        const pageId = randomUUID();
        this.pages.set(pageId, page);
        this.activePageId = pageId;
        page.on('close', () => {
            this.pages.delete(pageId);
            if (this.activePageId === pageId) {
                const next = this.pages.keys().next();
                this.activePageId = next.done ? null : next.value;
            }
        });

        if (url) {
            await this.gotoUrl(page, url, waitUntil, timeoutMs);
        }

        return { pageId, page };
    }

    private async getPage(args: Record<string, unknown>): Promise<{ pageId: string; page: Page } | AdapterResult> {
        await this.ensureBrowser();

        const pageId = this.asString(args.page_id);
        if (pageId) {
            const page = this.pages.get(pageId);
            if (!page) {
                return this.failure('INVALID_PARAM', `page_id 不存在: ${pageId}`);
            }
            this.activePageId = pageId;
            return { pageId, page };
        }

        if (this.activePageId && this.pages.has(this.activePageId)) {
            const page = this.pages.get(this.activePageId)!;
            return { pageId: this.activePageId, page };
        }

        const created = await this.createPage();
        return created;
    }

    private async gotoUrl(page: Page, url: string, waitUntil?: WaitUntilState, timeoutMs?: number): Promise<void> {
        const checkResult = networkGuard.checkUrl(url);
        if (checkResult.blocked) {
            console.warn(`[BrowserAdapter] Blocked URL: ${url} (${checkResult.reason})`);
            throw new Error(`访问被拒绝: ${checkResult.domain} 不在白名单中`);
        }
        if (!checkResult.allowed) {
            console.warn(`[BrowserAdapter] URL not in whitelist: ${url} (${checkResult.reason})`);
        }

        await page.goto(url, {
            waitUntil: waitUntil ?? 'domcontentloaded',
            timeout: timeoutMs,
        });
    }

    private async launchBrowser(args: Record<string, unknown>): Promise<AdapterResult> {
        const browserType = this.parseBrowserType(args.browser_type);
        if (args.browser_type !== undefined && !browserType) {
            return this.failure('INVALID_PARAM', 'browser_type 必须是 chromium/firefox/webkit');
        }
        const headless = this.asBoolean(args.headless);
        if (args.headless !== undefined && headless === null) {
            return this.failure('INVALID_PARAM', 'headless 必须是布尔值');
        }

        if (browserType) {
            this.browserType = browserType;
        }
        if (headless !== null) {
            this.headless = headless;
        }
        this.contextOptions = this.buildContextOptions(args);

        await this.ensureBrowser({ force: true });
        const created = await this.createPage();
        return this.success({
            browser_type: this.browserType,
            headless: this.headless,
            page_id: created.pageId,
        });
    }

    private async newPage(args: Record<string, unknown>): Promise<AdapterResult> {
        await this.ensureBrowser();
        const url = this.asString(args.url) ?? undefined;
        const waitUntil = this.parseWaitUntil(args.wait_until);
        const timeoutMs = this.asNumber(args.timeout_ms) ?? undefined;
        const created = await this.createPage(url, waitUntil, timeoutMs);
        return this.success({ page_id: created.pageId, url: created.page.url() });
    }

    private async listPages(): Promise<AdapterResult> {
        if (!this.browser || !this.context) {
            return this.success({ pages: [], active_page_id: null });
        }
        const pages = Array.from(this.pages.entries()).map(([pageId, page]) => ({
            page_id: pageId,
            url: page.url(),
            active: pageId === this.activePageId,
        }));
        return this.success({ pages, active_page_id: this.activePageId });
    }

    private async setActivePage(pageId: string): Promise<AdapterResult> {
        const id = this.asString(pageId);
        if (!id) {
            return this.failure('INVALID_PARAM', 'page_id 必须是非空字符串');
        }
        const page = this.pages.get(id);
        if (!page) {
            return this.failure('INVALID_PARAM', `page_id 不存在: ${id}`);
        }
        this.activePageId = id;
        return this.success({ page_id: id, url: page.url() });
    }

    private async closePage(pageId?: string): Promise<AdapterResult> {
        const id = this.asString(pageId) ?? this.activePageId;
        if (!id) {
            return this.failure('INVALID_PARAM', '没有可关闭的标签页');
        }
        const page = this.pages.get(id);
        if (!page) {
            return this.failure('INVALID_PARAM', `page_id 不存在: ${id}`);
        }
        await page.close();
        this.pages.delete(id);
        if (this.activePageId === id) {
            const next = this.pages.keys().next();
            this.activePageId = next.done ? null : next.value;
        }
        return this.success({ closed: true, page_id: id });
    }

    private async openURL(args: Record<string, unknown>): Promise<AdapterResult> {
        const url = this.asString(args.url);
        if (!url) {
            return this.failure('INVALID_PARAM', 'url 必须是非空字符串');
        }

        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }

        const waitUntil = this.parseWaitUntil(args.wait_until);
        const timeoutMs = this.asNumber(args.timeout_ms) ?? undefined;
        await this.gotoUrl(pageResult.page, url, waitUntil, timeoutMs);
        return this.success({ url, title: await pageResult.page.title(), page_id: pageResult.pageId });
    }

    private async getCurrentURL(pageId?: string): Promise<AdapterResult> {
        const pageResult = await this.getPage({ page_id: pageId });
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        return this.success({ url: pageResult.page.url(), page_id: pageResult.pageId });
    }

    private async search(args: Record<string, unknown>): Promise<AdapterResult> {
        const query = this.asString(args.query);
        if (!query) {
            return this.failure('INVALID_PARAM', 'query 必须是非空字符串');
        }
        const engine = this.asOptionalString(args.engine) ?? 'google';
        const searchUrls: Record<string, string> = {
            google: `https://www.google.com/search?q=${encodeURIComponent(query)}`,
            bing: `https://www.bing.com/search?q=${encodeURIComponent(query)}`,
            duckduckgo: `https://duckduckgo.com/?q=${encodeURIComponent(query)}`,
            baidu: `https://www.baidu.com/s?wd=${encodeURIComponent(query)}`,
        };
        const url = searchUrls[engine] || searchUrls.google;
        return this.openURL({
            url,
            page_id: args.page_id,
            wait_until: args.wait_until,
            timeout_ms: args.timeout_ms,
        });
    }

    private async goBack(pageId?: string): Promise<AdapterResult> {
        const pageResult = await this.getPage({ page_id: pageId });
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        await pageResult.page.goBack();
        return this.success({ action: 'go_back', url: pageResult.page.url(), page_id: pageResult.pageId });
    }

    private async goForward(pageId?: string): Promise<AdapterResult> {
        const pageResult = await this.getPage({ page_id: pageId });
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        await pageResult.page.goForward();
        return this.success({ action: 'go_forward', url: pageResult.page.url(), page_id: pageResult.pageId });
    }

    private async refresh(pageId?: string): Promise<AdapterResult> {
        const pageResult = await this.getPage({ page_id: pageId });
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        await pageResult.page.reload();
        return this.success({ action: 'refresh', url: pageResult.page.url(), page_id: pageResult.pageId });
    }

    private async waitFor(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const selector = this.asString(args.selector) ?? undefined;
        const state = this.parseSelectorState(args.state);
        const loadState = this.parseWaitUntil(args.load_state);
        const timeoutMs = this.asNumber(args.timeout_ms) ?? undefined;

        if (selector) {
            await pageResult.page.waitForSelector(selector, { state, timeout: timeoutMs });
            return this.success({ waited: 'selector', selector, page_id: pageResult.pageId });
        }

        if (loadState) {
            await pageResult.page.waitForLoadState(loadState, { timeout: timeoutMs });
            return this.success({ waited: 'load_state', load_state: loadState, page_id: pageResult.pageId });
        }

        if (timeoutMs !== undefined) {
            await pageResult.page.waitForTimeout(timeoutMs);
            return this.success({ waited: 'timeout', timeout_ms: timeoutMs, page_id: pageResult.pageId });
        }

        return this.failure('INVALID_PARAM', '必须提供 selector、load_state 或 timeout_ms');
    }

    private async click(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const selector = this.asString(args.selector);
        const x = this.asNumber(args.x);
        const y = this.asNumber(args.y);
        const button = this.asOptionalString(args.button) as 'left' | 'right' | 'middle' | undefined;
        const clickCount = this.asNumber(args.click_count) ?? undefined;
        const delay = this.asNumber(args.delay_ms) ?? undefined;
        const timeoutMs = this.asNumber(args.timeout_ms) ?? undefined;

        if (selector) {
            await pageResult.page.click(selector, { button, clickCount, delay, timeout: timeoutMs });
            return this.success({ clicked: true, selector, page_id: pageResult.pageId });
        }

        if (x !== null && y !== null) {
            await pageResult.page.mouse.click(x, y, { button, clickCount, delay });
            return this.success({ clicked: true, x, y, page_id: pageResult.pageId });
        }

        return this.failure('INVALID_PARAM', '必须提供 selector 或 x/y 坐标');
    }

    private async fill(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const selector = this.asString(args.selector);
        const text = this.asString(args.text);
        const timeoutMs = this.asNumber(args.timeout_ms) ?? undefined;
        if (!selector || !text) {
            return this.failure('INVALID_PARAM', 'selector 和 text 必须是非空字符串');
        }
        await pageResult.page.fill(selector, text, { timeout: timeoutMs });
        return this.success({ filled: true, selector, page_id: pageResult.pageId });
    }

    private async typeText(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const text = this.asString(args.text);
        if (!text) {
            return this.failure('INVALID_PARAM', 'text 必须是非空字符串');
        }
        const selector = this.asString(args.selector) ?? undefined;
        const delay = this.asNumber(args.delay_ms) ?? undefined;
        const timeoutMs = this.asNumber(args.timeout_ms) ?? undefined;

        if (selector) {
            await pageResult.page.type(selector, text, { delay, timeout: timeoutMs });
        } else {
            await pageResult.page.keyboard.type(text, { delay });
        }
        return this.success({ typed: true, selector, page_id: pageResult.pageId });
    }

    private async pressKey(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const key = this.asString(args.key);
        if (!key) {
            return this.failure('INVALID_PARAM', 'key 必须是非空字符串');
        }
        const selector = this.asString(args.selector) ?? undefined;
        const timeoutMs = this.asNumber(args.timeout_ms) ?? undefined;

        if (selector) {
            await pageResult.page.press(selector, key, { timeout: timeoutMs });
        } else {
            await pageResult.page.keyboard.press(key);
        }
        return this.success({ pressed: true, key, page_id: pageResult.pageId });
    }

    private async hover(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const selector = this.asString(args.selector);
        const timeoutMs = this.asNumber(args.timeout_ms) ?? undefined;
        if (!selector) {
            return this.failure('INVALID_PARAM', 'selector 必须是非空字符串');
        }
        await pageResult.page.hover(selector, { timeout: timeoutMs });
        return this.success({ hovered: true, selector, page_id: pageResult.pageId });
    }

    private async selectOption(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const selector = this.asString(args.selector);
        const values = this.asStringArray(args.values);
        const timeoutMs = this.asNumber(args.timeout_ms) ?? undefined;
        if (!selector || !values) {
            return this.failure('INVALID_PARAM', 'selector 必须是非空字符串且 values 必须是字符串数组');
        }
        await pageResult.page.selectOption(selector, values, { timeout: timeoutMs });
        return this.success({ selected: true, selector, page_id: pageResult.pageId });
    }

    private async scroll(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const selector = this.asString(args.selector) ?? undefined;
        const to = this.asString(args.to) ?? undefined;
        const deltaX = this.asNumber(args.delta_x) ?? 0;
        const deltaY = this.asNumber(args.delta_y) ?? 0;

        if (selector) {
            await pageResult.page.evaluate(({ sel, dx, dy, dir }) => {
                const container = document.querySelector(sel) as HTMLElement | null;
                if (!container) return;
                if (dir === 'top') {
                    container.scrollTop = 0;
                } else if (dir === 'bottom') {
                    container.scrollTop = container.scrollHeight;
                } else {
                    container.scrollBy(dx, dy);
                }
            }, { sel: selector, dx: deltaX, dy: deltaY, dir: to });
            return this.success({ scrolled: true, selector, page_id: pageResult.pageId });
        }

        if (to === 'top' || to === 'bottom') {
            await pageResult.page.evaluate((dir) => {
                if (dir === 'top') {
                    window.scrollTo(0, 0);
                } else {
                    window.scrollTo(0, document.body.scrollHeight);
                }
            }, to);
            return this.success({ scrolled: true, to, page_id: pageResult.pageId });
        }

        if (deltaX === 0 && deltaY === 0) {
            return this.failure('INVALID_PARAM', '必须提供 delta_x/delta_y 或 to');
        }

        await pageResult.page.mouse.wheel(deltaX, deltaY);
        return this.success({ scrolled: true, delta_x: deltaX, delta_y: deltaY, page_id: pageResult.pageId });
    }

    private async screenshot(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const path = this.asString(args.path);
        if (!path) {
            return this.failure('INVALID_PARAM', 'path 必须是非空字符串');
        }
        const fullPage = this.asBoolean(args.full_page) ?? false;
        const selector = this.asString(args.selector) ?? undefined;
        const type = this.asOptionalString(args.type) as 'png' | 'jpeg' | undefined;

        if (selector) {
            await pageResult.page.locator(selector).screenshot({ path, type });
        } else {
            await pageResult.page.screenshot({ path, fullPage, type });
        }
        return this.success({ path, captured: true, page_id: pageResult.pageId });
    }

    private async getTitle(pageId?: string): Promise<AdapterResult> {
        const pageResult = await this.getPage({ page_id: pageId });
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const title = await pageResult.page.title();
        return this.success({ title, url: pageResult.page.url(), page_id: pageResult.pageId });
    }

    private async setViewport(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const width = this.asNumber(args.width);
        const height = this.asNumber(args.height);
        if (width === null || height === null) {
            return this.failure('INVALID_PARAM', 'width/height 必须是有效数字');
        }
        await pageResult.page.setViewportSize({ width, height });
        return this.success({ width, height, page_id: pageResult.pageId });
    }

    private normalizeContent(value: string, trim: boolean): string {
        return trim ? value.trim() : value;
    }

    private async getContent(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const selector = this.asString(args.selector) ?? undefined;
        const contentType = (this.asOptionalString(args.content_type) ?? 'text') as ExtractContentType;
        const attribute = this.asOptionalString(args.attribute) ?? undefined;
        const multiple = this.asBoolean(args.multiple) ?? false;
        const trim = this.asBoolean(args.trim) ?? true;

        if (contentType === 'attribute' && !attribute) {
            return this.failure('INVALID_PARAM', 'content_type 为 attribute 时必须提供 attribute');
        }

        if (!selector) {
            if (multiple) {
                return this.failure('INVALID_PARAM', 'multiple=true 时必须提供 selector');
            }
            if (contentType === 'html') {
                const html = await pageResult.page.content();
                return this.success({ content: html, page_id: pageResult.pageId });
            }
            const text = await pageResult.page.evaluate(() => document.body?.innerText ?? '');
            return this.success({ content: this.normalizeContent(text, trim), page_id: pageResult.pageId });
        }

        if (multiple) {
            const results = await pageResult.page.$$eval(
                selector,
                (nodes, payload) => {
                    return nodes.map((node) => {
                        const element = node as HTMLElement;
                        if (payload.type === 'html') {
                            return element.innerHTML || '';
                        }
                        if (payload.type === 'attribute') {
                            return element.getAttribute(payload.attribute || '') || '';
                        }
                        return element.textContent || '';
                    });
                },
                { type: contentType, attribute }
            );
            return this.success({
                content: results.map((item) => this.normalizeContent(item, trim)),
                page_id: pageResult.pageId,
            });
        }

        const content = await pageResult.page.$eval(
            selector,
            (node, payload) => {
                const element = node as HTMLElement;
                if (payload.type === 'html') {
                    return element.innerHTML || '';
                }
                if (payload.type === 'attribute') {
                    return element.getAttribute(payload.attribute || '') || '';
                }
                return element.textContent || '';
            },
            { type: contentType, attribute }
        );

        return this.success({ content: this.normalizeContent(content, trim), page_id: pageResult.pageId });
    }

    private parseExtractFields(input: unknown): ExtractField[] | null {
        if (!Array.isArray(input)) return null;
        const fields: ExtractField[] = [];
        for (const item of input) {
            if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
            const obj = item as Record<string, unknown>;
            const name = this.asString(obj.name);
            if (!name) return null;
            const selector = this.asOptionalString(obj.selector);
            const type = this.asOptionalString(obj.type) as ExtractContentType | undefined;
            const attribute = this.asOptionalString(obj.attribute);
            fields.push({ name, selector, type, attribute });
        }
        return fields;
    }

    private async extractList(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const listSelector = this.asString(args.list_selector);
        if (!listSelector) {
            return this.failure('INVALID_PARAM', 'list_selector 必须是非空字符串');
        }
        const fields = this.parseExtractFields(args.fields);
        if (!fields) {
            return this.failure('INVALID_PARAM', 'fields 必须是字段配置数组');
        }
        const limit = this.asNumber(args.limit) ?? undefined;

        const results = await pageResult.page.$$eval(
            listSelector,
            (nodes, payload) => {
                const items: Record<string, string>[] = [];
                const max = payload.limit && payload.limit > 0 ? payload.limit : nodes.length;
                for (let i = 0; i < nodes.length && items.length < max; i += 1) {
                    const base = nodes[i] as HTMLElement;
                    const record: Record<string, string> = {};
                    for (const field of payload.fields) {
                        const target = field.selector
                            ? base.querySelector(field.selector)
                            : base;
                        if (!target) {
                            record[field.name] = '';
                            continue;
                        }
                        const element = target as HTMLElement;
                        if (field.type === 'html') {
                            record[field.name] = element.innerHTML || '';
                        } else if (field.type === 'attribute') {
                            record[field.name] = element.getAttribute(field.attribute || '') || '';
                        } else {
                            record[field.name] = element.textContent || '';
                        }
                    }
                    items.push(record);
                }
                return items;
            },
            {
                fields,
                limit,
            }
        );

        return this.success({ items: results, page_id: pageResult.pageId });
    }

    private async evaluate(args: Record<string, unknown>): Promise<AdapterResult> {
        const pageResult = await this.getPage(args);
        if ('success' in pageResult && pageResult.success === false) {
            return pageResult;
        }
        const script = this.asString(args.script);
        if (!script) {
            return this.failure('INVALID_PARAM', 'script 必须是非空字符串');
        }
        const result = await pageResult.page.evaluate(script, args.args ?? null);
        return this.success({ result, page_id: pageResult.pageId });
    }

    private parseSearchSites(input: unknown): SearchSiteConfig[] | null {
        if (!Array.isArray(input)) return null;
        const sites: SearchSiteConfig[] = [];
        for (const item of input) {
            if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
            const obj = item as Record<string, unknown>;
            const url = this.asString(obj.url);
            const searchInput = this.asString(obj.search_input_selector);
            const resultList = this.asString(obj.result_list_selector);
            if (!url || !searchInput || !resultList) {
                return null;
            }
            const site: SearchSiteConfig = {
                name: this.asOptionalString(obj.name),
                url,
                search_input_selector: searchInput,
                search_button_selector: this.asOptionalString(obj.search_button_selector),
                result_list_selector: resultList,
                title_selector: this.asOptionalString(obj.title_selector),
                price_selector: this.asOptionalString(obj.price_selector),
                link_selector: this.asOptionalString(obj.link_selector),
                price_attribute: this.asOptionalString(obj.price_attribute),
                link_attribute: this.asOptionalString(obj.link_attribute),
                timeout_ms: this.asNumber(obj.timeout_ms) ?? undefined,
                limit: this.asNumber(obj.limit) ?? undefined,
                keep_page: this.asBoolean(obj.keep_page) ?? false,
            };
            sites.push(site);
        }
        return sites;
    }

    private parsePrice(text: string): number | null {
        const normalized = text.replace(/[,\s]/g, '').replace(/[^\d.]/g, '');
        if (!normalized) return null;
        const value = Number.parseFloat(normalized);
        return Number.isFinite(value) ? value : null;
    }

    private async searchSite(query: string, site: SearchSiteConfig, limit?: number): Promise<{
        site: string;
        items: Array<{ title: string; price_text: string; price_value: number | null; link: string }>;
        page_id: string;
    }> {
        await this.ensureBrowser();
        const created = await this.createPage(site.url, 'domcontentloaded', site.timeout_ms);
        const page = created.page;
        const pageId = created.pageId;

        await page.waitForSelector(site.search_input_selector, { timeout: site.timeout_ms });
        await page.fill(site.search_input_selector, query, { timeout: site.timeout_ms });

        if (site.search_button_selector) {
            await page.click(site.search_button_selector, { timeout: site.timeout_ms });
        } else {
            await page.keyboard.press('Enter');
        }

        await page.waitForSelector(site.result_list_selector, { timeout: site.timeout_ms });

        const payload = {
            listSelector: site.result_list_selector,
            titleSelector: site.title_selector,
            priceSelector: site.price_selector,
            linkSelector: site.link_selector,
            priceAttribute: site.price_attribute,
            linkAttribute: site.link_attribute,
            limit: limit ?? site.limit ?? 10,
        };

        const items = await page.$$eval(
            payload.listSelector,
            (nodes, cfg) => {
                const results: Array<{ title: string; price_text: string; link: string }> = [];
                const max = cfg.limit && cfg.limit > 0 ? cfg.limit : nodes.length;
                for (let i = 0; i < nodes.length && results.length < max; i += 1) {
                    const node = nodes[i] as HTMLElement;
                    const titleEl = cfg.titleSelector ? node.querySelector(cfg.titleSelector) : node;
                    const priceEl = cfg.priceSelector ? node.querySelector(cfg.priceSelector) : node;
                    const linkEl = cfg.linkSelector ? node.querySelector(cfg.linkSelector) : node;
                    const title = (titleEl?.textContent || '').trim();
                    const priceText = cfg.priceAttribute
                        ? priceEl?.getAttribute(cfg.priceAttribute) || ''
                        : (priceEl?.textContent || '').trim();
                    const link = cfg.linkAttribute
                        ? linkEl?.getAttribute(cfg.linkAttribute) || ''
                        : (linkEl as HTMLAnchorElement | null)?.href || '';
                    results.push({ title, price_text: priceText, link });
                }
                return results;
            },
            payload
        );

        if (!site.keep_page) {
            await page.close();
        }

        return {
            site: site.name ?? site.url,
            page_id: pageId,
            items: items.map((item) => ({
                title: item.title,
                price_text: item.price_text,
                price_value: this.parsePrice(item.price_text),
                link: item.link,
            })),
        };
    }

    private async searchAndCompare(args: Record<string, unknown>): Promise<AdapterResult> {
        const query = this.asString(args.query);
        if (!query) {
            return this.failure('INVALID_PARAM', 'query 必须是非空字符串');
        }
        const sites = this.parseSearchSites(args.sites);
        if (!sites) {
            return this.failure('INVALID_PARAM', 'sites 必须是站点配置数组');
        }
        const parallel = this.asBoolean(args.parallel) ?? false;
        const limit = this.asNumber(args.limit) ?? undefined;

        const results: Array<{ site: string; items: Array<{ title: string; price_text: string; price_value: number | null; link: string }>; page_id: string }> = [];
        const errors: Array<{ site: string; message: string }> = [];

        const tasks = sites.map((site) => this.searchSite(query, site, limit).then(
            (data) => results.push(data),
            (error) => errors.push({ site: site.name ?? site.url, message: String(error) })
        ));

        if (parallel) {
            await Promise.all(tasks);
        } else {
            for (const task of tasks) {
                await task;
            }
        }

        let cheapest: { site: string; title: string; price_value: number; link: string } | null = null;
        for (const result of results) {
            for (const item of result.items) {
                if (item.price_value === null) continue;
                if (!cheapest || item.price_value < cheapest.price_value) {
                    cheapest = {
                        site: result.site,
                        title: item.title,
                        price_value: item.price_value,
                        link: item.link,
                    };
                }
            }
        }

        return this.success({ query, results, cheapest, errors });
    }

    private async closeBrowserInternal(): Promise<void> {
        if (this.context) {
            await this.context.close();
            this.context = null;
        }
        if (this.browser) {
            await this.browser.close();
            this.browser = null;
        }
        this.pages.clear();
        this.activePageId = null;
    }

    private async closeBrowser(): Promise<AdapterResult> {
        await this.closeBrowserInternal();
        console.log('[BrowserAdapter] Browser closed');
        return this.success({ closed: true });
    }

    async shutdown(): Promise<void> {
        await this.closeBrowserInternal();
    }
}

export const browserAdapter = new BrowserAdapter();
