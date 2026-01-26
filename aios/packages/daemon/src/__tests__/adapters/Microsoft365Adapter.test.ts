/**
 * Microsoft365Adapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { Microsoft365Adapter } from '../../adapters/productivity/Microsoft365Adapter';
import type { OAuthManager } from '../../auth';

describe('Microsoft365Adapter', () => {
    let adapter: Microsoft365Adapter;
    let oauth: OAuthManager;

    beforeEach(() => {
        adapter = new Microsoft365Adapter();
        oauth = {
            isAuthenticated: vi.fn(() => true),
            getAccessToken: vi.fn(async () => 'test-token'),
        } as unknown as OAuthManager;
        adapter.setOAuthManager(oauth);

        const fetchMock = vi.fn(async (url: RequestInfo, init?: RequestInit) => {
            const target = typeof url === 'string' ? url : url.toString();
            const method = init?.method ?? 'GET';

            if (target.includes('/me/drive/root:') && target.endsWith(':/content') && method === 'PUT') {
                return {
                    ok: true,
                    status: 201,
                    json: async () => ({ id: 'item-1', name: 'file.docx', webUrl: 'https://file' }),
                } as Response;
            }

            if (target.includes('/me/drive/items/item-1/preview') && method === 'POST') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ getUrl: 'https://preview' }),
                } as Response;
            }

            if (target.includes('/me/drive/root/children') && method === 'GET') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ value: [{ id: 'item-1', name: 'file.docx' }] }),
                } as Response;
            }

            if (target.includes("/workbook/worksheets/Sheet1/range(address='A1:B2')") && method === 'GET') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ address: 'A1:B2', values: [[1, 2]], rowCount: 1, columnCount: 2 }),
                } as Response;
            }

            if (target.includes("/workbook/worksheets/Sheet1/range(address='A1')") && method === 'PATCH') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ address: 'A1', rowCount: 1, columnCount: 1 }),
                } as Response;
            }

            if (target.includes('/me/drive/items/item-1') && method === 'GET') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ id: 'item-1', name: 'file.docx', webUrl: 'https://file' }),
                } as Response;
            }

            if (target.includes('/me/drive/items/item-1') && method === 'DELETE') {
                return { ok: true, status: 204, json: async () => ({}) } as Response;
            }

            return { ok: false, status: 500, json: async () => ({}) } as Response;
        });

        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.microsoft365');
            expect(adapter.name).toBe('Microsoft 365');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('word_create');
            expect(capabilityIds).toContain('word_get_content');
            expect(capabilityIds).toContain('excel_read_range');
            expect(capabilityIds).toContain('excel_write_range');
            expect(capabilityIds).toContain('ppt_get_slides');
            expect(capabilityIds).toContain('list_files');
            expect(capabilityIds).toContain('delete_file');
        });
    });

    describe('办公操作', () => {
        it('应该能创建 Word 文档', async () => {
            const result = await adapter.invoke('word_create', { name: 'file' });

            expect(result.success).toBe(true);
            expect((result.data as { id?: string }).id).toBe('item-1');
        });

        it('应该能读取 Word 文档信息', async () => {
            const result = await adapter.invoke('word_get_content', { itemId: 'item-1' });

            expect(result.success).toBe(true);
            expect((result.data as { id?: string }).id).toBe('item-1');
        });

        it('应该能读取 Excel 范围', async () => {
            const result = await adapter.invoke('excel_read_range', {
                itemId: 'item-1',
                worksheet: 'Sheet1',
                range: 'A1:B2',
            });

            expect(result.success).toBe(true);
            expect((result.data as { address?: string }).address).toBe('A1:B2');
        });

        it('应该能写入 Excel 范围', async () => {
            const result = await adapter.invoke('excel_write_range', {
                itemId: 'item-1',
                worksheet: 'Sheet1',
                range: 'A1',
                values: [[1]],
            });

            expect(result.success).toBe(true);
        });

        it('应该能获取 PPT 预览', async () => {
            const result = await adapter.invoke('ppt_get_slides', { itemId: 'item-1' });

            expect(result.success).toBe(true);
            expect((result.data as { previewUrl?: string }).previewUrl).toBe('https://preview');
        });

        it('应该能列出文件', async () => {
            const result = await adapter.invoke('list_files', {});

            expect(result.success).toBe(true);
            const files = (result.data as { files?: unknown[] }).files;
            expect(Array.isArray(files)).toBe(true);
        });

        it('应该能删除文件', async () => {
            const result = await adapter.invoke('delete_file', { itemId: 'item-1' });

            expect(result.success).toBe(true);
            expect((result.data as { deleted?: boolean }).deleted).toBe(true);
        });
    });

    describe('权限检查', () => {
        it('未配置 OAuth 时应该失败', async () => {
            const noAuth = new Microsoft365Adapter();
            const result = await noAuth.invoke('list_files', {});

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('NO_OAUTH');
        });
    });
});
