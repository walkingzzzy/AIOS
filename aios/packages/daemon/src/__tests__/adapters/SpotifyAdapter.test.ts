/**
 * SpotifyAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { SpotifyAdapter } from '../../adapters/media/SpotifyAdapter';
import type { OAuthManager } from '../../auth';

describe('SpotifyAdapter', () => {
    let adapter: SpotifyAdapter;
    let oauth: OAuthManager;

    beforeEach(() => {
        adapter = new SpotifyAdapter();
        oauth = {
            isAuthenticated: vi.fn(() => true),
            getAccessToken: vi.fn(async () => 'test-token'),
        } as unknown as OAuthManager;
        adapter.setOAuthManager(oauth);

        const fetchMock = vi.fn(async (url: RequestInfo) => {
            const target = typeof url === 'string' ? url : url.toString();

            if (target.includes('/me/player/play')) {
                return { ok: true, status: 204, json: async () => ({}) } as Response;
            }

            if (target.includes('/me/player/pause')) {
                return { ok: true, status: 204, json: async () => ({}) } as Response;
            }

            if (target.includes('/me/player/next')) {
                return { ok: true, status: 204, json: async () => ({}) } as Response;
            }

            if (target.includes('/me/player/previous')) {
                return { ok: true, status: 204, json: async () => ({}) } as Response;
            }

            if (target.includes('/search')) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ tracks: { items: [] } }),
                } as Response;
            }

            if (target.includes('/me/player/currently-playing')) {
                return { ok: true, status: 204, json: async () => ({}) } as Response;
            }

            return { ok: false, status: 500, json: async () => ({}) } as Response;
        });

        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.spotify');
            expect(adapter.name).toBe('Spotify');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('play');
            expect(capabilityIds).toContain('pause');
            expect(capabilityIds).toContain('next');
            expect(capabilityIds).toContain('previous');
            expect(capabilityIds).toContain('search');
            expect(capabilityIds).toContain('get_current');
        });
    });

    describe('播放控制', () => {
        it('应该能播放音乐', async () => {
            const result = await adapter.invoke('play', {});

            expect(result.success).toBe(true);
        });

        it('应该能暂停音乐', async () => {
            const result = await adapter.invoke('pause', {});

            expect(result.success).toBe(true);
        });

        it('应该能切换到下一首', async () => {
            const result = await adapter.invoke('next', {});

            expect(result.success).toBe(true);
        });

        it('应该能切换到上一首', async () => {
            const result = await adapter.invoke('previous', {});

            expect(result.success).toBe(true);
        });
    });

    describe('搜索与状态', () => {
        it('应该能搜索歌曲', async () => {
            const result = await adapter.invoke('search', {
                query: 'test song',
                type: 'track',
            });

            expect(result.success).toBe(true);
            expect(result.data).toBeDefined();
        });

        it('应该能获取当前播放状态', async () => {
            const result = await adapter.invoke('get_current', {});

            expect(result.success).toBe(true);
            expect((result.data as { playing?: boolean }).playing).toBe(false);
        });
    });

    describe('权限检查', () => {
        it('未配置 OAuth 时应该失败', async () => {
            const noAuthAdapter = new SpotifyAdapter();
            const result = await noAuthAdapter.invoke('play', {});

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('NO_OAUTH');
        });
    });
});
