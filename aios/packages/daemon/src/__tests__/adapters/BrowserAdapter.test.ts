/**
 * BrowserAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { BrowserAdapter } from '../../adapters/browser/BrowserAdapter';

describe('BrowserAdapter', () => {
    let adapter: BrowserAdapter;

    beforeEach(() => {
        adapter = new BrowserAdapter();
    });

    afterEach(async () => {
        // 清理浏览器实例
        try {
            await adapter.execute('browser_close', {});
        } catch (error) {
            // Ignore cleanup errors
        }
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('browser');
            expect(adapter.name).toBe('Browser Automation');
            expect(adapter.permissionLevel).toBe('high');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('browser_navigate');
            expect(toolNames).toContain('browser_click');
            expect(toolNames).toContain('browser_type');
            expect(toolNames).toContain('browser_screenshot');
        });
    });

    describe('浏览器操作', () => {
        it('应该能导航到URL', async () => {
            const result = await adapter.execute('browser_navigate', {
                url: 'https://example.com'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能截图', async () => {
            await adapter.execute('browser_navigate', {
                url: 'https://example.com'
            });

            const result = await adapter.execute('browser_screenshot', {});

            expect(result).toBeDefined();
            expect(result.screenshot).toBeDefined();
        });

        it('应该能点击元素', async () => {
            await adapter.execute('browser_navigate', {
                url: 'https://example.com'
            });

            const result = await adapter.execute('browser_click', {
                selector: 'a'
            });

            expect(result).toBeDefined();
        });

        it('应该能输入文本', async () => {
            await adapter.execute('browser_navigate', {
                url: 'https://example.com'
            });

            const result = await adapter.execute('browser_type', {
                selector: 'input',
                text: 'Test'
            });

            expect(result).toBeDefined();
        });

        it('应该拒绝无效的URL', async () => {
            await expect(
                adapter.execute('browser_navigate', { url: 'invalid-url' })
            ).rejects.toThrow();
        });

        it('应该拒绝危险的URL', async () => {
            await expect(
                adapter.execute('browser_navigate', { url: 'file:///etc/passwd' })
            ).rejects.toThrow();
        });
    });
});
