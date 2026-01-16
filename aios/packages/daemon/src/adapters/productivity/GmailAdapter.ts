import { BaseAdapter } from '../BaseAdapter.js';
import type { AdapterResult, AdapterCapability } from '@aios/shared';
import type { OAuthManager } from '../../auth/index.js';

// Gmail API 响应类型定义（按照 typescript skill 要求）
interface GmailSendResponse {
    id: string;
}

interface GmailMessage {
    id: string;
    threadId?: string;
}

interface GmailListResponse {
    messages?: GmailMessage[];
}

export class GmailAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.gmail';
    readonly name = 'Gmail';
    readonly description = 'Gmail 邮件管理';
    readonly capabilities: AdapterCapability[] = [
        { id: 'send_email', name: 'send_email', description: '发送邮件', permissionLevel: 'high', parameters: [{ name: 'to', type: 'string', required: true, description: '收件人' }, { name: 'subject', type: 'string', required: true, description: '主题' }, { name: 'body', type: 'string', required: true, description: '正文' }] },
        { id: 'list_messages', name: 'list_messages', description: '获取邮件列表', permissionLevel: 'low', parameters: [{ name: 'maxResults', type: 'number', required: false, description: '最大数量' }, { name: 'query', type: 'string', required: false, description: '搜索条件' }] },
        { id: 'get_message', name: 'get_message', description: '获取邮件详情', permissionLevel: 'low', parameters: [{ name: 'id', type: 'string', required: true, description: '邮件 ID' }] },
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
                case 'send_email': return this.sendEmail(token, params.to as string, params.subject as string, params.body as string);
                case 'list_messages': return this.listMessages(token, params.maxResults as number, params.query as string);
                case 'get_message': return this.getMessage(token, params.id as string);
                default: return this.failure('UNKNOWN_CAPABILITY', `Unknown capability: ${capability}`);
            }
        } catch (error) {
            return this.failure('API_ERROR', (error as Error).message);
        }
    }

    private async apiCall(token: string, endpoint: string, method = 'GET', body?: object): Promise<Response> {
        return fetch(`https://gmail.googleapis.com/gmail/v1/users/me${endpoint}`, {
            method,
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            ...(body && { body: JSON.stringify(body) }),
        });
    }

    private async sendEmail(token: string, to: string, subject: string, body: string): Promise<AdapterResult> {
        const raw = btoa(`To: ${to}\r\nSubject: ${subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n${body}`)
            .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
        const res = await this.apiCall(token, '/messages/send', 'POST', { raw });
        if (!res.ok) return this.failure('GMAIL_ERROR', `API error: ${res.status}`);
        const data = await res.json() as GmailSendResponse;
        return this.success({ id: data.id });
    }

    private async listMessages(token: string, maxResults = 10, query?: string): Promise<AdapterResult> {
        const params = new URLSearchParams({ maxResults: String(maxResults) });
        if (query) params.set('q', query);
        const res = await this.apiCall(token, `/messages?${params}`);
        if (!res.ok) return this.failure('GMAIL_ERROR', `API error: ${res.status}`);
        const data = await res.json() as GmailListResponse;
        return this.success({ messages: data.messages ?? [] });
    }

    private async getMessage(token: string, id: string): Promise<AdapterResult> {
        const res = await this.apiCall(token, `/messages/${id}`);
        if (!res.ok) return this.failure('GMAIL_ERROR', `API error: ${res.status}`);
        const data = await res.json() as GmailMessage;
        return this.success({ message: data });
    }
}
