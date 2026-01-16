/**
 * NetworkAdapter 单元测试
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { NetworkAdapter } from '../../adapters/system/NetworkAdapter';

describe('NetworkAdapter', () => {
    let adapter: NetworkAdapter;

    beforeEach(() => {
        adapter = new NetworkAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('network');
            expect(adapter.name).toBe('Network Control');
            expect(adapter.permissionLevel).toBe('medium');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('network_get_status');
            expect(toolNames).toContain('network_list_interfaces');
        });
    });

    describe('网络状态', () => {
        it('应该能获取网络状态', async () => {
            const result = await adapter.execute('network_get_status', {});

            expect(result).toBeDefined();
            expect(typeof result.online).toBe('boolean');
        });

        it('应该能列出网络接口', async () => {
            const result = await adapter.execute('network_list_interfaces', {});

            expect(result).toBeDefined();
            expect(Array.isArray(result.interfaces)).toBe(true);
        });

        it('应该能获取接口详情', async () => {
            const listResult = await adapter.execute('network_list_interfaces', {});

            if (listResult.interfaces.length > 0) {
                const interfaceName = listResult.interfaces[0].name;
                const result = await adapter.execute('network_get_interface_info', {
                    interface: interfaceName
                });

                expect(result).toBeDefined();
                expect(result.name).toBe(interfaceName);
            }
        });

        it('应该能测试连接', async () => {
            const result = await adapter.execute('network_test_connection', {
                host: 'google.com'
            });

            expect(result).toBeDefined();
            expect(typeof result.reachable).toBe('boolean');
        });
    });
});
