import { BaseAdapter } from '../BaseAdapter.js';
import type { AdapterCapability, AdapterResult } from '@aios/shared';

// Slack API 响应类型定义（按照 typescript skill 要求）
interface SlackApiResponse {
    ok: boolean;
    error?: string;
}

interface SlackPostMessageResponse extends SlackApiResponse {
    ts?: string;
    channel?: string;
}

interface SlackMessage {
    ts: string;
    text: string;
    user: string;
    type: string;
}

interface SlackMessagesResponse extends SlackApiResponse {
    messages?: SlackMessage[];
}

interface SlackChannel {
    id: string;
    name: string;
}

interface SlackChannelsResponse extends SlackApiResponse {
    channels?: SlackChannel[];
}

interface SlackUser {
    id: string;
    name: string;
    real_name?: string;
    is_bot?: boolean;
}

interface SlackUsersResponse extends SlackApiResponse {
    members?: SlackUser[];
}

export class SlackAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.slack';
    readonly name = 'Slack';
    readonly description = 'Slack 消息适配器';
    readonly capabilities: AdapterCapability[] = [
        {
            id: 'send_message',
            name: 'send_message',
            description: '发送 Slack 消息到指定频道',
            permissionLevel: 'medium',
            parameters: [
                { name: 'channel', type: 'string', required: true, description: '频道 ID 或名称' },
                { name: 'text', type: 'string', required: true, description: '消息内容' },
            ],
        },
        {
            id: 'get_messages',
            name: 'get_messages',
            description: '读取 Slack 频道消息历史',
            permissionLevel: 'medium',
            parameters: [
                { name: 'channel', type: 'string', required: true, description: '频道 ID' },
                { name: 'limit', type: 'number', required: false, description: '消息数量限制' },
            ],
        },
        {
            id: 'list_channels',
            name: 'list_channels',
            description: '获取 Slack 频道列表',
            permissionLevel: 'low',
        },
        {
            id: 'get_users',
            name: 'get_users',
            description: '获取 Slack 用户列表',
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

    async initialize(): Promise<void> {
        // No-op, uses setToken for configuration
    }

    async shutdown(): Promise<void> {
        this.token = null;
    }

    async invoke(capability: string, params: Record<string, unknown>): Promise<AdapterResult> {
        if (!this.token) {
            return this.failure('NO_TOKEN', 'Slack token not configured');
        }

        switch (capability) {
            case 'send_message':
                return this.sendMessage(params.channel as string, params.text as string);
            case 'get_messages':
                return this.getMessages(params.channel as string, params.limit as number | undefined);
            case 'list_channels':
                return this.listChannels();
            case 'get_users':
                return this.getUserList();
            default:
                return this.failure('UNKNOWN_CAPABILITY', `Unknown capability: ${capability}`);
        }
    }

    private async sendMessage(channel: string, text: string): Promise<AdapterResult> {
        const response = await fetch('https://slack.com/api/chat.postMessage', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ channel, text }),
        });
        const data = await response.json() as SlackPostMessageResponse;
        return data.ok
            ? this.success({ ts: data.ts, channel: data.channel })
            : this.failure('SLACK_ERROR', data.error ?? '未知错误');
    }

    private async getMessages(channel: string, limit?: number): Promise<AdapterResult> {
        const url = new URL('https://slack.com/api/conversations.history');
        url.searchParams.set('channel', channel);
        if (limit) url.searchParams.set('limit', String(limit));

        const response = await fetch(url.toString(), {
            headers: { 'Authorization': `Bearer ${this.token}` },
        });
        const data = await response.json() as SlackMessagesResponse;
        return data.ok
            ? this.success({
                messages: (data.messages ?? []).map((m) => ({
                    ts: m.ts,
                    text: m.text,
                    user: m.user,
                    type: m.type,
                })),
            })
            : this.failure('SLACK_ERROR', data.error ?? '未知错误');
    }

    private async listChannels(): Promise<AdapterResult> {
        const response = await fetch('https://slack.com/api/conversations.list', {
            headers: { 'Authorization': `Bearer ${this.token}` },
        });
        const data = await response.json() as SlackChannelsResponse;
        return data.ok
            ? this.success({ channels: (data.channels ?? []).map((c) => ({ id: c.id, name: c.name })) })
            : this.failure('SLACK_ERROR', data.error ?? '未知错误');
    }

    private async getUserList(): Promise<AdapterResult> {
        const response = await fetch('https://slack.com/api/users.list', {
            headers: { 'Authorization': `Bearer ${this.token}` },
        });
        const data = await response.json() as SlackUsersResponse;
        return data.ok
            ? this.success({
                users: (data.members ?? []).map((u) => ({
                    id: u.id,
                    name: u.name,
                    real_name: u.real_name,
                    is_bot: u.is_bot,
                })),
            })
            : this.failure('SLACK_ERROR', data.error ?? '未知错误');
    }
}
