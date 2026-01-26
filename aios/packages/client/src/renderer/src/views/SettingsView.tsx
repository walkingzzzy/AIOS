/**
 * SettingsView - 设置界面
 * 支持动态获取模型列表和连接测试
 */

import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';
import MCPConfigView from './MCPConfigView';
import A2AConfigView from './A2AConfigView';

interface LayerConfig {
    baseUrl: string;
    apiKey: string;
    model: string;
}

interface ModelInfo {
    id: string;
    name?: string;
    created?: number;
}

interface LayerState {
    config: LayerConfig;
    models: ModelInfo[];
    loading: boolean;
    testing: boolean;
    testResult: 'idle' | 'success' | 'error';
    testMessage: string;
    error: string;
}

const DEFAULT_URLS: Record<string, string> = {
    openai: 'https://api.openai.com/v1',
    anthropic: 'https://api.anthropic.com/v1',
    deepseek: 'https://api.deepseek.com/v1',
    google: 'https://generativelanguage.googleapis.com/v1beta',
    groq: 'https://api.groq.com/openai/v1',
    ollama: 'http://localhost:11434/v1',
};

const LAYER_INFO = {
    fast: { emoji: '⚡', name: 'Fast Layer', desc: '简单指令，快速响应，成本最低' },
    vision: { emoji: '👁️', name: 'Vision Layer', desc: '截图分析，图像理解，多模态处理' },
    smart: { emoji: '🧠', name: 'Smart Layer', desc: '复杂推理，深度思考，最高质量' },
};

const createInitialState = (): LayerState => ({
    config: { baseUrl: '', apiKey: '', model: '' },
    models: [],
    loading: false,
    testing: false,
    testResult: 'idle',
    testMessage: '',
    error: '',
});

