import { BaseAdapter } from '../BaseAdapter.js';
import type { AdapterResult, AdapterCapability } from '@aios/shared';
import type { OAuthManager } from '../../auth/index.js';

// Outlook API 响应类型
interface OutlookErrorResponse {
    error?: { message?: string };
}

interface OutlookEmailAddress {
    address?: string;
    name?: string;
}

interface OutlookMessage {
    id: string;
    subject?: string;
    from?: { emailAddress?: OutlookEmailAddress };
    toRecipients?: Array<{ emailAddress?: OutlookEmailAddress }>;
    receivedDateTime?: string;
    isRead?: boolean;
    bodyPreview?: string;
    body?: { content?: string; contentType?: string };
}

interface OutlookMessagesResponse {
    value: OutlookMessage[];
}

/**
 * Outlook 邮件适配器
 * 使用 Microsoft Graph API 实现邮件管理
 */
export class OutlookAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.outlook';
    readonly name = 'Outlook';
    readonly description = 'Microsoft Outlook 邮件管理';
    readonly capabilities: AdapterCapability[] = [
        {
            id: 'send_email',
            name: 'send_email',
            description: '发送 Outlook 邮件',
            permissionLevel: 'high',
            parameters: [
                { name: 'to', type: 'string', required: true, description: '收件人邮箱' },
                { name: 'subject', type: 'string', required: true, description: '邮件主题' },
                { name: 'body', type: 'string', required: true, description: '邮件正文' },
                { name: 'isHtml', type: 'boolean', required: false, description: '是否为 HTML 格式' },
            ],
        },
        {
            id: 'list_messages',
            name: 'list_messages',
            description: '获取 Outlook 邮件列表',
            permissionLevel: 'low',
            parameters: [
                { name: 'folder', type: 'string', required: false, description: '文件夹（inbox/sent/drafts）' },
                { name: 'top', type: 'number', required: false, description: '返回数量限制' },
            ],
        },
        {
            id: 'get_message',
            name: 'get_message',
            description: '获取 Outlook 邮件详情',
            permissionLevel: 'low',
            parameters: [
                { name: 'id', type: 'string', required: true, description: '邮件 ID' },
            ],
        },
        {
            id: 'reply_email',
            name: 'reply_email',
            description: '回复 Outlook 邮件',
            permissionLevel: 'medium',
            parameters: [
                { name: 'id', type: 'string', required: true, description: '原邮件 ID' },
                { name: 'body', type: 'string', required: true, description: '回复内容' },
            ],
        },
        {
            id: 'delete_message',
            name: 'delete_message',
            description: '删除 Outlook 邮件',
            permissionLevel: 'high',
            parameters: [
                { name: 'id', type: 'string', required: true, description: '邮件 ID' },
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
                case 'send_email':
                    return this.sendEmail(token, params.to as string, params.subject as string, params.body as string, params.isHtml as boolean);
                case 'list_messages':
                    return this.listMessages(token, params.folder as string, params.top as number);
                case 'get_message':
                    return this.getMessage(token, params.id as string);
                case 'reply_email':
                    return this.replyEmail(token, params.id as string, params.body as string);
                case 'delete_message':
                    return this.deleteMessage(token, params.id as string);
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

    /**
     * 发送邮件
     */
    private async sendEmail(token: string, to: string, subject: string, body: string, isHtml = false): Promise<AdapterResult> {
        const message = {
            message: {
                subject,
                body: {
                    contentType: isHtml ? 'HTML' : 'Text',
                    content: body,
                },
                toRecipients: [
                    {
                        emailAddress: { address: to },
                    },
                ],
            },
            saveToSentItems: true,
        };

        const res = await this.apiCall(token, '/me/sendMail', 'POST', message);
        if (!res.ok) {
            const errorData = await res.json().catch(() => ({})) as OutlookErrorResponse;
            return this.failure('OUTLOOK_ERROR', `API error: ${res.status} - ${errorData.error?.message ?? 'Unknown'}`);
        }
        return this.success({ sent: true });
    }

    /**
     * 获取邮件列表
     */
    private async listMessages(token: string, folder = 'inbox', top = 10): Promise<AdapterResult> {
        const folderPath = folder === 'inbox' ? 'inbox' : `mailFolders/${folder}`;
        const endpoint = `/me/${folderPath}/messages?$top=${top}&$select=id,subject,from,receivedDateTime,isRead,bodyPreview`;

        const res = await this.apiCall(token, endpoint);
        if (!res.ok) {
            return this.failure('OUTLOOK_ERROR', `API error: ${res.status}`);
        }

        const data = await res.json() as OutlookMessagesResponse;
        return this.success({
            messages: data.value.map((m) => ({
                id: m.id,
                subject: m.subject,
                from: m.from?.emailAddress?.address,
                fromName: m.from?.emailAddress?.name,
                receivedDateTime: m.receivedDateTime,
                isRead: m.isRead,
                preview: m.bodyPreview,
            })),
        });
    }

    /**
     * 获取邮件详情
     */
    private async getMessage(token: string, id: string): Promise<AdapterResult> {
        const res = await this.apiCall(token, `/me/messages/${id}`);
        if (!res.ok) {
            return this.failure('OUTLOOK_ERROR', `API error: ${res.status}`);
        }

        const m = await res.json() as OutlookMessage;
        return this.success({
            id: m.id,
            subject: m.subject,
            from: m.from?.emailAddress?.address,
            fromName: m.from?.emailAddress?.name,
            to: m.toRecipients?.map((r) => r.emailAddress?.address),
            receivedDateTime: m.receivedDateTime,
            isRead: m.isRead,
            body: m.body?.content,
            bodyType: m.body?.contentType,
        });
    }

    /**
     * 回复邮件
     */
    private async replyEmail(token: string, messageId: string, body: string): Promise<AdapterResult> {
        const reply = {
            message: {
                body: {
                    contentType: 'Text',
                    content: body,
                },
            },
        };

        const res = await this.apiCall(token, `/me/messages/${messageId}/reply`, 'POST', reply);
        if (!res.ok) {
            return this.failure('OUTLOOK_ERROR', `API error: ${res.status}`);
        }
        return this.success({ replied: true });
    }

    /**
     * 删除邮件
     */
    private async deleteMessage(token: string, id: string): Promise<AdapterResult> {
        const res = await this.apiCall(token, `/me/messages/${id}`, 'DELETE');
        if (!res.ok && res.status !== 204) {
            return this.failure('OUTLOOK_ERROR', `API error: ${res.status}`);
        }
        return this.success({ deleted: true });
    }
}
