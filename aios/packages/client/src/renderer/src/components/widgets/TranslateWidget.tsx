/**
 * TranslateWidget - 翻译小部件
 */

import React, { useState, useCallback } from 'react';
import { api } from '../../utils/api';

const LANGUAGES = [
    { code: 'zh', name: '中文' },
    { code: 'en', name: '英语' },
    { code: 'ja', name: '日语' },
    { code: 'ko', name: '韩语' },
    { code: 'fr', name: '法语' },
    { code: 'de', name: '德语' },
];

const TranslateWidget: React.FC = () => {
    const [text, setText] = useState('');
    const [targetLang, setTargetLang] = useState('en');
    const [result, setResult] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleTranslate = useCallback(async () => {
        if (!text.trim()) return;

        setLoading(true);
        setError(null);

        try {
            const response = await api.invoke('com.aios.adapter.translate', 'translate', {
                text,
                targetLang,
            }) as { success?: boolean; data?: { translatedText: string }; error?: { message: string } };

            if (response?.success && response.data) {
                setResult(response.data.translatedText);
            } else {
                setError(response?.error?.message || '翻译失败');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '网络错误');
        } finally {
            setLoading(false);
        }
    }, [text, targetLang]);

    return (
        <div className="translate-widget">
            <div className="widget-header">
                <h4>🌐 翻译</h4>
            </div>
            <div className="widget-body">
                <textarea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="输入要翻译的文本..."
                    rows={3}
                />
                <div className="translate-controls">
                    <select value={targetLang} onChange={(e) => setTargetLang(e.target.value)}>
                        {LANGUAGES.map((lang) => (
                            <option key={lang.code} value={lang.code}>
                                {lang.name}
                            </option>
                        ))}
                    </select>
                    <button onClick={handleTranslate} disabled={loading || !text.trim()}>
                        {loading ? '翻译中...' : '翻译'}
                    </button>
                </div>
                {error && <div className="widget-error">{error}</div>}
                {result && (
                    <div className="translate-result">
                        <strong>结果:</strong>
                        <p>{result}</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default TranslateWidget;
