import { BaseAdapter } from '../BaseAdapter.js';
import type { AdapterCapability, AdapterResult } from '@aios/shared';

// Notion API 响应类型
interface NotionPage {
    id: string;
    url?: string;
}

interface NotionSearchItem {
    id: string;
    object: string;
}

interface NotionDatabase {
    id: string;
    title?: Array<{ plain_text?: string }>;
}

interface NotionSearchResponse {
    results: NotionSearchItem[];
}

interface NotionDatabasesResponse {
    results: NotionDatabase[];
}

export class NotionAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.notion';
    readonly name = 'Notion';
    readonly description = 'Notion 生产力工具适配器';
    readonly capabilities: AdapterCapability[] = [
        {
            id: 'create_page',
            name: 'create_page',
            description: '在 Notion 数据库中创建新页面',
            permissionLevel: 'medium',
            parameters: [
                { name: 'databaseId', type: 'string', required: true, description: '数据库 ID' },
                { name: 'title', type: 'string', required: true, description: '页面标题' },
                { name: 'properties', type: 'object', required: false, description: '页面属性' },
            ],
        },
        {
            id: 'search',
            name: 'search',
            description: '搜索 Notion 页面和数据库',
            permissionLevel: 'low',
            parameters: [
                { name: 'query', type: 'string', required: true, description: '搜索关键词' },
            ],
        },
        {
            id: 'list_databases',
            name: 'list_databases',
            description: '获取 Notion 数据库列表',
            permissionLevel: 'low',
        },
    ];

    private token: string | null = null;

    setToken(token: string): void {
        this.token = token;
    }

    async checkAvailability(): Promise<boolean> {
        return this.token !== null;
    }

    async invoke(capability: string, params: Record<string, unknown>): Promise<AdapterResult> {
        if (!this.token) {
            return this.failure('NO_TOKEN', 'Notion token not configured');
        }

        switch (capability) {
            case 'create_page':
                return this.createPage(params.databaseId as string, params.title as string, params.properties as Record<string, unknown>);
            case 'search':
                return this.search(params.query as string);
            case 'list_databases':
                return this.listDatabases();
            default:
                return this.failure('UNKNOWN_CAPABILITY', `Unknown capability: ${capability}`);
        }
    }

    private async createPage(databaseId: string, title: string, properties?: Record<string, unknown>): Promise<AdapterResult> {
        const response = await fetch('https://api.notion.com/v1/pages', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json',
                'Notion-Version': '2022-06-28',
            },
            body: JSON.stringify({
                parent: { database_id: databaseId },
                properties: {
                    title: { title: [{ text: { content: title } }] },
                    ...properties,
                },
            }),
        });
        if (!response.ok) {
            return this.failure('NOTION_API_ERROR', `Notion API error: ${response.status}`);
        }
        const data = await response.json() as NotionPage;
        return this.success({ id: data.id, url: data.url });
    }

    private async search(query: string): Promise<AdapterResult> {
        const response = await fetch('https://api.notion.com/v1/search', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json',
                'Notion-Version': '2022-06-28',
            },
            body: JSON.stringify({ query }),
        });
        if (!response.ok) {
            return this.failure('NOTION_API_ERROR', `Notion API error: ${response.status}`);
        }
        const data = await response.json() as NotionSearchResponse;
        return this.success({ results: data.results.map((r) => ({ id: r.id, type: r.object })) });
    }

    private async listDatabases(): Promise<AdapterResult> {
        const response = await fetch('https://api.notion.com/v1/search', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json',
                'Notion-Version': '2022-06-28',
            },
            body: JSON.stringify({ filter: { property: 'object', value: 'database' } }),
        });
        if (!response.ok) {
            return this.failure('NOTION_API_ERROR', `Notion API error: ${response.status}`);
        }
        const data = await response.json() as NotionDatabasesResponse;
        return this.success({ databases: data.results.map((d) => ({ id: d.id, title: d.title?.[0]?.plain_text })) });
    }
}
