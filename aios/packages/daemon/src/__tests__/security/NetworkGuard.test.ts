/**
 * NetworkGuard 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NetworkGuard } from '../../core/security/NetworkGuard.js';

vi.mock('psl', () => ({
    default: {
        get: (host: string) => host.split('.').slice(-2).join('.'),
    },
}));

describe('NetworkGuard', () => {
    let guard: NetworkGuard;

    beforeEach(() => {
        guard = new NetworkGuard();
    });

    describe('checkUrl', () => {
        it('should allow default whitelisted domains', () => {
            const result = guard.checkUrl('https://www.google.com/search?q=test');
            expect(result.allowed).toBe(true);
            expect(result.domain).toBe('google.com');
        });

        it('should allow github.com', () => {
            const result = guard.checkUrl('https://github.com/user/repo');
            expect(result.allowed).toBe(true);
            expect(result.domain).toBe('github.com');
        });

        it('should allow subdomains of whitelisted domains', () => {
            const result = guard.checkUrl('https://docs.github.com/en/pages');
            expect(result.allowed).toBe(true);
        });

        it('should block non-whitelisted domains', () => {
            const result = guard.checkUrl('https://malicious-site.xyz/phishing');
            expect(result.allowed).toBe(false);
            expect(result.reason).toContain('not in whitelist');
        });

        it('should handle invalid URLs', () => {
            const result = guard.checkUrl('not-a-valid-url');
            expect(result.allowed).toBe(false);
            expect(result.reason).toContain('Invalid URL');
        });

        it('should allow localhost', () => {
            const result = guard.checkUrl('http://localhost:3000/api');
            expect(result.allowed).toBe(true);
        });
    });

    describe('addAllowedDomain', () => {
        it('should add new domain to whitelist', () => {
            guard.addAllowedDomain('example.com');
            const result = guard.checkUrl('https://example.com/page');
            expect(result.allowed).toBe(true);
        });
    });

    describe('removeAllowedDomain', () => {
        it('should remove domain from whitelist', () => {
            guard.addAllowedDomain('temp-domain.com');
            expect(guard.checkUrl('https://temp-domain.com').allowed).toBe(true);

            guard.removeAllowedDomain('temp-domain.com');
            expect(guard.checkUrl('https://temp-domain.com').allowed).toBe(false);
        });
    });

    describe('approveTemporarily', () => {
        it('should temporarily allow blocked domain', () => {
            const url = 'https://blocked-site.xyz/page';
            expect(guard.checkUrl(url).allowed).toBe(false);

            guard.approveTemporarily('blocked-site.xyz');
            expect(guard.checkUrl(url).allowed).toBe(true);
            expect(guard.checkUrl(url).reason).toBe('User approved');
        });

        it('should clear temporary approvals', () => {
            guard.approveTemporarily('temp-approved.xyz');
            expect(guard.checkUrl('https://temp-approved.xyz').allowed).toBe(true);

            guard.clearUserApprovals();
            expect(guard.checkUrl('https://temp-approved.xyz').allowed).toBe(false);
        });
    });

    describe('enable/disable', () => {
        it('should bypass checks when disabled', () => {
            const url = 'https://any-site.xyz';
            expect(guard.checkUrl(url).allowed).toBe(false);

            guard.setEnabled(false);
            expect(guard.checkUrl(url).allowed).toBe(true);
            expect(guard.checkUrl(url).reason).toBe('NetworkGuard disabled');
        });
    });

    describe('getAllowedDomains', () => {
        it('should return list of allowed domains', () => {
            const domains = guard.getAllowedDomains();
            expect(domains).toContain('google.com');
            expect(domains).toContain('github.com');
            expect(Array.isArray(domains)).toBe(true);
        });
    });

    describe('configuration', () => {
        it('should accept custom allowed domains', () => {
            const customGuard = new NetworkGuard({
                allowedDomains: ['custom-domain.io'],
            });
            expect(customGuard.checkUrl('https://custom-domain.io').allowed).toBe(true);
        });

        it('should start disabled when configured', () => {
            const disabledGuard = new NetworkGuard({ enabled: false });
            expect(disabledGuard.isEnabled()).toBe(false);
            expect(disabledGuard.checkUrl('https://any-site.xyz').allowed).toBe(true);
        });
    });
});
