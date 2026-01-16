/**
 * ToolsView - 工具/适配器展示界面
 * 显示所有可用的适配器和能力，点击可进行测试
 */

import React, { useState, useEffect } from 'react';
import PermissionGuide from '../components/PermissionGuide';
import { api } from '../utils/api';

interface Capability {
    id: string;
    name: string;
    description: string;
    permissionLevel: string;
    parameters?: Array<{
        name: string;
        type: string;
        required: boolean;
        description: string;
    }>;
}

interface Adapter {
    id: string;
    name: string;
    description: string;
    capabilities: Capability[];
    available?: boolean;
}

interface TestResult {
    success: boolean;
    result?: unknown;
    error?: string;
}

interface TestHistoryItem {
    id: string;
    adapterId: string;
    capabilityId: string;
    capabilityName: string;
    params: Record<string, unknown>;
    result: TestResult;
    timestamp: Date;
}

// 快速测试预设参数
const QUICK_TEST_PRESETS: Record<string, Record<string, Record<string, unknown>>> = {
    'com.aios.adapter.audio': {
        'set_volume': { volume: 50 },
        'set_muted': { muted: true },
    },
    'com.aios.adapter.display': {
        'set_brightness': { brightness: 50 },
    },
    'com.aios.adapter.desktop': {
        'set_appearance': { mode: 'dark' },
    },
    'com.aios.adapter.power': {
        'shutdown': { delay: 60, confirm: false },
        'restart': { delay: 60, confirm: false },
    },
    'com.aios.adapter.clipboard': {
        'write_text': { text: 'Hello from AIOS!' },
    },
    'com.aios.adapter.notification': {
        'show': { title: 'AIOS 测试', message: '这是一条测试通知' },
    },
    'com.aios.adapter.calculator': {
        'evaluate': { expression: '2 + 2 * 3' },
    },
    'com.aios.adapter.speech': {
        'speak': { text: '你好，我是 AIOS' },
    },
};

const ADAPTER_ICONS: Record<string, string> = {
    'com.aios.adapter.audio': '🔊',
    'com.aios.adapter.display': '🔆',
    'com.aios.adapter.desktop': '🖼️',
    'com.aios.adapter.power': '⚡',
    'com.aios.adapter.file': '📁',
    'com.aios.adapter.systeminfo': '💻',
    'com.aios.adapter.apps': '📱',
    'com.aios.adapter.window': '🪟',
    'com.aios.adapter.browser': '🌐',
    'com.aios.adapter.speech': '🗣️',
    'com.aios.adapter.notification': '🔔',
    'com.aios.adapter.timer': '⏰',
    'com.aios.adapter.calculator': '🧮',
    'com.aios.adapter.calendar': '📅',
    'com.aios.adapter.weather': '🌤️',
    'com.aios.adapter.translate': '🌍',
    'com.aios.adapter.screenshot': '📸',
    'com.aios.adapter.clipboard': '📋',
};

