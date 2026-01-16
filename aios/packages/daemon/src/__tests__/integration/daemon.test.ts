/**
 * Daemon 集成测试
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { adapterRegistry } from '../../core/AdapterRegistry.js';
import { audioAdapter } from '../../adapters/system/AudioAdapter.js';
import { powerAdapter } from '../../adapters/system/PowerAdapter.js';
import { screenshotAdapter } from '../../adapters/screenshot/ScreenshotAdapter.js';
import { clipboardAdapter } from '../../adapters/clipboard/ClipboardAdapter.js';

describe('Daemon 集成测试', () => {
    beforeAll(async () => {
        // 注册适配器
        adapterRegistry.register(audioAdapter);
        adapterRegistry.register(powerAdapter);
        adapterRegistry.register(screenshotAdapter);
        adapterRegistry.register(clipboardAdapter);
        
        // 初始化
        await adapterRegistry.initializeAll();
    });

    afterAll(async () => {
        await adapterRegistry.shutdownAll();
    });

    describe('AdapterRegistry', () => {
        it('应该注册所有适配器', () => {
            const adapters = adapterRegistry.getAll();
            expect(adapters.length).toBeGreaterThanOrEqual(4);
        });

        it('应该能通过 ID 获取适配器', () => {
            const audio = adapterRegistry.get('com.aios.adapter.audio');
            expect(audio).toBeDefined();
            expect(audio?.name).toBe('音频控制');
        });

        it('应该返回 undefined 对于不存在的适配器', () => {
            const notFound = adapterRegistry.get('com.aios.adapter.notfound');
            expect(notFound).toBeUndefined();
        });
    });

    describe('适配器能力', () => {
        it('AudioAdapter 应该有 5 个能力', () => {
            const audio = adapterRegistry.get('com.aios.adapter.audio');
            expect(audio?.capabilities.length).toBe(5);
        });

        it('PowerAdapter 应该有 6 个能力', () => {
            const power = adapterRegistry.get('com.aios.adapter.power');
            expect(power?.capabilities.length).toBe(6);
        });

        it('ScreenshotAdapter 应该有 4 个能力', () => {
            const screenshot = adapterRegistry.get('com.aios.adapter.screenshot');
            expect(screenshot?.capabilities.length).toBe(4);
        });

        it('ClipboardAdapter 应该有 4 个能力', () => {
            const clipboard = adapterRegistry.get('com.aios.adapter.clipboard');
            expect(clipboard?.capabilities.length).toBe(4);
        });
    });

    describe('能力调用', () => {
        it('应该能调用 get_screenshot_dir', async () => {
            const screenshot = adapterRegistry.get('com.aios.adapter.screenshot');
            const result = await screenshot?.invoke('get_screenshot_dir', {});
            expect(result?.success).toBe(true);
            expect(result?.data?.directory).toBeDefined();
        });

        it('应该拒绝未确认的关机操作', async () => {
            const power = adapterRegistry.get('com.aios.adapter.power');
            const result = await power?.invoke('shutdown', {});
            expect(result?.success).toBe(false);
            expect(result?.error?.code).toBe('CONFIRMATION_REQUIRED');
        });
    });
});
