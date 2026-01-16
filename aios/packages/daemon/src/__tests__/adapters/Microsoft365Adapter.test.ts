/**
 * Microsoft365Adapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { Microsoft365Adapter } from '../../adapters/productivity/Microsoft365Adapter';

describe('Microsoft365Adapter', () => {
    let adapter: Microsoft365Adapter;

    beforeEach(() => {
        adapter = new Microsoft365Adapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('microsoft365');
            expect(adapter.name).toBe('Microsoft 365');
            expect(adapter.permissionLevel).toBe('high');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('m365_create_document');
            expect(toolNames).toContain('m365_list_files');
        });
    });

    describe('文档操作', () => {
        it('应该能创建文档', async () => {
            const result = await adapter.execute('m365_create_document', {
                name: 'Test Document',
                content: 'Test content'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能列出文件', async () => {
            const result = await adapter.execute('m365_list_files', {
                folder: 'Documents'
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.files)).toBe(true);
        });

        it('应该能读取文档', async () => {
            const result = await adapter.execute('m365_read_document', {
                fileId: '123456'
            });

            expect(result).toBeDefined();
            expect(result.content).toBeDefined();
        });
    });

    describe('Excel 操作', () => {
        it('应该能创建工作簿', async () => {
            const result = await adapter.execute('m365_create_workbook', {
                name: 'Test Workbook'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能读取工作表数据', async () => {
            const result = await adapter.execute('m365_read_worksheet', {
                workbookId: '123456',
                worksheetName: 'Sheet1'
            });

            expect(result).toBeDefined();
            expect(result.data).toBeDefined();
        });
    });

    describe('Teams 操作', () => {
        it('应该能发送 Teams 消息', async () => {
            const result = await adapter.execute('m365_send_teams_message', {
                channelId: '123456',
                message: 'Test message'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能列出 Teams', async () => {
            const result = await adapter.execute('m365_list_teams', {});

            expect(result).toBeDefined();
            expect(Array.isArray(result.teams)).toBe(true);
        });
    });
});
