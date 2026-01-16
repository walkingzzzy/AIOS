/**
 * SystemInfoAdapter 单元测试
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { SystemInfoAdapter } from '../../adapters/system/SystemInfoAdapter';

describe('SystemInfoAdapter', () => {
    let adapter: SystemInfoAdapter;

    beforeEach(() => {
        adapter = new SystemInfoAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('system_info');
            expect(adapter.name).toBe('System Information');
            expect(adapter.permissionLevel).toBe('public');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('system_get_info');
            expect(toolNames).toContain('system_get_cpu_usage');
            expect(toolNames).toContain('system_get_memory_usage');
        });

        it('应该始终可用', async () => {
            const isAvailable = await adapter.isAvailable();
            expect(isAvailable).toBe(true);
        });
    });

    describe('系统信息获取', () => {
        it('应该能获取系统信息', async () => {
            const result = await adapter.execute('system_get_info', {});

            expect(result).toBeDefined();
            expect(result.platform).toBeDefined();
            expect(result.arch).toBeDefined();
            expect(result.hostname).toBeDefined();
            expect(result.uptime).toBeGreaterThanOrEqual(0);
        });

        it('应该能获取CPU使用率', async () => {
            const result = await adapter.execute('system_get_cpu_usage', {});

            expect(result).toBeDefined();
            expect(typeof result.usage).toBe('number');
            expect(result.usage).toBeGreaterThanOrEqual(0);
            expect(result.usage).toBeLessThanOrEqual(100);
        });

        it('应该能获取内存使用情况', async () => {
            const result = await adapter.execute('system_get_memory_usage', {});

            expect(result).toBeDefined();
            expect(result.total).toBeGreaterThan(0);
            expect(result.free).toBeGreaterThanOrEqual(0);
            expect(result.used).toBeGreaterThanOrEqual(0);
            expect(result.usagePercent).toBeGreaterThanOrEqual(0);
            expect(result.usagePercent).toBeLessThanOrEqual(100);
        });

        it('应该能获取磁盘使用情况', async () => {
            const result = await adapter.execute('system_get_disk_usage', {});

            expect(result).toBeDefined();
            expect(Array.isArray(result.disks)).toBe(true);
        });

        it('应该能获取电池状态', async () => {
            const result = await adapter.execute('system_get_battery_status', {});

            expect(result).toBeDefined();
            // 电池状态可能不可用（台式机）
            if (result.available) {
                expect(typeof result.level).toBe('number');
                expect(typeof result.charging).toBe('boolean');
            }
        });
    });
});
