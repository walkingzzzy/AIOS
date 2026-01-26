/**
 * OAuth 提供商配置
 * 定义各服务的 OAuth 授权端点
 */

import type { OAuthConfig } from './OAuthManager.js';

/**
 * 预定义的 OAuth 提供商配置
 */
export const OAuthProviders: Record<string, Omit<OAuthConfig, 'clientId' | 'clientSecret'>> = {
    // Google (Gmail, Docs, Sheets)
    google: {
        authUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
        tokenUrl: 'https://oauth2.googleapis.com/token',
        scopes: [
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/calendar',
        ],
    },

    // Microsoft (Outlook, OneDrive, Office 365)
    microsoft: {
        authUrl: 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
        tokenUrl: 'https://login.microsoftonline.com/common/oauth2/v2.0/token',
        scopes: [
            'https://graph.microsoft.com/Mail.Send',
            'https://graph.microsoft.com/Mail.Read',
            'https://graph.microsoft.com/Files.ReadWrite',
            'https://graph.microsoft.com/User.Read',
            'offline_access',
        ],
    },

    // Spotify
    spotify: {
        authUrl: 'https://accounts.spotify.com/authorize',
        tokenUrl: 'https://accounts.spotify.com/api/token',
        scopes: [
            'user-read-playback-state',
            'user-modify-playback-state',
            'user-read-currently-playing',
            'streaming',
            'playlist-read-private',
        ],
    },

    // Notion
    notion: {
        authUrl: 'https://api.notion.com/v1/oauth/authorize',
        tokenUrl: 'https://api.notion.com/v1/oauth/token',
        scopes: [], // Notion 使用单一权限
    },
};

/**
 * 获取提供商的完整 OAuth 配置
 * @param providerId 提供商 ID
 * @param clientId 客户端 ID
 * @param clientSecret 客户端密钥
 * @param redirectUri 重定向 URI（可选）
 */
export function getOAuthConfig(
    providerId: string,
    clientId: string,
    clientSecret: string,
    redirectUri?: string
): OAuthConfig {
    const baseConfig = OAuthProviders[providerId];
    if (!baseConfig) {
        throw new Error(`Unknown OAuth provider: ${providerId}`);
    }

    return {
        ...baseConfig,
        clientId,
        clientSecret,
        redirectUri: redirectUri || 'http://localhost:3000/oauth/callback',
    };
}

/**
 * 环境变量名称映射
 */
export const OAuthEnvVars: Record<string, { clientId: string; clientSecret: string }> = {
    google: {
        clientId: 'GOOGLE_CLIENT_ID',
        clientSecret: 'GOOGLE_CLIENT_SECRET',
    },
    microsoft: {
        clientId: 'MICROSOFT_CLIENT_ID',
        clientSecret: 'MICROSOFT_CLIENT_SECRET',
    },
    spotify: {
        clientId: 'SPOTIFY_CLIENT_ID',
        clientSecret: 'SPOTIFY_CLIENT_SECRET',
    },
    notion: {
        clientId: 'NOTION_CLIENT_ID',
        clientSecret: 'NOTION_CLIENT_SECRET',
    },
};

/**
 * Token 类型配置（用于直接使用 API Token 的服务）
 */
export const TokenBasedServices: Record<string, { envVar: string; description: string }> = {
    slack: {
        envVar: 'SLACK_BOT_TOKEN',
        description: 'Slack Bot User OAuth Token (xoxb-...)',
    },
    discord: {
        envVar: 'DISCORD_BOT_TOKEN',
        description: 'Discord Bot Token',
    },
};
