import { BaseAdapter } from '../BaseAdapter.js';
import type { AdapterResult, AdapterCapability } from '@aios/shared';
import type { OAuthManager } from '../../auth/index.js';

// Microsoft Graph API 响应类型定义（按照 typescript skill 要求）
interface DriveItem {
    id: string;
    name: string;
    size?: number;
    webUrl?: string;
    createdDateTime?: string;
    lastModifiedDateTime?: string;
    folder?: object;
}

interface DriveItemsResponse {
    value: DriveItem[];
}

interface PreviewResponse {
    getUrl?: string;
}

interface ExcelRangeResponse {
    address: string;
    values: unknown[][];
    rowCount: number;
    columnCount: number;
}

interface WorksheetResponse {
    id: string;
    name: string;
    position: number;
}

/**
 * Microsoft 365 办公套件适配器
 * 使用 Microsoft Graph API 控制 Word、Excel、PowerPoint
 */
export class Microsoft365Adapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.microsoft365';
    readonly name = 'Microsoft 365';
    readonly description = 'Microsoft 365 办公套件（Word/Excel/PowerPoint）';
    readonly capabilities: AdapterCapability[] = [
        // ==================== Word ====================
        {
            id: 'word_create',
            name: 'word_create',
            description: '创建新的 Word 文档',
            permissionLevel: 'medium',
            parameters: [
                { name: 'name', type: 'string', required: true, description: '文档名称' },
                { name: 'folder', type: 'string', required: false, description: '文件夹路径' },
            ],
        },
        {
            id: 'word_get_content',
            name: 'word_get_content',
            description: '获取 Word 文档内容',
            permissionLevel: 'low',
            parameters: [
                { name: 'itemId', type: 'string', required: true, description: '文档 ID' },
            ],
        },
        // ==================== Excel ====================
        {
            id: 'excel_create',
            name: 'excel_create',
            description: '创建新的 Excel 工作簿',
            permissionLevel: 'medium',
            parameters: [
                { name: 'name', type: 'string', required: true, description: '工作簿名称' },
                { name: 'folder', type: 'string', required: false, description: '文件夹路径' },
            ],
        },
        {
            id: 'excel_read_range',
            name: 'excel_read_range',
            description: '读取 Excel 单元格范围',
            permissionLevel: 'low',
            parameters: [
                { name: 'itemId', type: 'string', required: true, description: '工作簿 ID' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围（如 A1:C10）' },
            ],
        },
        {
            id: 'excel_write_range',
            name: 'excel_write_range',
            description: '写入 Excel 单元格范围',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: true, description: '工作簿 ID' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围' },
                { name: 'values', type: 'array', required: true, description: '数据（二维数组）' },
            ],
        },
        {
            id: 'excel_add_worksheet',
            name: 'excel_add_worksheet',
            description: '添加 Excel 工作表',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: true, description: '工作簿 ID' },
                { name: 'name', type: 'string', required: true, description: '工作表名称' },
            ],
        },
        // ==================== PowerPoint ====================
        {
            id: 'ppt_create',
            name: 'ppt_create',
            description: '创建新的 PowerPoint 演示文稿',
            permissionLevel: 'medium',
            parameters: [
                { name: 'name', type: 'string', required: true, description: '演示文稿名称' },
                { name: 'folder', type: 'string', required: false, description: '文件夹路径' },
            ],
        },
        {
            id: 'ppt_get_slides',
            name: 'ppt_get_slides',
            description: '获取 PowerPoint 幻灯片列表',
            permissionLevel: 'low',
            parameters: [
                { name: 'itemId', type: 'string', required: true, description: '演示文稿 ID' },
            ],
        },
        // ==================== 通用 ====================
        {
            id: 'list_files',
            name: 'list_files',
            description: '列出 OneDrive 文件',
            permissionLevel: 'low',
            parameters: [
                { name: 'folder', type: 'string', required: false, description: '文件夹路径' },
                { name: 'type', type: 'string', required: false, description: '文件类型过滤（word/excel/ppt）' },
            ],
        },
        {
            id: 'delete_file',
            name: 'delete_file',
            description: '删除 OneDrive 文件',
            permissionLevel: 'high',
            parameters: [
                { name: 'itemId', type: 'string', required: true, description: '文件 ID' },
            ],
        },
    ];

    private oauth: OAuthManager | null = null;
    private readonly providerId = 'microsoft';
    private readonly graphApiBase = 'https://graph.microsoft.com/v1.0';

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
                // Word
                case 'word_create':
                    return this.createDocument(token, params.name as string, 'docx', params.folder as string);
                case 'word_get_content':
                    return this.getDocumentContent(token, params.itemId as string);
                // Excel
                case 'excel_create':
                    return this.createDocument(token, params.name as string, 'xlsx', params.folder as string);
                case 'excel_read_range':
                    return this.excelReadRange(token, params.itemId as string, params.worksheet as string, params.range as string);
                case 'excel_write_range':
                    return this.excelWriteRange(token, params.itemId as string, params.worksheet as string, params.range as string, params.values as any[][]);
                case 'excel_add_worksheet':
                    return this.excelAddWorksheet(token, params.itemId as string, params.name as string);
                // PowerPoint
                case 'ppt_create':
                    return this.createDocument(token, params.name as string, 'pptx', params.folder as string);
                case 'ppt_get_slides':
                    return this.pptGetSlides(token, params.itemId as string);
                // 通用
                case 'list_files':
                    return this.listFiles(token, params.folder as string, params.type as string);
                case 'delete_file':
                    return this.deleteFile(token, params.itemId as string);
                default:
                    return this.failure('UNKNOWN_CAPABILITY', `Unknown capability: ${capability}`);
            }
        } catch (error) {
            return this.failure('API_ERROR', (error as Error).message);
        }
    }

    private async apiCall(token: string, endpoint: string, method = 'GET', body?: object): Promise<Response> {
        return fetch(`${this.graphApiBase}${endpoint}`, {
            method,
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            ...(body && { body: JSON.stringify(body) }),
        });
    }

    // ==================== 通用文件操作 ====================

    /**
     * 创建文档（Word/Excel/PowerPoint）
     */
    private async createDocument(token: string, name: string, extension: string, folder?: string): Promise<AdapterResult> {
        const fileName = name.endsWith(`.${extension}`) ? name : `${name}.${extension}`;
        const path = folder ? `/me/drive/root:/${folder}/${fileName}:/content` : `/me/drive/root:/${fileName}:/content`;

        // 创建空文件（不同类型使用不同模板）
        const templates: Record<string, string> = {
            docx: 'UEsDBBQAAAAIAA', // 简化的空 docx 占位
            xlsx: 'UEsDBBQAAAAIAA',
            pptx: 'UEsDBBQAAAAIAA',
        };

        const res = await fetch(`${this.graphApiBase}${path}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/octet-stream',
            },
            body: new Uint8Array(0), // 创建空文件
        });

        if (!res.ok) {
            return this.failure('MS365_ERROR', `API error: ${res.status}`);
        }

        const data = await res.json() as DriveItem;
        return this.success({
            id: data.id,
            name: data.name,
            webUrl: data.webUrl,
            createdDateTime: data.createdDateTime,
        });
    }

    /**
     * 获取文档内容（Word）
     */
    private async getDocumentContent(token: string, itemId: string): Promise<AdapterResult> {
        // 获取文档元数据
        const metaRes = await this.apiCall(token, `/me/drive/items/${itemId}`);
        if (!metaRes.ok) {
            return this.failure('MS365_ERROR', `API error: ${metaRes.status}`);
        }
        const meta = await metaRes.json() as DriveItem;

        // 获取内容（作为 HTML 预览）
        const previewRes = await this.apiCall(token, `/me/drive/items/${itemId}/preview`, 'POST');
        let previewUrl: string | null = null;
        if (previewRes.ok) {
            const preview = await previewRes.json() as PreviewResponse;
            previewUrl = preview.getUrl ?? null;
        }

        return this.success({
            id: meta.id,
            name: meta.name,
            size: meta.size,
            webUrl: meta.webUrl,
            previewUrl,
            lastModifiedDateTime: meta.lastModifiedDateTime,
        });
    }

    /**
     * 列出 OneDrive 文件
     */
    private async listFiles(token: string, folder?: string, type?: string): Promise<AdapterResult> {
        const path = folder ? `/me/drive/root:/${folder}:/children` : '/me/drive/root/children';
        const res = await this.apiCall(token, path);

        if (!res.ok) {
            return this.failure('MS365_ERROR', `API error: ${res.status}`);
        }

        const data = await res.json() as DriveItemsResponse;
        let files = data.value;

        // 按类型过滤
        if (type) {
            const extensions: Record<string, string[]> = {
                word: ['.doc', '.docx'],
                excel: ['.xls', '.xlsx'],
                ppt: ['.ppt', '.pptx'],
            };
            const exts = extensions[type.toLowerCase()] || [];
            files = files.filter((f) => exts.some(ext => f.name?.toLowerCase().endsWith(ext)));
        }

        return this.success({
            files: files.map((f) => ({
                id: f.id,
                name: f.name,
                size: f.size,
                webUrl: f.webUrl,
                isFolder: !!f.folder,
                lastModifiedDateTime: f.lastModifiedDateTime,
            })),
        });
    }

    /**
     * 删除文件
     */
    private async deleteFile(token: string, itemId: string): Promise<AdapterResult> {
        const res = await this.apiCall(token, `/me/drive/items/${itemId}`, 'DELETE');
        if (!res.ok && res.status !== 204) {
            return this.failure('MS365_ERROR', `API error: ${res.status}`);
        }
        return this.success({ deleted: true });
    }

    // ==================== Excel 专用 ====================

    /**
     * 读取 Excel 范围
     */
    private async excelReadRange(token: string, itemId: string, worksheet?: string, range?: string): Promise<AdapterResult> {
        const sheetName = worksheet || 'Sheet1';
        const rangeStr = range || 'A1:Z100';
        const endpoint = `/me/drive/items/${itemId}/workbook/worksheets/${sheetName}/range(address='${rangeStr}')`;

        const res = await this.apiCall(token, endpoint);
        if (!res.ok) {
            return this.failure('MS365_ERROR', `API error: ${res.status}`);
        }

        const data = await res.json() as ExcelRangeResponse;
        return this.success({
            address: data.address,
            values: data.values,
            rowCount: data.rowCount,
            columnCount: data.columnCount,
        });
    }

    /**
     * 写入 Excel 范围
     */
    private async excelWriteRange(token: string, itemId: string, worksheet?: string, range?: string, values?: unknown[][]): Promise<AdapterResult> {
        const sheetName = worksheet || 'Sheet1';
        const rangeStr = range || 'A1';
        const endpoint = `/me/drive/items/${itemId}/workbook/worksheets/${sheetName}/range(address='${rangeStr}')`;

        const res = await fetch(`${this.graphApiBase}${endpoint}`, {
            method: 'PATCH',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ values }),
        });

        if (!res.ok) {
            return this.failure('MS365_ERROR', `API error: ${res.status}`);
        }

        const data = await res.json() as ExcelRangeResponse;
        return this.success({
            address: data.address,
            rowCount: data.rowCount,
            columnCount: data.columnCount,
        });
    }

    /**
     * 添加 Excel 工作表
     */
    private async excelAddWorksheet(token: string, itemId: string, name: string): Promise<AdapterResult> {
        const endpoint = `/me/drive/items/${itemId}/workbook/worksheets/add`;
        const res = await this.apiCall(token, endpoint, 'POST', { name });

        if (!res.ok) {
            return this.failure('MS365_ERROR', `API error: ${res.status}`);
        }

        const data = await res.json() as WorksheetResponse;
        return this.success({
            id: data.id,
            name: data.name,
            position: data.position,
        });
    }

    // ==================== PowerPoint 专用 ====================

    /**
     * 获取 PowerPoint 幻灯片（注：Graph API 对 PPT 支持有限）
     */
    private async pptGetSlides(token: string, itemId: string): Promise<AdapterResult> {
        // 获取文件信息
        const res = await this.apiCall(token, `/me/drive/items/${itemId}`);
        if (!res.ok) {
            return this.failure('MS365_ERROR', `API error: ${res.status}`);
        }

        const meta = await res.json() as DriveItem;

        // 获取预览 URL
        const previewRes = await this.apiCall(token, `/me/drive/items/${itemId}/preview`, 'POST');
        let previewUrl: string | null = null;
        if (previewRes.ok) {
            const preview = await previewRes.json() as PreviewResponse;
            previewUrl = preview.getUrl ?? null;
        }

        return this.success({
            id: meta.id,
            name: meta.name,
            webUrl: meta.webUrl,
            previewUrl,
            note: 'Graph API 对 PPT 幻灯片内容的访问有限，建议使用 webUrl 在线编辑',
        });
    }
}
