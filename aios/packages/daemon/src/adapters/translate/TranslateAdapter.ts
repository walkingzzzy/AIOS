/**
 * 翻译适配器
 * 使用 Google Translate API 进行多语言翻译
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// 语言代码映射
const LANGUAGE_CODES: Record<string, string> = {
    'zh': '中文',
    'en': '英语',
    'ja': '日语',
    'ko': '韩语',
    'fr': '法语',
    'de': '德语',
    'es': '西班牙语',
    'ru': '俄语',
    'pt': '葡萄牙语',
    'it': '意大利语',
};

export class TranslateAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.translate';
    readonly name = '翻译';
    readonly description = '多语言翻译适配器';

    private apiKey = '';
    private baseUrl = 'https://translation.googleapis.com/language/translate/v2';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'translate',
            name: '翻译文本',
            description: '将文本翻译为目标语言',
            permissionLevel: 'public',
            parameters: [
                { name: 'text', type: 'string', required: true, description: '要翻译的文本' },
                { name: 'targetLang', type: 'string', required: true, description: '目标语言代码 (zh/en/ja等)' },
                { name: 'sourceLang', type: 'string', required: false, description: '源语言代码 (自动检测)' },
            ],
        },
        {
            id: 'detect_language',
            name: '检测语言',
            description: '检测文本的语言',
            permissionLevel: 'public',
            parameters: [
                { name: 'text', type: 'string', required: true, description: '要检测的文本' },
            ],
        },
        {
            id: 'get_languages',
            name: '获取支持的语言',
            description: '获取支持的语言列表',
            permissionLevel: 'public',
        },
        {
            id: 'set_api_key',
            name: '设置 API Key',
            description: '配置 Google Translate API Key',
            permissionLevel: 'medium',
            parameters: [
                { name: 'apiKey', type: 'string', required: true, description: 'API Key' },
            ],
        },
    ];

    async checkAvailability(): Promise<boolean> {
        return true;
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'translate':
                    return this.translate(
                        args.text as string,
                        args.targetLang as string,
                        args.sourceLang as string | undefined
                    );
                case 'detect_language':
                    return this.detectLanguage(args.text as string);
                case 'get_languages':
                    return this.getLanguages();
                case 'set_api_key':
                    return this.setApiKey(args.apiKey as string);
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private ensureApiKey(): string | null {
        if (!this.apiKey) {
            this.apiKey = process.env.GOOGLE_TRANSLATE_API_KEY || '';
        }
        return this.apiKey || null;
    }

    private async translate(text: string, targetLang: string, sourceLang?: string): Promise<AdapterResult> {
        if (!text) {
            return this.failure('INVALID_ARGS', '文本不能为空');
        }

        if (!targetLang) {
            return this.failure('INVALID_ARGS', '目标语言是必需的');
        }

        const apiKey = this.ensureApiKey();
        if (!apiKey) {
            return this.failure('API_KEY_MISSING', '请先配置 Google Translate API Key');
        }

        try {
            const source = sourceLang || 'auto';
            const url = `${this.baseUrl}?key=${encodeURIComponent(apiKey)}`;
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    q: text,
                    source,
                    target: targetLang,
                    format: 'text',
                }),
            });

            if (!response.ok) {
                return this.failure('TRANSLATE_ERROR', `API 错误: ${response.status}`);
            }

            const data = await response.json() as { data?: { translations?: Array<{ translatedText?: string; detectedSourceLanguage?: string }> } };
            const translation = data.data?.translations?.[0];
            if (!translation?.translatedText) {
                return this.failure('TRANSLATE_ERROR', '翻译结果为空');
            }

            return this.success({
                originalText: text,
                translatedText: translation.translatedText,
                sourceLang: translation.detectedSourceLanguage || source,
                targetLang,
            });
        } catch (error) {
            return this.failure('NETWORK_ERROR', `网络错误: ${String(error)}`);
        }
    }

    private async detectLanguage(text: string): Promise<AdapterResult> {
        if (!text) {
            return this.failure('INVALID_ARGS', '文本不能为空');
        }

        const apiKey = this.ensureApiKey();
        if (!apiKey) {
            return this.failure('API_KEY_MISSING', '请先配置 Google Translate API Key');
        }

        try {
            const url = `${this.baseUrl}/detect?key=${encodeURIComponent(apiKey)}`;
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ q: text }),
            });

            if (!response.ok) {
                return this.failure('TRANSLATE_ERROR', `API 错误: ${response.status}`);
            }

            const data = await response.json() as {
                data?: { detections?: Array<Array<{ language: string; confidence?: number }>> };
            };

            const detection = data.data?.detections?.[0]?.[0];
            if (!detection?.language) {
                return this.failure('TRANSLATE_ERROR', '语言检测结果为空');
            }

            return this.success({
                text: text.length > 50 ? `${text.substring(0, 50)}...` : text,
                language: detection.language,
                languageName: LANGUAGE_CODES[detection.language] || detection.language,
                confidence: detection.confidence ?? null,
            });
        } catch (error) {
            return this.failure('NETWORK_ERROR', `网络错误: ${String(error)}`);
        }
    }

    private async getLanguages(): Promise<AdapterResult> {
        const apiKey = this.ensureApiKey();
        if (!apiKey) {
            return this.failure('API_KEY_MISSING', '请先配置 Google Translate API Key');
        }

        try {
            const url = `${this.baseUrl}/languages?key=${encodeURIComponent(apiKey)}&target=zh-CN`;
            const response = await fetch(url);
            if (!response.ok) {
                return this.failure('TRANSLATE_ERROR', `API 错误: ${response.status}`);
            }

            const data = await response.json() as { data?: { languages?: Array<{ language: string; name?: string }> } };
            const languages = (data.data?.languages ?? []).map((lang) => ({
                code: lang.language,
                name: lang.name || LANGUAGE_CODES[lang.language] || lang.language,
            }));

            return this.success({ languages });
        } catch (error) {
            return this.failure('NETWORK_ERROR', `网络错误: ${String(error)}`);
        }
    }

    private setApiKey(apiKey: string): AdapterResult {
        if (!apiKey) {
            return this.failure('INVALID_ARGS', 'API Key 不能为空');
        }

        this.apiKey = apiKey;
        return this.success({ configured: true });
    }
}

export const translateAdapter = new TranslateAdapter();
