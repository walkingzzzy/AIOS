/**
 * ScreenshotAdapter 单元测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ScreenshotAdapter } from '../../adapters/screenshot/ScreenshotAdapter.js';

// Mock fs
vi.mock('fs', () => ({
    existsSync: vi.fn().mockReturnValue(true),
    mkdirSync: vi.fn(),
    readFileSync: vi.fn(),
    unlinkSync: vi.fn(),
}));

// Mock child_process
vi.mock('child_process', async (importOriginal) => {
    const actual = await importOriginal<typeof import('child_process')>();
    return {
        ...actual,
        execFile: vi.fn((_cmd: string, _args: string[], cb?: (err: Error | null, stdout?: string, stderr?: string) => void) => {
            cb?.(null, '', '');
        }),
        exec: vi.fn((_cmd: string, cb?: (err: Error | null, stdout?: string, stderr?: string) => void) => {
            cb?.(null, '', '');
        }),
    };
});

vi.mock('util', () => ({
    promisify: vi.fn((fn) => {
        return async (...args: unknown[]) => {
            return new Promise((resolve, reject) => {
                fn(...args, (err: Error | null, stdout: string, stderr: string) => {
                    if (err) reject(err);
                    else resolve({ stdout, stderr });
                });
            });
        };
    }),
}));

describe('ScreenshotAdapter', () => {
    let adapter: ScreenshotAdapter;

    beforeEach(async () => {
        adapter = new ScreenshotAdapter();
        await adapter.initialize();
    });

    describe('基本属性', () => {
        it('应该有正确的 id', () => {
            expect(adapter.id).toBe('com.aios.adapter.screenshot');
        });

        it('应该有正确的名称', () => {
            expect(adapter.name).toBe('截图');
        });

        it('应该有 4 个能力', () => {
            expect(adapter.capabilities).toHaveLength(4);
        });

        it('应该包含 capture_screen 能力', () => {
            const capability = adapter.capabilities.find(c => c.id === 'capture_screen');
            expect(capability).toBeDefined();
            expect(capability?.permissionLevel).toBe('low');
        });

        it('应该包含 capture_window 能力', () => {
            const capability = adapter.capabilities.find(c => c.id === 'capture_window');
            expect(capability).toBeDefined();
        });

        it('应该包含 capture_region 能力', () => {
            const capability = adapter.capabilities.find(c => c.id === 'capture_region');
            expect(capability).toBeDefined();
        });

        it('应该包含 get_screenshot_dir 能力', () => {
            const capability = adapter.capabilities.find(c => c.id === 'get_screenshot_dir');
            expect(capability).toBeDefined();
            expect(capability?.permissionLevel).toBe('public');
        });
    });

    describe('get_screenshot_dir', () => {
        it('应该返回截图目录', async () => {
            const result = await adapter.invoke('get_screenshot_dir', {});
            expect(result.success).toBe(true);
            expect(result.data?.directory).toContain('AIOS Screenshots');
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
