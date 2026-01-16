/**
 * SpotifyAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SpotifyAdapter } from '../../adapters/media/SpotifyAdapter';

describe('SpotifyAdapter', () => {
    let adapter: SpotifyAdapter;

    beforeEach(() => {
        adapter = new SpotifyAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('spotify');
            expect(adapter.name).toBe('Spotify');
            expect(adapter.permissionLevel).toBe('low');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('spotify_play');
            expect(toolNames).toContain('spotify_pause');
            expect(toolNames).toContain('spotify_next');
            expect(toolNames).toContain('spotify_previous');
        });
    });

    describe('播放控制', () => {
        it('应该能播放音乐', async () => {
            const result = await adapter.execute('spotify_play', {});

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能暂停音乐', async () => {
            const result = await adapter.execute('spotify_pause', {});

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能切换到下一首', async () => {
            const result = await adapter.execute('spotify_next', {});

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能切换到上一首', async () => {
            const result = await adapter.execute('spotify_previous', {});

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });
    });

    describe('音量控制', () => {
        it('应该能设置音量', async () => {
            const result = await adapter.execute('spotify_set_volume', {
                volume: 50
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该拒绝无效的音量值', async () => {
            await expect(
                adapter.execute('spotify_set_volume', { volume: 150 })
            ).rejects.toThrow();

            await expect(
                adapter.execute('spotify_set_volume', { volume: -10 })
            ).rejects.toThrow();
        });
    });

    describe('搜索和播放', () => {
        it('应该能搜索歌曲', async () => {
            const result = await adapter.execute('spotify_search', {
                query: 'test song',
                type: 'track'
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.results)).toBe(true);
        });

        it('应该能播放指定歌曲', async () => {
            const result = await adapter.execute('spotify_play_track', {
                uri: 'spotify:track:123456'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });
    });

    describe('播放状态', () => {
        it('应该能获取当前播放状态', async () => {
            const result = await adapter.execute('spotify_get_playback_state', {});

            expect(result).toBeDefined();
            expect(result.isPlaying).toBeDefined();
        });

        it('应该能获取当前播放的歌曲', async () => {
            const result = await adapter.execute('spotify_get_current_track', {});

            expect(result).toBeDefined();
        });
    });
});
