/**
 * PermissionManager 单元测试
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PermissionManager } from '../../core/PermissionManager.js';

// Mock child_process
vi.mock('child_process', () => ({
    exec: vi.fn((cmd, callback) => {
        // 模拟各种命令的响应
        if (cmd.includes('osascript') && cmd.includes('System Events')) {
            callback(null, 'true', '');
        } else if (cmd.includes('screencapture')) {
            callback(null, '', '');
        } else if (cmd.includes('IsInRole')) {
            callback(null, 'False', '');
        } else {
            callback(null, '', '');
        }
    }),
}));

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

describe('PermissionManager', () => {
    let manager: PermissionManager;

    beforeEach(() => {
        manager = PermissionManager.getInstance();
        manager.clearCache();
    });

    afterEach(() => {
        manager.clearCache();
    });

    describe('getInstance', () => {
        it('应该返回单例实例', () => {
            const instance1 = PermissionManager.getInstance();
            const instance2 = PermissionManager.getInstance();
            expect(instance1).toBe(instance2);
        });
    });

    describe('checkPermission', () => {
        it('public 级别应该总是返回 granted', async () => {
            const result = await manager.checkPermission('public');
            expect(result.granted).toBe(true);
            expect(result.level).toBe('public');
        });

        it('low 级别应该返回 granted', async () => {
            const result = await manager.checkPermission('low');
            expect(result.granted).toBe(true);
            expect(result.level).toBe('low');
        });

        it('应该缓存权限检查结果', async () => {
            await manager.checkPermission('low');
            const result = await manager.checkPermission('low');
            expect(result.granted).toBe(true);
        });
    });

    describe('requestPermission', () => {
        it('public 级别应该直接返回成功', async () => {
            const result = await manager.requestPermission('public');
            expect(result.success).toBe(true);
            expect(result.granted).toBe(true);
        });

        it('low 级别应该直接返回成功', async () => {
            const result = await manager.requestPermission('low');
            expect(result.success).toBe(true);
            expect(result.granted).toBe(true);
        });
    });

    describe('getRequiredPermissions', () => {
        it('应该返回权限要求列表', () => {
            const requirements = manager.getRequiredPermissions('test-adapter', 'test-capability');
            expect(requirements).toHaveLength(1);
            expect(requirements[0].level).toBe('low');
        });
    });

    describe('clearCache', () => {
        it('应该清除缓存', async () => {
            await manager.checkPermission('low');
            manager.clearCache();
            // 再次检查应该重新执行检查逻辑
            const result = await manager.checkPermission('low');
            expect(result.granted).toBe(true);
        });
    });
});