const SettingsView: React.FC = () => {
    const [fast, setFast] = useState<LayerState>(createInitialState());
    const [vision, setVision] = useState<LayerState>(createInitialState());
    const [smart, setSmart] = useState<LayerState>(createInitialState());
    const [mainTab, setMainTab] = useState<'ai' | 'mcp' | 'a2a'>('ai');
    const [aiSubTab, setAiSubTab] = useState<'fast' | 'vision' | 'smart'>('fast');
    const [saving, setSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle');
    const [initialLoading, setInitialLoading] = useState(true);
    const [version, setVersion] = useState<string>('');

    // 加载版本信息
    useEffect(() => {
        api.getVersion()
            .then(res => setVersion(res?.version || ''))
            .catch(() => setVersion(''));
    }, []);

    // 加载已有配置
    useEffect(() => {
        const loadConfig = async () => {
            try {
                const config = await api.getAIConfig() as any;
                if (config) {
                    if (config.fast) {
                        setFast(prev => ({
                            ...prev,
                            config: {
                                baseUrl: config.fast.baseUrl || DEFAULT_URLS.openai,
                                apiKey: config.fast.apiKey || '',
                                model: config.fast.model || '',
                            }
                        }));
                    }
                    if (config.vision) {
                        setVision(prev => ({
                            ...prev,
                            config: {
                                baseUrl: config.vision.baseUrl || DEFAULT_URLS.google,
                                apiKey: config.vision.apiKey || '',
                                model: config.vision.model || '',
                            }
                        }));
                    }
                    if (config.smart) {
                        setSmart(prev => ({
                            ...prev,
                            config: {
                                baseUrl: config.smart.baseUrl || DEFAULT_URLS.anthropic,
                                apiKey: config.smart.apiKey || '',
                                model: config.smart.model || '',
                            }
                        }));
                    }
                }
            } catch (error) {
                console.error('Failed to load AI config:', error);
            } finally {
                setInitialLoading(false);
            }
        };
        loadConfig();
    }, []);

    // 获取模型列表
    const fetchModels = useCallback(async (
        layer: 'fast' | 'vision' | 'smart',
        setState: React.Dispatch<React.SetStateAction<LayerState>>
    ) => {
        const state = layer === 'fast' ? fast : layer === 'vision' ? vision : smart;
        const { baseUrl, apiKey } = state.config;

        if (!baseUrl) {
            setState(prev => ({ ...prev, error: '请输入 API 地址' }));
            return;
        }

        setState(prev => ({ ...prev, loading: true, error: '', models: [] }));

        try {
            const result = await api.fetchModels({ baseUrl, apiKey }) as any;
            if (result.success && result.models) {
                setState(prev => ({
                    ...prev,
                    loading: false,
                    models: result.models,
                    error: '',
                }));
            } else {
                setState(prev => ({
                    ...prev,
                    loading: false,
                    error: result.error || '获取模型列表失败',
                }));
            }
        } catch (error: any) {
            setState(prev => ({
                ...prev,
                loading: false,
                error: error.message || '获取模型列表失败',
            }));
        }
    }, [fast, vision, smart]);

    // 测试连接
    const testConnection = useCallback(async (
        layer: 'fast' | 'vision' | 'smart',
        setState: React.Dispatch<React.SetStateAction<LayerState>>
    ) => {
        const state = layer === 'fast' ? fast : layer === 'vision' ? vision : smart;
        const { baseUrl, apiKey, model } = state.config;

        if (!baseUrl || !model) {
            setState(prev => ({
                ...prev,
                testResult: 'error',
                testMessage: '请填写 API 地址并选择模型'
            }));
            return;
        }

        setState(prev => ({ ...prev, testing: true, testResult: 'idle', testMessage: '' }));

        try {
            const result = await api.testAIConnection({ baseUrl, apiKey, model }) as any;
            setState(prev => ({
                ...prev,
                testing: false,
                testResult: result.success ? 'success' : 'error',
                testMessage: result.success
                    ? `连接成功! "${result.response?.substring(0, 50)}${result.response?.length > 50 ? '...' : ''}"`
                    : result.error,
            }));
        } catch (error: any) {
            setState(prev => ({
                ...prev,
                testing: false,
                testResult: 'error',
                testMessage: error.message || '连接测试失败',
            }));
        }
    }, [fast, vision, smart]);

    // 保存配置
    const handleSave = async () => {
        setSaving(true);
        setSaveStatus('idle');

        try {
            await api.setAIConfig({
                fast: {
                    baseUrl: fast.config.baseUrl,
                    apiKey: fast.config.apiKey === '••••••••' ? undefined : fast.config.apiKey,
                    model: fast.config.model,
                },
                vision: {
                    baseUrl: vision.config.baseUrl,
                    apiKey: vision.config.apiKey === '••••••••' ? undefined : vision.config.apiKey,
                    model: vision.config.model,
                },
                smart: {
                    baseUrl: smart.config.baseUrl,
                    apiKey: smart.config.apiKey === '••••••••' ? undefined : smart.config.apiKey,
                    model: smart.config.model,
                },
            });
            setSaveStatus('success');
            setTimeout(() => setSaveStatus('idle'), 3000);
        } catch (error) {
            console.error('Failed to save config:', error);
            setSaveStatus('error');
        } finally {
            setSaving(false);
        }
    };

    // 快速填充预设 URL
    const applyPreset = (
        preset: string,
        setState: React.Dispatch<React.SetStateAction<LayerState>>
    ) => {
        const url = DEFAULT_URLS[preset];
        if (url) {
            setState(prev => ({
                ...prev,
                config: { ...prev.config, baseUrl: url },
                models: [],
                error: '',
            }));
        }
    };

    // 获取当前选中的预设
    const getActivePreset = (baseUrl: string): string | null => {
        for (const [key, url] of Object.entries(DEFAULT_URLS)) {
            if (baseUrl === url) return key;
        }
        return null;
    };

    // 渲染单个 Layer 配置
    const renderLayerConfig = (
        layer: 'fast' | 'vision' | 'smart',
        state: LayerState,
        setState: React.Dispatch<React.SetStateAction<LayerState>>
    ) => {
        const info = LAYER_INFO[layer];
        const activePreset = getActivePreset(state.config.baseUrl);

        return (
            <div className="settings-section" key={layer}>
                <h3>
                    <span>{info.emoji}</span>
                    {info.name}
                </h3>
                <p className="layer-desc">{info.desc}</p>

                {/* 预设按钮 */}
                <div className="preset-buttons">
                    <span className="preset-label">快速选择:</span>
                    {Object.keys(DEFAULT_URLS).map(preset => (
                        <button
                            key={preset}
                            className={`preset-btn ${activePreset === preset ? 'active' : ''}`}
                            onClick={() => applyPreset(preset, setState)}
                        >
                            {preset}
                        </button>
                    ))}
                </div>

                {/* Base URL */}
                <div className="setting-item">
                    <span className="setting-label">API 地址</span>
                    <input
                        type="text"
                        className="setting-input"
                        value={state.config.baseUrl}
                        onChange={(e) => setState(prev => ({
                            ...prev,
                            config: { ...prev.config, baseUrl: e.target.value },
                            models: [],
                        }))}
                        placeholder="https://api.openai.com/v1"
                    />
                </div>

                {/* API Key */}
                <div className="setting-item">
                    <span className="setting-label">API Key</span>
                    <input
                        type="password"
                        className="setting-input"
                        value={state.config.apiKey}
                        onChange={(e) => setState(prev => ({
                            ...prev,
                            config: { ...prev.config, apiKey: e.target.value },
                        }))}
                        placeholder="sk-... (可选，部分服务不需要)"
                    />
                </div>

                {/* 获取模型按钮 */}
                <div className="setting-item">
                    <span className="setting-label"></span>
                    <button
                        className="fetch-models-btn"
                        onClick={() => fetchModels(layer, setState)}
                        disabled={state.loading || !state.config.baseUrl}
                    >
                        {state.loading ? '⏳ 获取中...' : '📥 获取模型列表'}
                    </button>
                    {state.error && <span className="error-text">{state.error}</span>}
                </div>

                {/* 模型选择 */}
                <div className="setting-item">
                    <span className="setting-label">模型</span>
                    {state.models.length > 0 ? (
                        <select
                            className="setting-input"
                            value={state.config.model}
                            onChange={(e) => setState(prev => ({
                                ...prev,
                                config: { ...prev.config, model: e.target.value },
                                testResult: 'idle',
                            }))}
                        >
                            <option value="">-- 选择模型 --</option>
                            {state.models.map(m => (
                                <option key={m.id} value={m.id}>{m.id}</option>
                            ))}
                        </select>
                    ) : (
                        <input
                            type="text"
                            className="setting-input"
                            value={state.config.model}
                            onChange={(e) => setState(prev => ({
                                ...prev,
                                config: { ...prev.config, model: e.target.value },
                                testResult: 'idle',
                            }))}
                            placeholder="手动输入或点击上方获取列表"
                        />
                    )}
                </div>

                {/* 测试连接 */}
                <div className="test-section">
                    <button
                        className={`test-conn-btn ${state.testResult}`}
                        onClick={() => testConnection(layer, setState)}
                        disabled={state.testing || !state.config.model}
                    >
                        {state.testing ? '⏳ 测试中...' : '🧪 测试连接'}
                    </button>
                    {state.testMessage && (
                        <span className={`test-message ${state.testResult}`}>
                            {state.testResult === 'success' ? '✅ ' : '❌ '}
                            {state.testMessage}
                        </span>
                    )}
                </div>
            </div>
        );
    };

    if (initialLoading) {
        return (
            <div className="settings-view">
                <h2>⚙️ 设置</h2>
                <div className="loading">加载配置中</div>
            </div>
        );
    }

    return (
        <div className="settings-view">
            <h2>⚙️ 设置</h2>

            {/* 主导航 Tab */}
            <div className="settings-main-tabs">
                <button
                    className={`settings-main-tab ${mainTab === 'ai' ? 'active' : ''}`}
                    onClick={() => setMainTab('ai')}
                >
                    🧠 AI 模型
                </button>
                <button
                    className={`settings-main-tab ${mainTab === 'mcp' ? 'active' : ''}`}
                    onClick={() => setMainTab('mcp')}
                >
                    🔌 MCP
                </button>
                <button
                    className={`settings-main-tab ${mainTab === 'a2a' ? 'active' : ''}`}
                    onClick={() => setMainTab('a2a')}
                >
                    🤝 A2A
                </button>
            </div>

            {/* AI 模型配置 */}
            {mainTab === 'ai' && (
                <>
                    <p className="settings-intro">
                        配置三层 AI 模型，支持 OpenAI 兼容接口。输入 API 地址后点击获取模型列表，或手动输入模型名称。
                    </p>

                    <div className="settings-tabs">
                        <button
                            className={`settings-tab ${aiSubTab === 'fast' ? 'active' : ''}`}
                            onClick={() => setAiSubTab('fast')}
                        >
                            ⚡ Fast
                        </button>
                        <button
                            className={`settings-tab ${aiSubTab === 'vision' ? 'active' : ''}`}
                            onClick={() => setAiSubTab('vision')}
                        >
                            👁️ Vision
                        </button>
                        <button
                            className={`settings-tab ${aiSubTab === 'smart' ? 'active' : ''}`}
                            onClick={() => setAiSubTab('smart')}
                        >
                            🧠 Smart
                        </button>
                    </div>

                    <div className="settings-content">
                        {aiSubTab === 'fast' && renderLayerConfig('fast', fast, setFast)}
                        {aiSubTab === 'vision' && renderLayerConfig('vision', vision, setVision)}
                        {aiSubTab === 'smart' && renderLayerConfig('smart', smart, setSmart)}
                    </div>

                    <button
                        className="save-button"
                        onClick={handleSave}
                        disabled={saving}
                    >
                        {saving ? '💾 保存中...' : saveStatus === 'success' ? '✅ 配置已保存' : saveStatus === 'error' ? '❌ 保存失败' : '💾 保存配置'}
                    </button>
                </>
            )}

            {/* MCP 配置 */}
            {mainTab === 'mcp' && <MCPConfigView />}

            {/* A2A 配置 */}
            {mainTab === 'a2a' && <A2AConfigView />}

            <footer className="settings-footer">
                <span className="version-info">AIOS v{version || '...'}</span>
            </footer>
        </div>
    );
};

export default SettingsView;
