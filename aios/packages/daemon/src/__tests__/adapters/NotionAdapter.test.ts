/**
 * NotionAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotionAdapter } from '../../adapters/productivity/NotionAdapter';

describe('NotionAdapter', () => {
    let adapter: NotionAdapter;

    beforeEach(() => {
        adapter = new NotionAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('notion');
            expect(adapter.name).toBe('Notion');
            expect(adapter.permissionLevel).toBe('high');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('notion_create_page');
            expect(toolNames).toContain('notion_search');
        });
    });

    describe('页面操作', () => {
        it('应该能创建页面', async () => {
            const result = await adapter.execute('notion_create_page', {
                parent: { database_id: '123456' },
                properties: {
                    title: { title: [{ text: { content: 'Test Page' } }] }
                }
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能搜索页面', async () => {
            const result = await adapter.execute('notion_search', {
                query: 'test'
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.results)).toBe(true);
        });

        it('应该能读取页面', async () => {
            const result = await adapter.execute('notion_get_page', {
                pageId: '123456'
            });

            expect(result).toBeDefined();
            expect(result.page).toBeDefined();
        });

        it('应该能更新页面', async () => {
            const result = await adapter.execute('notion_update_page', {
                pageId: '123456',
                properties: {
                    title: { title: [{ text: { content: 'Updated' } }] }
                }
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });
    });

    describe('数据库操作', () => {
        it('应该能查询数据库', async () => {
            const result = await adapter.execute('notion_query_database', {
                databaseId: '123456'
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.results)).toBe(true);
        });

        it('应该能创建数据库条目', async () => {
            const result = await adapter.execute('notion_create_database_entry', {
                databaseId: '123456',
                properties: {
                    Name: { title: [{ text: { content: 'Test' } }] }
                }
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });
    });
});
