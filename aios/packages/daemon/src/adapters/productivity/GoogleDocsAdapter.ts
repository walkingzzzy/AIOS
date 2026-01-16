import { BaseAdapter } from '../BaseAdapter.js';
import type { AdapterResult, AdapterCapability } from '@aios/shared';
import type { OAuthManager } from '../../auth/index.js';

// Google API 响应类型定义（按照 typescript skill 要求）
interface GoogleDocResponse {
    documentId: string;
    title: string;
    body?: unknown;
}

interface GoogleSpreadsheetResponse {
    spreadsheetId: string;
    spreadsheetUrl: string;
    properties: { title: string };
}

interface GoogleSheetsReadResponse {
    range: string;
    values?: unknown[][];
}

interface GoogleSheetsWriteResponse {
    updatedRange: string;
    updatedRows: number;
    updatedColumns: number;
    updatedCells: number;
}

export class GoogleWorkspaceAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.google_workspace';
    readonly name = 'Google Workspace';
    readonly description = 'Google Workspace 管理（Docs + Sheets）';
    readonly capabilities: AdapterCapability[] = [
        // Google Docs 功能
        { id: 'create_document', name: 'create_document', description: '创建新文档', permissionLevel: 'medium', parameters: [{ name: 'title', type: 'string', required: true, description: '文档标题' }] },
        { id: 'get_document', name: 'get_document', description: '获取文档内容', permissionLevel: 'low', parameters: [{ name: 'documentId', type: 'string', required: true, description: '文档 ID' }] },
        { id: 'append_text', name: 'append_text', description: '在文档末尾追加文本', permissionLevel: 'medium', parameters: [{ name: 'documentId', type: 'string', required: true, description: '文档 ID' }, { name: 'text', type: 'string', required: true, description: '要追加的文本' }] },

        // Google Sheets 功能
        { id: 'create_spreadsheet', name: 'create_spreadsheet', description: '创建新表格', permissionLevel: 'medium', parameters: [{ name: 'title', type: 'string', required: true, description: '表格标题' }] },
        { id: 'read_spreadsheet', name: 'read_spreadsheet', description: '读取表格数据', permissionLevel: 'low', parameters: [{ name: 'spreadsheetId', type: 'string', required: true, description: '表格 ID' }, { name: 'range', type: 'string', required: true, description: '范围（如 Sheet1!A1:C10）' }] },
        { id: 'write_spreadsheet', name: 'write_spreadsheet', description: '写入表格数据', permissionLevel: 'medium', parameters: [{ name: 'spreadsheetId', type: 'string', required: true, description: '表格 ID' }, { name: 'range', type: 'string', required: true, description: '范围' }, { name: 'values', type: 'array', required: true, description: '要写入的数据（二维数组）' }] },
    ];

    private oauth: OAuthManager | null = null;
    private readonly providerId = 'google';

    setOAuthManager(oauth: OAuthManager): void {
        this.oauth = oauth;
    }

    async checkAvailability(): Promise<boolean> {
        return this.oauth?.isAuthenticated(this.providerId) ?? false;
    }

    async invoke(capability: string, params: Record<string, unknown>): Promise<AdapterResult> {
        if (!this.oauth) return this.failure('NO_OAUTH', 'OAuth manager not configured');

        try {
            const token = await this.oauth.getAccessToken(this.providerId);
            switch (capability) {
                // Docs
                case 'create_document': return this.createDocument(token, params.title as string);
                case 'get_document': return this.getDocument(token, params.documentId as string);
                case 'append_text': return this.appendText(token, params.documentId as string, params.text as string);
                // Sheets
                case 'create_spreadsheet': return this.createSpreadsheet(token, params.title as string);
                case 'read_spreadsheet': return this.readSpreadsheet(token, params.spreadsheetId as string, params.range as string);
                case 'write_spreadsheet': return this.writeSpreadsheet(token, params.spreadsheetId as string, params.range as string, params.values as unknown[][]);
                default: return this.failure('UNKNOWN_CAPABILITY', `Unknown capability: ${capability}`);
            }
        } catch (error) {
            return this.failure('API_ERROR', (error as Error).message);
        }
    }

    // ==================== Google Docs ====================

    private async createDocument(token: string, title: string): Promise<AdapterResult> {
        const res = await fetch('https://docs.googleapis.com/v1/documents', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ title }),
        });
        if (!res.ok) return this.failure('DOCS_ERROR', `API error: ${res.status}`);
        const data = await res.json() as GoogleDocResponse;
        return this.success({ documentId: data.documentId, title: data.title });
    }

    private async getDocument(token: string, documentId: string): Promise<AdapterResult> {
        const res = await fetch(`https://docs.googleapis.com/v1/documents/${documentId}`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });
        if (!res.ok) return this.failure('DOCS_ERROR', `API error: ${res.status}`);
        const data = await res.json() as GoogleDocResponse;
        return this.success({ documentId: data.documentId, title: data.title, body: data.body });
    }

    private async appendText(token: string, documentId: string, text: string): Promise<AdapterResult> {
        const res = await fetch(`https://docs.googleapis.com/v1/documents/${documentId}:batchUpdate`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({
                requests: [{ insertText: { location: { index: 1 }, text } }],
            }),
        });
        if (!res.ok) return this.failure('DOCS_ERROR', `API error: ${res.status}`);
        return this.success({ documentId });
    }

    // ==================== Google Sheets ====================

    private async createSpreadsheet(token: string, title: string): Promise<AdapterResult> {
        const res = await fetch('https://sheets.googleapis.com/v4/spreadsheets', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({
                properties: { title },
            }),
        });
        if (!res.ok) return this.failure('SHEETS_ERROR', `API error: ${res.status}`);
        const data = await res.json() as GoogleSpreadsheetResponse;
        return this.success({
            spreadsheetId: data.spreadsheetId,
            spreadsheetUrl: data.spreadsheetUrl,
            title: data.properties.title,
        });
    }

    private async readSpreadsheet(token: string, spreadsheetId: string, range: string): Promise<AdapterResult> {
        const res = await fetch(
            `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}`,
            {
                headers: { 'Authorization': `Bearer ${token}` },
            }
        );
        if (!res.ok) return this.failure('SHEETS_ERROR', `API error: ${res.status}`);
        const data = await res.json() as GoogleSheetsReadResponse;
        return this.success({
            range: data.range,
            values: data.values ?? [],
        });
    }

    private async writeSpreadsheet(token: string, spreadsheetId: string, range: string, values: unknown[][]): Promise<AdapterResult> {
        const res = await fetch(
            `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?valueInputOption=RAW`,
            {
                method: 'PUT',
                headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ values }),
            }
        );
        if (!res.ok) return this.failure('SHEETS_ERROR', `API error: ${res.status}`);
        const data = await res.json() as GoogleSheetsWriteResponse;
        return this.success({
            updatedRange: data.updatedRange,
            updatedRows: data.updatedRows,
            updatedColumns: data.updatedColumns,
            updatedCells: data.updatedCells,
        });
    }
}