const ToolsView: React.FC = () => {
    const [adapters, setAdapters] = useState<Adapter[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedAdapter, setSelectedAdapter] = useState<Adapter | null>(null);
    const [selectedCapability, setSelectedCapability] = useState<Capability | null>(null);
    const [testParams, setTestParams] = useState<Record<string, string>>({});
    const [testResult, setTestResult] = useState<TestResult | null>(null);
    const [testing, setTesting] = useState(false);
    const [testHistory, setTestHistory] = useState<TestHistoryItem[]>([]);
    const [showHistory, setShowHistory] = useState(false);

    useEffect(() => {
        fetchAdapters();
    }, []);

    const fetchAdapters = async () => {
        try {
            const result = await api.getAdaptersWithStatus();
            if (result && Array.isArray(result)) {
                setAdapters(result as Adapter[]);
            } else {
                console.error('Invalid adapters response:', result);
            }
        } catch (error) {
            console.error('Failed to fetch adapters:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleCapabilityClick = (adapter: Adapter, capability: Capability) => {
        setSelectedAdapter(adapter);
        setSelectedCapability(capability);
        setTestParams({});
        setTestResult(null);
    };

    const handleTest = async () => {
        if (!selectedAdapter || !selectedCapability) return;

        setTesting(true);
        setTestResult(null);

        try {
            const args: Record<string, unknown> = {};

            if (selectedCapability.parameters) {
                for (const param of selectedCapability.parameters) {
                    const value = testParams[param.name];
                    const hasValue = value !== undefined && value.trim() !== '';
                    if (param.required && !hasValue) {
                        setTestResult({
                            success: false,
                            error: `缺少必填参数: ${param.name}`,
                        });
                        setTesting(false);
                        return;
                    }
                    if (hasValue) {
                        try {
                            if (param.type === 'number') {
                                const num = Number(value);
                                if (Number.isNaN(num)) {
                                    throw new Error(`参数 ${param.name} 必须是数字`);
                                }
                                args[param.name] = num;
                            } else if (param.type === 'boolean') {
                                const lower = value.trim().toLowerCase();
                                if (lower === 'true' || lower === '1' || lower === 'yes') {
                                    args[param.name] = true;
                                } else if (lower === 'false' || lower === '0' || lower === 'no') {
                                    args[param.name] = false;
                                } else {
                                    throw new Error(`参数 ${param.name} 必须是 boolean (true/false)`);
                                }
                            } else if (param.type === 'object' || param.type === 'array') {
                                const parsed = JSON.parse(value);
                                if (param.type === 'array' && !Array.isArray(parsed)) {
                                    throw new Error(`参数 ${param.name} 必须是 JSON 数组`);
                                }
                                if (
                                    param.type === 'object' &&
                                    (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed))
                                ) {
                                    throw new Error(`参数 ${param.name} 必须是 JSON 对象`);
                                }
                                args[param.name] = parsed;
                            } else {
                                args[param.name] = value;
                            }
                        } catch (error) {
                            setTestResult({
                                success: false,
                                error: error instanceof Error ? error.message : `参数 ${param.name} 解析失败`,
                            });
                            setTesting(false);
                            return;
                        }
                    }
                }
            }

            console.log('[ToolsView] Invoking:', selectedAdapter.id, selectedCapability.id, args);
            const result = await api.invoke(selectedAdapter.id, selectedCapability.id, args);
            console.log('[ToolsView] Result:', result);

            setTestResult({ success: true, result });

            setTestHistory(prev => [{
                id: Date.now().toString(),
                adapterId: selectedAdapter.id,
                capabilityId: selectedCapability.id,
                capabilityName: selectedCapability.name,
                params: args,
                result: { success: true, result },
                timestamp: new Date(),
            }, ...prev].slice(0, 20));
        } catch (error) {
            console.error('[ToolsView] Error:', error);
            setTestResult({
                success: false,
                error: error instanceof Error ? error.message : '未知错误',
            });

            if (selectedAdapter && selectedCapability) {
                setTestHistory(prev => [{
                    id: Date.now().toString(),
                    adapterId: selectedAdapter.id,
                    capabilityId: selectedCapability.id,
                    capabilityName: selectedCapability.name,
                    params: {},
                    result: { success: false, error: error instanceof Error ? error.message : '未知错误' },
                    timestamp: new Date(),
                }, ...prev].slice(0, 20));
            }
        } finally {
            setTesting(false);
        }
    };

    const handleQuickTest = async (adapter: Adapter, capability: Capability) => {
        const presets = QUICK_TEST_PRESETS[adapter.id]?.[capability.id];
        if (!presets) return;

        setSelectedAdapter(adapter);
        setSelectedCapability(capability);
        setTesting(true);
        setTestResult(null);

        try {
            const result = await api.invoke(adapter.id, capability.id, presets);
            setTestResult({ success: true, result });
            setTestHistory(prev => [{
                id: Date.now().toString(),
                adapterId: adapter.id,
                capabilityId: capability.id,
                capabilityName: capability.name,
                params: presets,
                result: { success: true, result },
                timestamp: new Date(),
            }, ...prev].slice(0, 20));
        } catch (error) {
            setTestResult({
                success: false,
                error: error instanceof Error ? error.message : '未知错误',
            });
        } finally {
            setTesting(false);
        }
    };

    const hasQuickTest = (adapterId: string, capabilityId: string) => {
        return !!QUICK_TEST_PRESETS[adapterId]?.[capabilityId];
    };

    if (loading) {
        return (
            <div className="tools-view">
                <div className="loading">加载中</div>
            </div>
        );
    }

    return (
        <div className="tools-view">
            <header className="tools-header">
                <div className="tools-header-left">
                    <h2>🛠️ 工具箱</h2>
                    <p>点击能力按钮测试功能，带 ⚡ 标记的支持快速测试</p>
                </div>
                <div className="tools-header-right">
                    <button
                        className={`header-btn ${showHistory ? 'active' : ''}`}
                        onClick={() => setShowHistory(!showHistory)}
                        style={showHistory ? { background: 'var(--accent)', color: 'white', borderColor: 'var(--accent)' } : {}}
                    >
                        📜 历史 ({testHistory.length})
                    </button>
                </div>
            </header>

            <div className="tools-content">
                <div className="adapters-grid">
                    {adapters.map((adapter) => (
                        <div 
                            key={adapter.id} 
                            className={`adapter-card ${adapter.available === false ? 'unavailable' : ''}`}
                        >
                            <div className="adapter-header">
                                <span className="adapter-icon">{ADAPTER_ICONS[adapter.id] || '🔧'}</span>
                                <div className="adapter-info">
                                    <h3>
                                        {adapter.name}
                                        <span className={`status-badge ${adapter.available === false ? 'unavailable' : 'available'}`}>
                                            {adapter.available === false ? '不可用' : '可用'}
                                        </span>
                                    </h3>
                                    <p>{adapter.description}</p>
                                </div>
                            </div>
                            <div className="capabilities-list">
                                {adapter.capabilities.map((cap) => (
                                    <button
                                        key={cap.id}
                                        className={`capability-btn ${selectedAdapter?.id === adapter.id && selectedCapability?.id === cap.id ? 'active' : ''}`}
                                        onClick={() => handleCapabilityClick(adapter, cap)}
                                    >
                                        <span className="cap-name">{cap.name}</span>
                                        <span className={`cap-permission ${cap.permissionLevel}`}>
                                            {cap.permissionLevel}
                                        </span>
                                        {hasQuickTest(adapter.id, cap.id) && (
                                            <span
                                                className="quick-test-icon"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    handleQuickTest(adapter, cap);
                                                }}
                                                title="快速测试"
                                            >
                                                ⚡
                                            </span>
                                        )}
                                    </button>
                                ))}
                            </div>
                            {adapter.available === false && (
                                <PermissionGuide
                                    adapterId={adapter.id}
                                    adapterName={adapter.name}
                                    available={adapter.available}
                                />
                            )}
                        </div>
                    ))}
                </div>

                {selectedCapability && (
                    <div className="test-panel">
                        <h3>测试: {selectedCapability.name}</h3>
                        <p className="test-description">{selectedCapability.description}</p>

                        {selectedCapability.parameters && selectedCapability.parameters.length > 0 && (
                            <div className="test-params">
                                {selectedCapability.parameters.map((param) => (
                                    <div key={param.name} className="param-input">
                                        <label>
                                            {param.name}
                                            {param.required && <span className="required">*</span>}
                                        </label>
                                        <input
                                            type={param.type === 'number' ? 'number' : 'text'}
                                            placeholder={param.description}
                                            value={testParams[param.name] || ''}
                                            onChange={(e) => setTestParams({ ...testParams, [param.name]: e.target.value })}
                                        />
                                    </div>
                                ))}
                            </div>
                        )}

                        <button
                            className="test-btn"
                            onClick={handleTest}
                            disabled={testing}
                        >
                            {testing ? '⏳ 测试中...' : '🚀 执行测试'}
                        </button>

                        {testResult && (
                            <div className={`test-result ${testResult.success ? 'success' : 'error'}`}>
                                <h4>{testResult.success ? '✅ 成功' : '❌ 失败'}</h4>
                                <pre>
                                    {testResult.success
                                        ? JSON.stringify(testResult.result, null, 2)
                                        : testResult.error
                                    }
                                </pre>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ToolsView;
