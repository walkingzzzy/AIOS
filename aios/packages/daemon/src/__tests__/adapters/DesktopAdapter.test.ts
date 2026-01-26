/**
 * DesktopAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const runPlatformCommandMock = vi.hoisted(() => vi.fn(async () => ({
    stdout: 'Dark',
    stderr: '',
    exitCode: 0,
})));

vi.mock('@aios/shared', async () => {
    const actual = await vi.importActual<typeof import('@aios/shared')>('@aios/shared');
    return {
        ...actual,
        runPlatformCommand: runPlatformCommandMock,
    };
});

vi.mock('wallpaper', () => ({
    default: {
        get: vi.fn(async () => '/tmp/wallpaper.png'),
        set: vi.fn(async () => undefined),
    },
}));

vi.mock('child_process', async (importOriginal) => {
    const actual = await importOriginal<typeof import('child_process')>();
    return {
        ...actual,
        execFile: (_cmd: string, _args: string[], cb?: (err: Error | null, stdout?: string, stderr?: string) => void) => {
            cb?.(null, '', '');
        },
    };
});

import { DesktopAdapter } from '../../adapters/system/DesktopAdapter';

describe('DesktopAdapter', () => {
    let adapter: DesktopAdapter;

    beforeEach(async () => {
        adapter = new DesktopAdapter();
        await adapter.initialize();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.desktop');
            expect(adapter.name).toBe('桌面设置');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('get_wallpaper');
            expect(capabilityIds).toContain('set_wallpaper');
            expect(capabilityIds).toContain('get_appearance');
            expect(capabilityIds).toContain('set_appearance');
            expect(capabilityIds).toContain('click');
            expect(capabilityIds).toContain('type_text');
            expect(capabilityIds).toContain('scroll');
        });
    });

    describe('桌面操作', () => {
        it('应该能获取壁纸', async () => {
            const result = await adapter.invoke('get_wallpaper', {});

            expect(result.success).toBe(true);
            expect((result.data as { path?: string }).path).toBe('/tmp/wallpaper.png');
        });

        it('应该能设置壁纸', async () => {
            const result = await adapter.invoke('set_wallpaper', { path: '/tmp/new.png' });

            expect(result.success).toBe(true);
            expect((result.data as { path?: string }).path).toBe('/tmp/new.png');
        });

        it('应该能获取外观模式', async () => {
            const result = await adapter.invoke('get_appearance', {});

            expect(result.success).toBe(true);
            expect((result.data as { mode?: string }).mode).toBe('dark');
        });

        it('应该能设置外观模式', async () => {
            const result = await adapter.invoke('set_appearance', { mode: 'light' });

            expect(result.success).toBe(true);
            expect((result.data as { mode?: string }).mode).toBe('light');
        });

        it('应该能点击与输入文本', async () => {
            const clickResult = await adapter.invoke('click', { x: 100, y: 200 });
            expect(clickResult.success).toBe(true);

            const typeResult = await adapter.invoke('type_text', { text: 'Hello' });
            expect(typeResult.success).toBe(true);
        });

        it('应该能滚动', async () => {
            const result = await adapter.invoke('scroll', { direction: 'down', amount: 120 });

            expect(result.success).toBe(true);
        });
    });
});
