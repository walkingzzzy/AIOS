/**
 * 适配器基类
 */

import type { IAdapter, AdapterResult, AdapterCapability } from '@aios/shared';
import { getPlatform, type Platform } from '@aios/shared';

export abstract class BaseAdapter implements IAdapter {
    abstract readonly id: string;
    abstract readonly name: string;
    abstract readonly description: string;
    abstract readonly capabilities: AdapterCapability[];

    /** 初始化适配器 */
    async initialize(): Promise<void> {
        // 默认无操作，子类可覆盖
    }

    /** 检查适配器可用性 */
    abstract checkAvailability(): Promise<boolean>;

    /** 调用能力 */
    abstract invoke(
        capability: string,
        args: Record<string, unknown>
    ): Promise<AdapterResult>;

    /** 关闭适配器 */
    async shutdown(): Promise<void> {
        // 默认无操作，子类可覆盖
    }

    /** 获取当前平台 */
    protected getPlatform(): Platform {
        return getPlatform();
    }

    /** 创建成功结果 */
    protected success(data?: Record<string, unknown>): AdapterResult {
        return { success: true, data };
    }

    /** 创建失败结果 */
    protected failure(code: string, message: string): AdapterResult {
        return { success: false, error: { code, message } };
    }
}
