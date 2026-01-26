/**
 * AppsAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const openMock = vi.hoisted(() => vi.fn(async () => undefined));
const psListMock = vi.hoisted(() => vi.fn(async () => ([
    { pid: 101, name: 'TestApp', cpu: 1, memory: 100 },
])));
const discoveryMocks = vi.hoisted(() => ({
    scan: vi.fn(async () => ([{ name: 'App A' }])),
    search: vi.fn(async (query: string) => ([{ name: `Result ${query}` }])),
    findByBundleId: vi.fn(async (bundleId: string) => ({ name: 'App A', bundleId })),
}));

vi.mock('open', () => ({ default: openMock }));
vi.mock('ps-list', () => ({ default: psListMock }));
vi.mock('../../core/SoftwareDiscovery.js', () => ({
    SoftwareDiscovery: class {
        scan = discoveryMocks.scan;
        search = discoveryMocks.search;
        findByBundleId = discoveryMocks.findByBundleId;
    },
}));

import { AppsAdapter } from '../../adapters/apps/AppsAdapter';

describe('AppsAdapter', () => {
    let adapter: AppsAdapter;
    let killSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(async () => {
        adapter = new AppsAdapter();
        await adapter.initialize();
        killSpy = vi.spyOn(process, 'kill').mockImplementation(() => true as unknown as void);
    });

    afterEach(() => {
        killSpy.mockRestore();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.apps');
            expect(adapter.name).toBe('应用管理');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('open_app');
            expect(capabilityIds).toContain('list_processes');
            expect(capabilityIds).toContain('list_installed_apps');
            expect(capabilityIds).toContain('search_installed_apps');
            expect(capabilityIds).toContain('find_installed_app');
        });
    });

    describe('应用操作', () => {
        it('应该能打开应用', async () => {
            const result = await adapter.invoke('open_app', { name: 'TestApp' });

            expect(result.success).toBe(true);
            expect(openMock).toHaveBeenCalled();
        });

        it('应该能列出进程', async () => {
            const result = await adapter.invoke('list_processes', {});

            expect(result.success).toBe(true);
            const processes = (result.data as { processes?: unknown[] }).processes;
            expect(Array.isArray(processes)).toBe(true);
        });

        it('应该能列出已安装应用', async () => {
            const result = await adapter.invoke('list_installed_apps', {});

            expect(result.success).toBe(true);
            const apps = (result.data as { apps?: unknown[] }).apps;
            expect(Array.isArray(apps)).toBe(true);
        });

        it('应该能搜索已安装应用', async () => {
            const result = await adapter.invoke('search_installed_apps', { query: 'App' });

            expect(result.success).toBe(true);
            expect((result.data as { query?: string }).query).toBe('App');
        });

        it('应该能查找应用', async () => {
            const result = await adapter.invoke('find_installed_app', { bundleId: 'com.test.app' });

            expect(result.success).toBe(true);
            expect((result.data as { app?: { bundleId?: string } }).app?.bundleId).toBe('com.test.app');
        });

        it('应该能终止进程', async () => {
            const result = await adapter.invoke('kill_process', { pid: 123 });

            expect(result.success).toBe(true);
            expect(killSpy).toHaveBeenCalledWith(123);
        });

        it('应该能关闭应用', async () => {
            const result = await adapter.invoke('close_app', { name: 'TestApp' });

            expect(result.success).toBe(true);
            expect(killSpy).toHaveBeenCalled();
        });
    });
});
