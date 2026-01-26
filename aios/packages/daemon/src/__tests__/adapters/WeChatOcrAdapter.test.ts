/**
 * WeChatOcrAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('@aios/shared', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@aios/shared')>();
    return {
        ...actual,
        getPlatform: () => 'darwin',
    };
});

vi.mock('child_process', async (importOriginal) => {
    const actual = await importOriginal<typeof import('child_process')>();
    return {
        ...actual,
        execFile: vi.fn((cmd, args, options, callback) => {
            const cb = typeof options === 'function' ? options : callback;
            const cmdStr = String(cmd);
            if (cmdStr.includes('tesseract') && Array.isArray(args) && args[0] !== 'which') {
                cb?.(null, '识别结果', '');
                return;
            }
            cb?.(null, '', '');
        }),
    };
});

vi.mock('util', () => ({
    promisify: vi.fn((fn) => {
        return async (...args: unknown[]) => {
            return new Promise((resolve, reject) => {
                fn(...args, (err: Error | null, stdout: string) => {
                    if (err) reject(err);
                    else resolve({ stdout });
                });
            });
        };
    }),
}));

describe('WeChatOcrAdapter', () => {
    let adapter: import('../../adapters/cn/WeChatOcrAdapter').WeChatOcrAdapter;
    let WeChatOcrAdapter: typeof import('../../adapters/cn/WeChatOcrAdapter').WeChatOcrAdapter;

    beforeEach(async () => {
        ({ WeChatOcrAdapter } = await import('../../adapters/cn/WeChatOcrAdapter'));
        adapter = new WeChatOcrAdapter();
    });

    it('应通过 OCR 返回文本', async () => {
        const result = await adapter.invoke('wechat_capture_ocr', { mode: 'screen' });
        expect(result.success).toBe(true);
        const data = result.data as { text?: string };
        expect(data.text).toBe('识别结果');
    });
});
