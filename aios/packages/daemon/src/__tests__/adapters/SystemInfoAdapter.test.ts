/**
 * SystemInfoAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SystemInfoAdapter } from '../../adapters/system/SystemInfoAdapter';

vi.mock('systeminformation', () => ({
    cpu: vi.fn(async () => ({ brand: 'TestCPU', cores: 8, speed: '3.0' })),
    currentLoad: vi.fn(async () => ({ currentLoad: 42 })),
    mem: vi.fn(async () => ({ total: 8_000_000_000, used: 4_000_000_000, free: 4_000_000_000 })),
    battery: vi.fn(async () => ({ hasBattery: true, percent: 80, isCharging: true, timeRemaining: 120 })),
    fsSize: vi.fn(async () => ([{ mount: '/', size: 100 * 1024 ** 3, used: 50 * 1024 ** 3, use: 50 }])),
    graphics: vi.fn(async () => ({
        controllers: [{ model: 'TestGPU', vendor: 'TestVendor', vram: 4096 }],
        displays: [{ model: 'TestDisplay', resolutionX: 1920, resolutionY: 1080, currentResX: 1920, currentResY: 1080, sizeX: 520, sizeY: 320 }],
    })),
    osInfo: vi.fn(async () => ({ platform: 'linux', distro: 'TestOS', release: '1.0', arch: 'x64', hostname: 'test-host' })),
}));

describe('SystemInfoAdapter', () => {
    let adapter: SystemInfoAdapter;

    beforeEach(async () => {
        adapter = new SystemInfoAdapter();
        await adapter.initialize();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.systeminfo');
            expect(adapter.name).toBe('系统信息');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的工具列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('get_system');
            expect(capabilityIds).toContain('get_cpu');
            expect(capabilityIds).toContain('get_memory');
            expect(capabilityIds).toContain('get_display');
        });

        it('应该始终可用', async () => {
            const isAvailable = await adapter.checkAvailability();
            expect(isAvailable).toBe(true);
        });
    });

    describe('系统信息获取', () => {
        it('应该能获取系统信息', async () => {
            const result = await adapter.invoke('get_system', {});

            expect(result.success).toBe(true);
            const data = result.data as { platform?: string; arch?: string; hostname?: string };
            expect(data.platform).toBeDefined();
            expect(data.arch).toBeDefined();
            expect(data.hostname).toBeDefined();
        });

        it('应该能获取CPU使用率', async () => {
            const result = await adapter.invoke('get_cpu', {});

            expect(result.success).toBe(true);
            const data = result.data as { usage?: number };
            expect(typeof data.usage).toBe('number');
            expect(data.usage).toBeGreaterThanOrEqual(0);
            expect(data.usage).toBeLessThanOrEqual(100);
        });

        it('应该能获取内存使用情况', async () => {
            const result = await adapter.invoke('get_memory', {});

            expect(result.success).toBe(true);
            const data = result.data as { total?: number; free?: number; used?: number; usagePercent?: number };
            expect(data.total).toBeGreaterThan(0);
            expect(data.free).toBeGreaterThanOrEqual(0);
            expect(data.used).toBeGreaterThanOrEqual(0);
            expect(data.usagePercent).toBeGreaterThanOrEqual(0);
            expect(data.usagePercent).toBeLessThanOrEqual(100);
        });

        it('应该能获取磁盘使用情况', async () => {
            const result = await adapter.invoke('get_disk', {});

            expect(result.success).toBe(true);
            const data = result.data as { disks?: unknown[] };
            expect(Array.isArray(data.disks)).toBe(true);
        });

        it('应该能获取电池状态', async () => {
            const result = await adapter.invoke('get_battery', {});

            expect(result.success).toBe(true);
            const data = result.data as { hasBattery?: boolean; percent?: number; isCharging?: boolean };
            if (data.hasBattery) {
                expect(typeof data.percent).toBe('number');
                expect(typeof data.isCharging).toBe('boolean');
            }
        });

        it('应该能获取显示信息', async () => {
            const result = await adapter.invoke('get_display', {});

            expect(result.success).toBe(true);
            const data = result.data as { controllers?: unknown[]; displays?: unknown[] };
            expect(Array.isArray(data.controllers)).toBe(true);
            expect(Array.isArray(data.displays)).toBe(true);
        });
    });
});
