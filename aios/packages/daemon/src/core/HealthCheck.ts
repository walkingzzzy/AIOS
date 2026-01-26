/**
 * 健康检查服务
 */

import type { AdapterRegistry } from './AdapterRegistry.js';

export interface HealthAdapterStatus {
    id: string;
    name: string;
    available: boolean;
}

export interface HealthTransportStatus {
    stdio: { enabled: boolean };
    websocket: { enabled: boolean; port?: number; clients?: number };
    mcp: { enabled: boolean; mode?: 'v1' | 'v2'; port?: number; host?: string };
    a2a: { enabled: boolean; port?: number; host?: string };
}

export interface HealthSnapshot {
    ok: boolean;
    status: 'ok' | 'degraded';
    timestamp: number;
    startedAt: number;
    uptimeSeconds: number;
    version: string;
    platform: string;
    arch: string;
    node: string;
    adapters: {
        total: number;
        available: number;
        unavailable: number;
        details: HealthAdapterStatus[];
    };
    transports: HealthTransportStatus;
}

export class HealthCheckService {
    constructor(private options: {
        adapterRegistry: AdapterRegistry;
        version: string;
        startedAt: number;
        transportProvider: () => HealthTransportStatus;
    }) {}

    async check(): Promise<HealthSnapshot> {
        const adapters = this.options.adapterRegistry.getAll();
        const details = await Promise.all(
            adapters.map(async (adapter) => ({
                id: adapter.id,
                name: adapter.name,
                available: await adapter.checkAvailability(),
            }))
        );

        const available = details.filter((item) => item.available).length;
        const total = details.length;
        const status = available === total ? 'ok' : 'degraded';

        return {
            ok: status === 'ok',
            status,
            timestamp: Date.now(),
            startedAt: this.options.startedAt,
            uptimeSeconds: Math.floor(process.uptime()),
            version: this.options.version,
            platform: process.platform,
            arch: process.arch,
            node: process.version,
            adapters: {
                total,
                available,
                unavailable: total - available,
                details,
            },
            transports: this.options.transportProvider(),
        };
    }
}
