/**
 * NetworkGuard - 网络安全控制
 * 实现域名白名单和请求拦截
 */

import psl from 'psl';
import { isIP } from 'net';

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
    blocked?: boolean;
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
        'mozilla.org',
        // 常用媒体
        'wikipedia.org',
        'youtube.com',
        // AI 服务
        'openai.com',
        'anthropic.com',
    ];

    constructor(config: NetworkGuardConfig = {}) {
        this.enabled = config.enabled ?? true;
        this.blockUnauthorized = config.blockUnauthorized ?? true;

        this.allowedDomains = new Set([
            ...NetworkGuard.DEFAULT_ALLOWED_DOMAINS,
            ...(config.allowedDomains ?? []).map((domain) => domain.toLowerCase()),
        ]);
    }

    /**
     * 检查 URL 是否允许访问
     */
    checkUrl(url: string): DomainCheckResult {
        if (!this.enabled) {
            return { allowed: true, domain: '', reason: 'NetworkGuard disabled', blocked: false };
        }

        try {
            const parsedUrl = new URL(url);
            const domain = this.extractRootDomain(parsedUrl.hostname);
            const allowed = this.isAllowed(domain) || this.userApprovedDomains.has(domain);

            // 检查白名单
            if (allowed) {
                return {
                    allowed: true,
                    domain,
                    reason: this.userApprovedDomains.has(domain) ? 'User approved' : 'In whitelist',
                    blocked: false,
                };
            }

            const blocked = this.blockUnauthorized;
            return {
                allowed: false,
                domain,
                reason: blocked
                    ? `Domain not in whitelist: ${domain}`
                    : `Domain not in whitelist (blocking disabled): ${domain}`,
                blocked,
            };
        } catch (error) {
            return {
                allowed: false,
                domain: url,
                reason: `Invalid URL: ${error instanceof Error ? error.message : 'unknown'}`,
                blocked: this.blockUnauthorized,
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
        const host = hostname.split(':')[0].toLowerCase();

        // 处理 IP 地址
        if (isIP(host)) {
            return host;
        }

        // 处理 localhost
        if (host === 'localhost' || host === '127.0.0.1') {
            return 'localhost';
        }

        const domain = psl.get(host);
        if (domain) {
            return domain;
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
        const normalized = this.normalizeDomain(domain);
        if (!normalized) {
            return;
        }
        this.userApprovedDomains.add(normalized);
        console.log(`[NetworkGuard] Temporarily approved domain: ${normalized}`);
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

    private normalizeDomain(input: string): string {
        const trimmed = input.trim().toLowerCase();
        if (!trimmed) {
            return '';
        }
        try {
            if (trimmed.includes('://')) {
                const parsed = new URL(trimmed);
                return this.extractRootDomain(parsed.hostname);
            }
        } catch {
            // fallback to raw input
        }
        return this.extractRootDomain(trimmed);
    }
}

// 单例实例
export const networkGuard = new NetworkGuard();
