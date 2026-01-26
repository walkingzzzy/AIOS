/**
 * GoogleWorkspaceAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { GoogleWorkspaceAdapter } from '../../adapters/productivity/GoogleDocsAdapter';
import type { OAuthManager } from '../../auth';

describe('GoogleWorkspaceAdapter', () => {
    let adapter: GoogleWorkspaceAdapter;
    let oauth: OAuthManager;

    beforeEach(() => {
        adapter = new GoogleWorkspaceAdapter();
        oauth = {
            isAuthenticated: vi.fn(() => true),
            getAccessToken: vi.fn(async () => 'test-token'),
        } as unknown as OAuthManager;
        adapter.setOAuthManager(oauth);

        const fetchMock = vi.fn(async (url: RequestInfo, init?: RequestInit) => {
            const target = typeof url === 'string' ? url : url.toString();
            const method = init?.method ?? 'GET';

            if (target === 'https://docs.googleapis.com/v1/documents' && method === 'POST') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ documentId: 'doc-1', title: 'Doc' }),
                } as Response;
            }

            if (target.includes('https://docs.googleapis.com/v1/documents/doc-1') && method === 'GET') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ documentId: 'doc-1', title: 'Doc', body: { content: [] } }),
                } as Response;
            }

            if (target.includes('https://docs.googleapis.com/v1/documents/doc-1:batchUpdate') && method === 'POST') {
                return { ok: true, status: 200, json: async () => ({}) } as Response;
            }

            if (target === 'https://sheets.googleapis.com/v4/spreadsheets' && method === 'POST') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({
                        spreadsheetId: 'sheet-1',
                        spreadsheetUrl: 'https://sheet',
                        properties: { title: 'Sheet' },
                    }),
                } as Response;
            }

            if (target.includes('sheets.googleapis.com') && target.includes('/values/') && method === 'GET') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ range: 'Sheet1!A1:B2', values: [[1, 2]] }),
                } as Response;
            }

            if (target.includes('sheets.googleapis.com') && target.includes('/values/') && method === 'PUT') {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({
                        updatedRange: 'Sheet1!A1:B2',
                        updatedRows: 1,
                        updatedColumns: 2,
                        updatedCells: 2,
                    }),
                } as Response;
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
            expect(adapter.id).toBe('com.aios.adapter.google_workspace');
            expect(adapter.name).toBe('Google Workspace');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('create_document');
            expect(capabilityIds).toContain('get_document');
            expect(capabilityIds).toContain('append_text');
            expect(capabilityIds).toContain('create_spreadsheet');
            expect(capabilityIds).toContain('read_spreadsheet');
            expect(capabilityIds).toContain('write_spreadsheet');
        });
    });

    describe('Docs 操作', () => {
        it('应该能创建文档', async () => {
            const result = await adapter.invoke('create_document', { title: 'Doc' });

            expect(result.success).toBe(true);
            expect((result.data as { documentId?: string }).documentId).toBe('doc-1');
        });

        it('应该能读取文档', async () => {
            const result = await adapter.invoke('get_document', { documentId: 'doc-1' });

            expect(result.success).toBe(true);
            expect((result.data as { documentId?: string }).documentId).toBe('doc-1');
        });

        it('应该能追加文本', async () => {
            const result = await adapter.invoke('append_text', { documentId: 'doc-1', text: 'Hello' });

            expect(result.success).toBe(true);
        });
    });

    describe('Sheets 操作', () => {
        it('应该能创建表格', async () => {
            const result = await adapter.invoke('create_spreadsheet', { title: 'Sheet' });

            expect(result.success).toBe(true);
            expect((result.data as { spreadsheetId?: string }).spreadsheetId).toBe('sheet-1');
        });

        it('应该能读取表格数据', async () => {
            const result = await adapter.invoke('read_spreadsheet', {
                spreadsheetId: 'sheet-1',
                range: 'Sheet1!A1:B2',
            });

            expect(result.success).toBe(true);
            const values = (result.data as { values?: unknown[] }).values;
            expect(Array.isArray(values)).toBe(true);
        });

        it('应该能写入表格数据', async () => {
            const result = await adapter.invoke('write_spreadsheet', {
                spreadsheetId: 'sheet-1',
                range: 'Sheet1!A1:B2',
                values: [[1, 2]],
            });

            expect(result.success).toBe(true);
        });
    });

    describe('权限检查', () => {
        it('未配置 OAuth 时应该失败', async () => {
            const noAuth = new GoogleWorkspaceAdapter();
            const result = await noAuth.invoke('create_document', { title: 'Doc' });

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('NO_OAUTH');
        });
    });
});
