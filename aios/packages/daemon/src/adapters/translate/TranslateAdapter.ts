/**
 * 翻译适配器
 * 使用免费翻译API进行多语言翻译
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
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async translate(text: string, targetLang: string, sourceLang?: string): Promise<AdapterResult> {
        if (!text) {
            return this.failure('INVALID_ARGS', '文本不能为空');
        }

        if (!targetLang) {
            return this.failure('INVALID_ARGS', '目标语言是必需的');
        }

        try {
            // 使用 LibreTranslate 免费API (或可配置其他API)
            const source = sourceLang || 'auto';
            const url = 'https://libretranslate.com/translate';

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    q: text,
                    source: source,
                    target: targetLang,
                }),
            });

            if (response.ok) {
                const data = await response.json() as { translatedText: string };
                return this.success({
                    originalText: text,
                    translatedText: data.translatedText,
                    sourceLang: source,
                    targetLang,
                });
            }

            // 如果外部API失败，使用简单的回退逻辑
            return this.fallbackTranslate(text, targetLang);
        } catch {
            // 网络错误时使用回退
            return this.fallbackTranslate(text, targetLang);
        }
    }

    private fallbackTranslate(text: string, targetLang: string): AdapterResult {
        // 简单的回退：返回原文并提示需要API
        return this.success({
            originalText: text,
            translatedText: text,
            targetLang,
            warning: '翻译API不可用，返回原文。建议配置翻译服务。',
        });
    }

    private detectLanguage(text: string): AdapterResult {
        if (!text) {
            return this.failure('INVALID_ARGS', '文本不能为空');
        }

        // 简单的语言检测（基于字符范围）
        const hasChineseChar = /[\u4e00-\u9fff]/.test(text);
        const hasJapaneseChar = /[\u3040-\u309f\u30a0-\u30ff]/.test(text);
        const hasKoreanChar = /[\uac00-\ud7af]/.test(text);
        const hasCyrillic = /[\u0400-\u04ff]/.test(text);

        let detectedLang = 'en'; // 默认英语
        let confidence = 0.5;

        if (hasChineseChar && !hasJapaneseChar) {
            detectedLang = 'zh';
            confidence = 0.9;
        } else if (hasJapaneseChar) {
            detectedLang = 'ja';
            confidence = 0.9;
        } else if (hasKoreanChar) {
            detectedLang = 'ko';
            confidence = 0.9;
        } else if (hasCyrillic) {
            detectedLang = 'ru';
            confidence = 0.8;
        } else if (/^[a-zA-Z\s.,!?'"()-]+$/.test(text)) {
            detectedLang = 'en';
            confidence = 0.7;
        }

        return this.success({
            text: text.substring(0, 50) + (text.length > 50 ? '...' : ''),
            language: detectedLang,
            languageName: LANGUAGE_CODES[detectedLang] || detectedLang,
            confidence,
        });
    }

    private getLanguages(): AdapterResult {
        const languages = Object.entries(LANGUAGE_CODES).map(([code, name]) => ({
            code,
            name,
        }));

        return this.success({ languages });
    }
}

export const translateAdapter = new TranslateAdapter();
