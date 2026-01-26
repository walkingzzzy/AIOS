/**
 * NotionAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { NotionAdapter } from '../../adapters/productivity/NotionAdapter';

describe('NotionAdapter', () => {
    let adapter: NotionAdapter;

    beforeEach(() => {
        adapter = new NotionAdapter();
        adapter.setToken('test-token');

        const fetchMock = vi.fn(async (url: RequestInfo, init?: RequestInit) => {
            const target = typeof url === 'string' ? url : url.toString();
            const body = typeof init?.body === 'string' ? init.body : '';

            if (target.endsWith('/v1/pages')) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ id: 'page-1', url: 'https://notion.so/page' }),
                } as Response;
            }

            if (target.endsWith('/v1/search') && body.includes('database')) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ results: [{ id: 'db-1', title: [{ plain_text: 'DB' }] }] }),
                } as Response;
            }

            if (target.endsWith('/v1/search')) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ results: [{ id: 'page-1', object: 'page' }] }),
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
            expect(adapter.id).toBe('com.aios.adapter.notion');
            expect(adapter.name).toBe('Notion');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('create_page');
            expect(capabilityIds).toContain('search');
            expect(capabilityIds).toContain('list_databases');
        });
    });

    describe('Notion 操作', () => {
        it('应该能创建页面', async () => {
            const result = await adapter.invoke('create_page', {
                databaseId: 'db-1',
                title: 'New Page',
            });

            expect(result.success).toBe(true);
            expect((result.data as { id?: string }).id).toBe('page-1');
        });

        it('应该能搜索', async () => {
            const result = await adapter.invoke('search', { query: 'test' });

            expect(result.success).toBe(true);
            const results = (result.data as { results?: unknown[] }).results;
            expect(Array.isArray(results)).toBe(true);
        });

        it('应该能列出数据库', async () => {
            const result = await adapter.invoke('list_databases', {});

            expect(result.success).toBe(true);
            const databases = (result.data as { databases?: unknown[] }).databases;
            expect(Array.isArray(databases)).toBe(true);
        });
    });

    describe('权限检查', () => {
        it('未配置 token 时应该失败', async () => {
            const noToken = new NotionAdapter();
            const result = await noToken.invoke('search', { query: 'test' });

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('NO_TOKEN');
        });
    });
});
