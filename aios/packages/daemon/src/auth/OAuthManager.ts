import { Storage } from '../core/Storage.js';

export interface OAuthConfig {
    clientId: string;
    clientSecret: string;
    authUrl: string;
    tokenUrl: string;
    scopes: string[];
    redirectUri?: string;
}

export interface OAuthToken {
    accessToken: string;
    refreshToken?: string;
    expiresAt: number;
    tokenType: string;
    scope?: string;
}

// OAuth Token 响应类型
interface OAuthTokenResponse {
    access_token: string;
    refresh_token?: string;
    expires_in?: number | string;
    token_type?: string;
    scope?: string;
}

export class OAuthManager {
    private storage: Storage;
    private configs: Map<string, OAuthConfig> = new Map();

    constructor(storage: Storage) {
        this.storage = storage;
    }

    registerProvider(providerId: string, config: OAuthConfig): void {
        this.configs.set(providerId, config);
    }

    getAuthUrl(providerId: string, state?: string): string {
        const config = this.configs.get(providerId);
        if (!config) throw new Error(`Provider ${providerId} not registered`);

        const params = new URLSearchParams({
            client_id: config.clientId,
            redirect_uri: config.redirectUri || 'http://localhost:3000/oauth/callback',
            response_type: 'code',
            scope: config.scopes.join(' '),
            ...(state && { state }),
        });

        return `${config.authUrl}?${params.toString()}`;
    }

    async exchangeCode(providerId: string, code: string): Promise<OAuthToken> {
        const config = this.configs.get(providerId);
        if (!config) throw new Error(`Provider ${providerId} not registered`);

        const response = await fetch(config.tokenUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({
                client_id: config.clientId,
                client_secret: config.clientSecret,
                code,
                grant_type: 'authorization_code',
                redirect_uri: config.redirectUri || 'http://localhost:3000/oauth/callback',
            }),
        });

        const data = await this.parseTokenResponse(response, 'OAuth token exchange');
        const token: OAuthToken = {
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            expiresAt: Date.now() + (this.normalizeExpiresIn(data.expires_in) * 1000),
            tokenType: data.token_type ?? 'Bearer',
            scope: data.scope,
        };

        this.saveToken(providerId, token);
        return token;
    }

    async refreshToken(providerId: string): Promise<OAuthToken> {
        const config = this.configs.get(providerId);
        if (!config) throw new Error(`Provider ${providerId} not registered`);

        const currentToken = this.getToken(providerId);
        if (!currentToken?.refreshToken) {
            throw new Error('No refresh token available');
        }

        const response = await fetch(config.tokenUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({
                client_id: config.clientId,
                client_secret: config.clientSecret,
                refresh_token: currentToken.refreshToken,
                grant_type: 'refresh_token',
            }),
        });

        const data = await this.parseTokenResponse(response, 'OAuth token refresh');
        const token: OAuthToken = {
            accessToken: data.access_token,
            refreshToken: data.refresh_token ?? currentToken.refreshToken,
            expiresAt: Date.now() + (this.normalizeExpiresIn(data.expires_in) * 1000),
            tokenType: data.token_type ?? 'Bearer',
            scope: data.scope,
        };

        this.saveToken(providerId, token);
        return token;
    }

    async getAccessToken(providerId: string): Promise<string> {
        let token = this.getToken(providerId);
        if (!token) throw new Error(`No token for provider ${providerId}`);

        if (token.expiresAt - Date.now() < 5 * 60 * 1000 && token.refreshToken) {
            token = await this.refreshToken(providerId);
        }

        return token.accessToken;
    }

    isAuthenticated(providerId: string): boolean {
        const token = this.getToken(providerId);
        return !!token && token.expiresAt > Date.now();
    }

    private saveToken(providerId: string, token: OAuthToken): void {
        this.storage.setJSON(`oauth_token_${providerId}`, token);
    }

    getToken(providerId: string): OAuthToken | null {
        return this.storage.getJSON<OAuthToken>(`oauth_token_${providerId}`);
    }

    revokeToken(providerId: string): void {
        this.storage.delete(`oauth_token_${providerId}`);
    }

    private async parseTokenResponse(response: Response, context: string): Promise<OAuthTokenResponse> {
        if (!response.ok) {
            const text = await response.text().catch(() => '');
            const message = text ? `${text}` : response.statusText;
            throw new Error(`${context} failed (${response.status}): ${message}`);
        }

        let data: OAuthTokenResponse;
        try {
            data = await response.json() as OAuthTokenResponse;
        } catch (error) {
            throw new Error(`${context} returned invalid JSON`);
        }

        if (!data.access_token) {
            throw new Error(`${context} missing access_token`);
        }

        return data;
    }

    private normalizeExpiresIn(expiresIn?: number | string): number {
        const parsed = typeof expiresIn === 'number' ? expiresIn : Number(expiresIn);
        if (Number.isFinite(parsed) && parsed > 0) {
            return parsed;
        }
        // Fallback for providers that return non-expiring tokens.
        return 365 * 24 * 60 * 60;
    }
}
