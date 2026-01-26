/**
 * HealthCheckService 单元测试
 */

import { describe, it, expect } from 'vitest';
import { AdapterRegistry } from '../../core/AdapterRegistry.js';
import { HealthCheckService } from '../../core/HealthCheck.js';
import type { AdapterCapability, AdapterResult, IAdapter } from '@aios/shared';

class FakeAdapter implements IAdapter {
    readonly capabilities: AdapterCapability[] = [];

    constructor(
        public readonly id: string,
        public readonly name: string,
        public readonly description: string,
        private available: boolean
    ) {}

    async initialize(): Promise<void> {}

    async checkAvailability(): Promise<boolean> {
        return this.available;
    }

    async invoke(): Promise<AdapterResult> {
        return { success: true };
    }

    async shutdown(): Promise<void> {}
}

describe('HealthCheckService', () => {
    it('应该返回降级状态与适配器统计', async () => {
        const registry = new AdapterRegistry();
        registry.register(new FakeAdapter('adapter.ok', '可用适配器', 'ok', true));
        registry.register(new FakeAdapter('adapter.bad', '不可用适配器', 'bad', false));

        const service = new HealthCheckService({
            adapterRegistry: registry,
            version: '0.1.0',
            startedAt: 1700000000000,
            transportProvider: () => ({
                stdio: { enabled: true },
                websocket: { enabled: false },
                mcp: { enabled: false },
                a2a: { enabled: false },
            }),
        });

        const snapshot = await service.check();
        expect(snapshot.ok).toBe(false);
        expect(snapshot.status).toBe('degraded');
        expect(snapshot.adapters.total).toBe(2);
        expect(snapshot.adapters.available).toBe(1);
        expect(snapshot.adapters.unavailable).toBe(1);
        expect(snapshot.transports.stdio.enabled).toBe(true);
    });
});
