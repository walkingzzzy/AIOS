/**
 * ClipboardAdapter 单元测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ClipboardAdapter } from '../../adapters/clipboard/ClipboardAdapter.js';

// Mock child_process
vi.mock('child_process', () => ({
    exec: vi.fn((cmd, callback) => {
        if (cmd.includes('pbpaste') || cmd.includes('Get-Clipboard') || cmd.includes('xclip -selection clipboard -o')) {
            callback(null, 'test clipboard content', '');
        } else {
            callback(null, '', '');
        }
    }),
}));

vi.mock('util', () => ({
    promisify: vi.fn((fn) => {
        return async (...args: unknown[]) => {
            return new Promise((resolve, reject) => {
                fn(...args, (err: Error | null, stdout: string, stderr: string) => {
                    if (err) reject(err);
                    else resolve({ stdout, stderr });
                });
            });
        };
    }),
}));

describe('ClipboardAdapter', () => {
    let adapter: ClipboardAdapter;

    beforeEach(() => {
        adapter = new ClipboardAdapter();
    });

    describe('基本属性', () => {
        it('应该有正确的 id', () => {
            expect(adapter.id).toBe('com.aios.adapter.clipboard');
        });

        it('应该有正确的名称', () => {
            expect(adapter.name).toBe('剪贴板');
        });

        it('应该有 4 个能力', () => {
            expect(adapter.capabilities).toHaveLength(4);
        });

        it('应该包含 read_text 能力', () => {
            const capability = adapter.capabilities.find(c => c.id === 'read_text');
            expect(capability).toBeDefined();
            expect(capability?.permissionLevel).toBe('low');
        });

        it('应该包含 write_text 能力', () => {
            const capability = adapter.capabilities.find(c => c.id === 'write_text');
            expect(capability).toBeDefined();
            expect(capability?.parameters).toHaveLength(1);
        });
    });

    describe('错误处理', () => {
        it('应该处理未知能力', async () => {
            const result = await adapter.invoke('unknown_capability', {});
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('CAPABILITY_NOT_FOUND');
        });
    });
});
