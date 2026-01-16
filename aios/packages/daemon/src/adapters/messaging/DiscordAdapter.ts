import { BaseAdapter } from '../BaseAdapter.js';
import type { AdapterCapability, AdapterResult } from '@aios/shared';

// Discord API 响应类型定义（按照 typescript skill 要求）
interface DiscordMessage {
    id: string;
    channel_id: string;
}

interface DiscordGuild {
    id: string;
    name: string;
}

export class DiscordAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.discord';
    readonly name = 'Discord';
    readonly description = 'Discord 消息适配器';
    readonly capabilities: AdapterCapability[] = [
        {
            id: 'send_message',
            name: 'send_message',
            description: '发送 Discord 消息到指定频道',
            permissionLevel: 'medium',
            parameters: [
                { name: 'channelId', type: 'string', required: true, description: '频道 ID' },
                { name: 'content', type: 'string', required: true, description: '消息内容' },
            ],
        },
        {
            id: 'list_guilds',
            name: 'list_guilds',
            description: '获取 Discord 服务器列表',
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
            return this.failure('NO_TOKEN', 'Discord token not configured');
        }

        switch (capability) {
            case 'send_message':
                return this.sendMessage(params.channelId as string, params.content as string);
            case 'list_guilds':
                return this.listGuilds();
            default:
                return this.failure('UNKNOWN_CAPABILITY', `Unknown capability: ${capability}`);
        }
    }

    private async sendMessage(channelId: string, content: string): Promise<AdapterResult> {
        const response = await fetch(`https://discord.com/api/v10/channels/${channelId}/messages`, {
            method: 'POST',
            headers: {
                'Authorization': `Bot ${this.token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ content }),
        });
        if (!response.ok) {
            return this.failure('DISCORD_ERROR', `Discord API error: ${response.status}`);
        }
        const data = await response.json() as DiscordMessage;
        return this.success({ id: data.id, channelId: data.channel_id });
    }

    private async listGuilds(): Promise<AdapterResult> {
        const response = await fetch('https://discord.com/api/v10/users/@me/guilds', {
            headers: { 'Authorization': `Bot ${this.token}` },
        });
        if (!response.ok) {
            return this.failure('DISCORD_ERROR', `Discord API error: ${response.status}`);
        }
        const data = await response.json() as DiscordGuild[];
        return this.success({ guilds: data.map((g) => ({ id: g.id, name: g.name })) });
    }
}
