import { describe, it, expect, vi } from 'vitest';
import { MCPServer } from '../../protocol/MCPServer.js';
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

function createAdapter(
    id: string,
    capabilityId: string,
    invokeResult: AdapterResult
): IAdapter & { invoke: ReturnType<typeof vi.fn> } {
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

describe('MCPServer', () => {
    it('awaits tools/call and resolves adapterId/capabilityId safely', async () => {
        const google = createAdapter('google', 'send_email', { success: true, data: { from: 'google' } });
        const googleWorkspace = createAdapter('google_workspace', 'send_email', { success: true, data: { from: 'workspace' } });
        const registry = createMockRegistry([google, googleWorkspace]);

        const server = new MCPServer(registry);

        const listResponse = await (server as any).handleMessage({ id: 1, method: 'tools/list', params: {} });
        expect(listResponse.result.tools).toEqual(
            expect.arrayContaining([
                expect.objectContaining({ name: 'google_send_email' }),
                expect.objectContaining({ name: 'google_workspace_send_email' }),
            ])
        );

        const callResponse = await (server as any).handleMessage({
            id: 2,
            method: 'tools/call',
            params: { name: 'google_workspace_send_email', arguments: { foo: 'bar' } },
        });

        expect(googleWorkspace.invoke).toHaveBeenCalledWith('send_email', { foo: 'bar' });
        expect(google.invoke).not.toHaveBeenCalled();
        const payload = JSON.parse(callResponse.result.content[0].text);
        expect(payload.success).toBe(true);
        expect(payload.data).toEqual({ from: 'workspace' });
    });
});
