/**
 * 适配器注册表
 */

import type { IAdapter } from '@aios/shared';

export class AdapterRegistry {
    private adapters: Map<string, IAdapter> = new Map();

    /** 注册适配器 */
    register(adapter: IAdapter): void {
        this.adapters.set(adapter.id, adapter);
    }

    /** 获取适配器 */
    get(id: string): IAdapter | undefined {
        return this.adapters.get(id);
    }

    /** 获取所有适配器 */
    getAll(): IAdapter[] {
        return Array.from(this.adapters.values());
    }

    /** 根据能力查找适配器 */
    findByCapability(capabilityId: string): IAdapter | undefined {
        for (const adapter of this.adapters.values()) {
            if (adapter.capabilities.some((c) => c.id === capabilityId)) {
                return adapter;
            }
        }
        return undefined;
    }

    /** 初始化所有适配器 */
    async initializeAll(): Promise<void> {
        for (const adapter of this.adapters.values()) {
            try {
                await adapter.initialize();
            } catch (error) {
                console.error(`[AdapterRegistry] Failed to initialize ${adapter.id}:`, error);
            }
        }
    }

    /** 关闭所有适配器 */
    async shutdownAll(): Promise<void> {
        for (const adapter of this.adapters.values()) {
            try {
                await adapter.shutdown();
            } catch (error) {
                console.error(`[AdapterRegistry] Failed to shutdown ${adapter.id}:`, error);
            }
        }
    }
}

/** 全局适配器注册表 */
export const adapterRegistry = new AdapterRegistry();
