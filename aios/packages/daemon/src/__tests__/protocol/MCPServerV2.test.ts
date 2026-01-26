/**
 * MCPServerV2 单元测试
 */

import { describe, it, expect, vi } from 'vitest';
import { MCPServerV2 } from '../../protocol/MCPServerV2.js';
import type { AdapterRegistry } from '../../core/AdapterRegistry.js';
import type { IAdapter, AdapterCapability, AdapterResult } from '@aios/shared';

function createMockRegistry(adapters: IAdapter[]): AdapterRegistry {
    const byId = new Map(adapters.map(adapter => [adapter.id, adapter]));
    return {
        get: vi.fn((id: string) => byId.get(id)),
        getAll: vi.fn(() => adapters),
        register: vi.fn(),
        findByCapability: vi.fn(),
        initializeAll: vi.fn(),
        shutdownAll: vi.fn(),
    } as unknown as AdapterRegistry;
}

function createAdapter(id: string, capabilityId: string, invokeResult: AdapterResult): IAdapter & { invoke: ReturnType<typeof vi.fn> } {
    const capabilities: AdapterCapability[] = [
        {
            id: capabilityId,
            name: capabilityId,
            description: `${capabilityId} capability`,
            permissionLevel: 'public',
            parameters: [{ name: 'foo', type: 'string', required: false, description: 'foo' }],
        },
    ];

    return {
        id,
        name: id,
        description: id,
        capabilities,
        initialize: vi.fn(async () => undefined),
        checkAvailability: vi.fn(async () => true),
        invoke: vi.fn(async () => invokeResult),
        shutdown: vi.fn(async () => undefined),
    };
}

describe('MCPServerV2', () => {
    it('应该输出 tools/resources/prompts 元数据并支持调用', async () => {
        const adapter = createAdapter('com.aios.adapter.demo', 'ping', { success: true, data: { ok: true } });
        const registry = createMockRegistry([adapter]);
        const server = new MCPServerV2(registry);

        const tools = await (server as any).handleMessage({ id: 1, method: 'tools/list', params: {} });
        expect(tools.result.tools).toEqual(expect.arrayContaining([expect.objectContaining({ name: 'com.aios.adapter.demo_ping' })]));

        const resources = await (server as any).handleMessage({ id: 2, method: 'resources/list', params: {} });
        expect(resources.result.resources).toEqual(expect.arrayContaining([expect.objectContaining({ uri: 'adapters://list' })]));

        const prompts = await (server as any).handleMessage({ id: 3, method: 'prompts/list', params: {} });
        expect(prompts.result.prompts).toEqual(expect.arrayContaining([expect.objectContaining({ name: 'system_control' })]));

        const call = await (server as any).handleMessage({
            id: 4,
            method: 'tools/call',
            params: { name: 'com.aios.adapter.demo_ping', arguments: { foo: 'bar' } },
        });
        const payload = JSON.parse(call.result.content[0].text);
        expect(payload.success).toBe(true);
        expect(adapter.invoke).toHaveBeenCalledWith('ping', { foo: 'bar' });
    });
});
