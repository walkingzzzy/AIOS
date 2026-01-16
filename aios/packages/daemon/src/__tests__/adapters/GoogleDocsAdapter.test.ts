/**
 * GoogleDocsAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { GoogleDocsAdapter } from '../../adapters/productivity/GoogleDocsAdapter';

describe('GoogleDocsAdapter', () => {
    let adapter: GoogleDocsAdapter;

    beforeEach(() => {
        adapter = new GoogleDocsAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('google_docs');
            expect(adapter.name).toBe('Google Docs');
            expect(adapter.permissionLevel).toBe('high');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('gdocs_create_document');
            expect(toolNames).toContain('gdocs_read_document');
        });
    });

    describe('文档操作', () => {
        it('应该能创建文档', async () => {
            const result = await adapter.execute('gdocs_create_document', {
                title: 'Test Document'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
            expect(result.documentId).toBeDefined();
        });

        it('应该能读取文档', async () => {
            const result = await adapter.execute('gdocs_read_document', {
                documentId: '123456'
            });

            expect(result).toBeDefined();
            expect(result.content).toBeDefined();
        });

        it('应该能更新文档', async () => {
            const result = await adapter.execute('gdocs_update_document', {
                documentId: '123456',
                content: 'Updated content'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });
    });

    describe('Sheets 操作', () => {
        it('应该能创建电子表格', async () => {
            const result = await adapter.execute('gsheets_create_spreadsheet', {
                title: 'Test Spreadsheet'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
            expect(result.spreadsheetId).toBeDefined();
        });

        it('应该能读取电子表格数据', async () => {
            const result = await adapter.execute('gsheets_read_range', {
                spreadsheetId: '123456',
                range: 'Sheet1!A1:B10'
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.values)).toBe(true);
        });

        it('应该能写入电子表格数据', async () => {
            const result = await adapter.execute('gsheets_write_range', {
                spreadsheetId: '123456',
                range: 'Sheet1!A1:B2',
                values: [['A1', 'B1'], ['A2', 'B2']]
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });
    });

    describe('Drive 操作', () => {
        it('应该能列出文件', async () => {
            const result = await adapter.execute('gdrive_list_files', {
                pageSize: 10
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.files)).toBe(true);
        });

        it('应该能搜索文件', async () => {
            const result = await adapter.execute('gdrive_search_files', {
                query: 'name contains "test"'
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.files)).toBe(true);
        });
    });
});
