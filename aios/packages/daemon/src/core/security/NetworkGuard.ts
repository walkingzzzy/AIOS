/**
 * NetworkGuard - 网络安全控制
 * 实现域名白名单和请求拦截
 */

export interface NetworkGuardConfig {
    /** 允许访问的域名列表 */
    allowedDomains?: string[];
    /** 是否启用网络保护 */
    enabled?: boolean;
    /** 是否阻止未授权请求 */
    blockUnauthorized?: boolean;
}

export interface DomainCheckResult {
    allowed: boolean;
    domain: string;
    reason?: string;
}

/**
 * 网络安全守卫
 */
export class NetworkGuard {
    private allowedDomains: Set<string>;
    private enabled: boolean;
    private blockUnauthorized: boolean;
    private userApprovedDomains: Set<string> = new Set();

    // 默认安全域名白名单
    private static readonly DEFAULT_ALLOWED_DOMAINS = [
        // 本地开发
        'localhost',
        '127.0.0.1',
        // 常用搜索引擎
        'google.com',
        'bing.com',
        'duckduckgo.com',
        'baidu.com',
        // 常用开发资源
        'github.com',
        'stackoverflow.com',
        'npmjs.com',
        'developer.mozilla.org',
        // 常用媒体
        'wikipedia.org',
        'youtube.com',
        // AI 服务
        'openai.com',
        'anthropic.com',
    ];

    constructor(config: NetworkGuardConfig = {}) {
        this.enabled = config.enabled ?? true;
        this.blockUnauthorized = config.blockUnauthorized ?? false;

        this.allowedDomains = new Set([
            ...NetworkGuard.DEFAULT_ALLOWED_DOMAINS,
            ...(config.allowedDomains ?? []),
        ]);
    }

    /**
     * 检查 URL 是否允许访问
     */
    checkUrl(url: string): DomainCheckResult {
        if (!this.enabled) {
            return { allowed: true, domain: '', reason: 'NetworkGuard disabled' };
        }

        try {
            const parsedUrl = new URL(url);
            const domain = this.extractRootDomain(parsedUrl.hostname);

            // 检查白名单
            if (this.isAllowed(domain)) {
                return { allowed: true, domain, reason: 'In whitelist' };
            }

            // 检查用户已授权
            if (this.userApprovedDomains.has(domain)) {
                return { allowed: true, domain, reason: 'User approved' };
            }

            return {
                allowed: false,
                domain,
                reason: `Domain not in whitelist: ${domain}`,
            };
        } catch (error) {
            return {
                allowed: false,
                domain: url,
                reason: `Invalid URL: ${error instanceof Error ? error.message : 'unknown'}`,
            };
        }
    }

    /**
     * 检查域名是否在白名单中
     */
    private isAllowed(domain: string): boolean {
        // 精确匹配
        if (this.allowedDomains.has(domain)) return true;

        // 检查父域名
        const parts = domain.split('.');
        for (let i = 1; i < parts.length; i++) {
            const parentDomain = parts.slice(i).join('.');
            if (this.allowedDomains.has(parentDomain)) return true;
        }

        return false;
    }

    /**
     * 提取根域名
     */
    private extractRootDomain(hostname: string): string {
        // 移除端口号
        const host = hostname.split(':')[0];

        // 处理 IP 地址
        if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) {
            return host;
        }

        // 处理 localhost
        if (host === 'localhost' || host === '127.0.0.1') {
            return 'localhost';
        }

        // 提取根域名（简化处理）
        const parts = host.split('.');
        if (parts.length >= 2) {
            return parts.slice(-2).join('.');
        }

        return host;
    }

    /**
     * 添加允许的域名
     */
    addAllowedDomain(domain: string): void {
        this.allowedDomains.add(domain.toLowerCase());
    }

    /**
     * 移除允许的域名
     */
    removeAllowedDomain(domain: string): boolean {
        return this.allowedDomains.delete(domain.toLowerCase());
    }

    /**
     * 用户授权域名（临时）
     */
    approveTemporarily(domain: string): void {
        this.userApprovedDomains.add(domain.toLowerCase());
        console.log(`[NetworkGuard] Temporarily approved domain: ${domain}`);
    }

    /**
     * 获取所有白名单域名
     */
    getAllowedDomains(): string[] {
        return Array.from(this.allowedDomains);
    }

    /**
     * 获取用户已授权域名
     */
    getUserApprovedDomains(): string[] {
        return Array.from(this.userApprovedDomains);
    }

    /**
     * 启用/禁用
     */
    setEnabled(enabled: boolean): void {
        this.enabled = enabled;
    }

    /**
     * 是否启用
     */
    isEnabled(): boolean {
        return this.enabled;
    }

    /**
     * 清除用户临时授权
     */
    clearUserApprovals(): void {
        this.userApprovedDomains.clear();
    }
}

// 单例实例
export const networkGuard = new NetworkGuard();
