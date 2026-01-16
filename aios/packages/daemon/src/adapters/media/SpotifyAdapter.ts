import { BaseAdapter } from '../BaseAdapter.js';
import type { AdapterResult, AdapterCapability } from '@aios/shared';
import type { OAuthManager } from '../../auth/index.js';

// Spotify API 响应类型
interface SpotifySearchResponse {
    tracks?: { items: unknown[] };
    albums?: { items: unknown[] };
    artists?: { items: unknown[] };
}

interface SpotifyPlaybackState {
    is_playing: boolean;
    item?: unknown;
}

export class SpotifyAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.spotify';
    readonly name = 'Spotify';
    readonly description = 'Spotify 音乐播放控制';
    readonly capabilities: AdapterCapability[] = [
        { id: 'play', name: 'play', description: '播放音乐', permissionLevel: 'low', parameters: [{ name: 'uri', type: 'string', required: false, description: 'Spotify URI' }] },
        { id: 'pause', name: 'pause', description: '暂停播放', permissionLevel: 'low' },
        { id: 'next', name: 'next', description: '下一首', permissionLevel: 'low' },
        { id: 'previous', name: 'previous', description: '上一首', permissionLevel: 'low' },
        { id: 'search', name: 'search', description: '搜索音乐', permissionLevel: 'public', parameters: [{ name: 'query', type: 'string', required: true, description: '搜索关键词' }, { name: 'type', type: 'string', required: false, description: '类型: track/album/artist' }] },
        { id: 'get_current', name: 'get_current', description: '获取当前播放信息', permissionLevel: 'public' },
    ];

    private oauth: OAuthManager | null = null;
    private readonly providerId = 'spotify';

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
                case 'play': return this.play(token, params.uri as string | undefined);
                case 'pause': return this.pause(token);
                case 'next': return this.next(token);
                case 'previous': return this.previous(token);
                case 'search': return this.search(token, params.query as string, params.type as string);
                case 'get_current': return this.getCurrent(token);
                default: return this.failure('UNKNOWN_CAPABILITY', `Unknown capability: ${capability}`);
            }
        } catch (error) {
            return this.failure('API_ERROR', (error as Error).message);
        }
    }

    private async apiCall(token: string, endpoint: string, method = 'GET', body?: object): Promise<Response> {
        return fetch(`https://api.spotify.com/v1${endpoint}`, {
            method,
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            ...(body && { body: JSON.stringify(body) }),
        });
    }

    private async play(token: string, uri?: string): Promise<AdapterResult> {
        const res = await this.apiCall(token, '/me/player/play', 'PUT', uri ? { uris: [uri] } : undefined);
        return res.ok ? this.success({}) : this.failure('SPOTIFY_ERROR', `API error: ${res.status}`);
    }

    private async pause(token: string): Promise<AdapterResult> {
        const res = await this.apiCall(token, '/me/player/pause', 'PUT');
        return res.ok ? this.success({}) : this.failure('SPOTIFY_ERROR', `API error: ${res.status}`);
    }

    private async next(token: string): Promise<AdapterResult> {
        const res = await this.apiCall(token, '/me/player/next', 'POST');
        return res.ok ? this.success({}) : this.failure('SPOTIFY_ERROR', `API error: ${res.status}`);
    }

    private async previous(token: string): Promise<AdapterResult> {
        const res = await this.apiCall(token, '/me/player/previous', 'POST');
        return res.ok ? this.success({}) : this.failure('SPOTIFY_ERROR', `API error: ${res.status}`);
    }

    private async search(token: string, query: string, type = 'track'): Promise<AdapterResult> {
        const res = await this.apiCall(token, `/search?q=${encodeURIComponent(query)}&type=${type}&limit=10`);
        if (!res.ok) return this.failure('SPOTIFY_ERROR', `API error: ${res.status}`);
        const data = await res.json() as Record<string, unknown>;
        return this.success(data);
    }

    private async getCurrent(token: string): Promise<AdapterResult> {
        const res = await this.apiCall(token, '/me/player/currently-playing');
        if (res.status === 204) return this.success({ playing: false });
        if (!res.ok) return this.failure('SPOTIFY_ERROR', `API error: ${res.status}`);
        const data = await res.json() as Record<string, unknown>;
        return this.success(data);
    }
}
