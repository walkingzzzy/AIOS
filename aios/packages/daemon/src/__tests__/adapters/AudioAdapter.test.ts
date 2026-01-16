/**
 * AudioAdapter 单元测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AudioAdapter } from '../../adapters/system/AudioAdapter.js';

// Mock loudness 模块
vi.mock('loudness', () => ({
    default: {
        getVolume: vi.fn().mockResolvedValue(50),
        setVolume: vi.fn().mockResolvedValue(undefined),
        getMuted: vi.fn().mockResolvedValue(false),
        setMuted: vi.fn().mockResolvedValue(undefined),
    },
}));

describe('AudioAdapter', () => {
    let adapter: AudioAdapter;

    beforeEach(async () => {
        adapter = new AudioAdapter();
        await adapter.initialize();
    });

    describe('基本属性', () => {
        it('应该有正确的 id', () => {
            expect(adapter.id).toBe('com.aios.adapter.audio');
        });

        it('应该有正确的名称', () => {
            expect(adapter.name).toBe('音频控制');
        });

        it('应该有 5 个能力', () => {
            expect(adapter.capabilities).toHaveLength(5);
        });
    });

    describe('get_volume', () => {
        it('应该返回当前音量', async () => {
            const result = await adapter.invoke('get_volume', {});
            expect(result.success).toBe(true);
            expect(result.data?.volume).toBe(50);
        });
    });

    describe('set_volume', () => {
        it('应该设置音量', async () => {
            const result = await adapter.invoke('set_volume', { volume: 75 });
            expect(result.success).toBe(true);
            expect(result.data?.volume).toBe(75);
        });

        it('应该限制音量在 0-100 范围内', async () => {
            const result = await adapter.invoke('set_volume', { volume: 150 });
            expect(result.success).toBe(true);
            expect(result.data?.volume).toBe(100);
        });

        it('应该限制负数音量为 0', async () => {
            const result = await adapter.invoke('set_volume', { volume: -10 });
            expect(result.success).toBe(true);
            expect(result.data?.volume).toBe(0);
        });
    });

    describe('get_muted', () => {
        it('应该返回静音状态', async () => {
            const result = await adapter.invoke('get_muted', {});
            expect(result.success).toBe(true);
            expect(result.data?.muted).toBe(false);
        });
    });

    describe('set_muted', () => {
        it('应该设置静音状态', async () => {
            const result = await adapter.invoke('set_muted', { muted: true });
            expect(result.success).toBe(true);
            expect(result.data?.muted).toBe(true);
        });
    });

    describe('toggle_mute', () => {
        it('应该切换静音状态', async () => {
            const result = await adapter.invoke('toggle_mute', {});
            expect(result.success).toBe(true);
            expect(result.data?.muted).toBe(true); // 从 false 切换到 true
        });
    });

    describe('错误处理', () => {
        it('应该处理未知能力', async () => {
            const result = await adapter.invoke('unknown_capability', {});
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('CAPABILITY_NOT_FOUND');
        });
    });
});
