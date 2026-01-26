/**
 * ToolsView - 工具/适配器展示界面
 * 显示所有可用的适配器和能力，点击可进行测试
 */

import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { ToolCardsPanel } from '../components/tools/ToolCardsPanel';
import { ToolTestDialog } from '../components/tools/ToolTestDialog';
import type { ToolAdapter, ToolCapability, ToolTestHistoryItem, ToolTestResult } from '../components/tools/types';

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
    const [adapters, setAdapters] = useState<ToolAdapter[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedAdapter, setSelectedAdapter] = useState<ToolAdapter | null>(null);
    const [selectedCapability, setSelectedCapability] = useState<ToolCapability | null>(null);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [testParams, setTestParams] = useState<Record<string, string>>({});
    const [testResult, setTestResult] = useState<ToolTestResult | null>(null);
    const [testing, setTesting] = useState(false);
    const [testHistory, setTestHistory] = useState<ToolTestHistoryItem[]>([]);
    const [showHistory, setShowHistory] = useState(false);

    useEffect(() => {
        fetchAdapters();
    }, []);

    const fetchAdapters = async () => {
        try {
            const result = await api.getAdaptersWithStatus();
            if (result && Array.isArray(result)) {
                setAdapters(result as ToolAdapter[]);
            } else {
                console.error('Invalid adapters response:', result);
            }
        } catch (error) {
            console.error('Failed to fetch adapters:', error);
        } finally {
            setLoading(false);
        }
    };

    const openDialog = (adapter: ToolAdapter, capability: ToolCapability, presetParams?: Record<string, unknown>) => {
        setSelectedAdapter(adapter);
        setSelectedCapability(capability);
        const nextParams: Record<string, string> = {};
        if (presetParams) {
            Object.entries(presetParams).forEach(([key, value]) => {
                nextParams[key] = typeof value === 'string' ? value : JSON.stringify(value);
            });
        }
        setTestParams(nextParams);
        setTestResult(null);
        setDialogOpen(true);
    };

    const handleSelectCapability = (adapter: ToolAdapter, capability: ToolCapability) => {
        openDialog(adapter, capability);
    };

    const handleCloseDialog = () => {
        setDialogOpen(false);
        setShowHistory(false);
    };

    const updateParam = (name: string, value: string) => {
        setTestParams((prev) => ({ ...prev, [name]: value }));
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
                        setTestResult({ success: false, error: `缺少必填参数: ${param.name}` });
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
                                if (param.type === 'object' && (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed))) {
                                    throw new Error(`参数 ${param.name} 必须是 JSON 对象`);
                                }
                                args[param.name] = parsed;
                            } else {
                                args[param.name] = value;
                            }
                        } catch (error) {
                            setTestResult({ success: false, error: error instanceof Error ? error.message : `参数 ${param.name} 解析失败` });
                            setTesting(false);
                            return;
                        }
                    }
                }
            }

            const result = await api.invoke(selectedAdapter.id, selectedCapability.id, args);
            setTestResult({ success: true, result });
            setTestHistory((prev) => [{
                id: Date.now().toString(),
                adapterId: selectedAdapter.id,
                capabilityId: selectedCapability.id,
                capabilityName: selectedCapability.name,
                params: args,
                result: { success: true, result },
                timestamp: new Date(),
            }, ...prev].slice(0, 20));
        } catch (error) {
            setTestResult({ success: false, error: error instanceof Error ? error.message : '未知错误' });
            if (selectedAdapter && selectedCapability) {
                setTestHistory((prev) => [{
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

    const handleQuickTest = async (adapter: ToolAdapter, capability: ToolCapability) => {
        const presets = QUICK_TEST_PRESETS[adapter.id]?.[capability.id];
        if (!presets) return;
        openDialog(adapter, capability, presets);
        setTesting(true);
        setTestResult(null);

        try {
            const result = await api.invoke(adapter.id, capability.id, presets);
            setTestResult({ success: true, result });
            setTestHistory((prev) => [{
                id: Date.now().toString(),
                adapterId: adapter.id,
                capabilityId: capability.id,
                capabilityName: capability.name,
                params: presets,
                result: { success: true, result },
                timestamp: new Date(),
            }, ...prev].slice(0, 20));
        } catch (error) {
            setTestResult({ success: false, error: error instanceof Error ? error.message : '未知错误' });
        } finally {
            setTesting(false);
        }
    };

    const hasQuickTest = (adapterId: string, capabilityId: string) => {
        return !!QUICK_TEST_PRESETS[adapterId]?.[capabilityId];
    };

    const quickTestHandler = selectedAdapter && selectedCapability && hasQuickTest(selectedAdapter.id, selectedCapability.id)
        ? () => handleQuickTest(selectedAdapter, selectedCapability)
        : undefined;

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
            </header>

            <div className="tools-content">
                <ToolCardsPanel
                    adapters={adapters}
                    selectedAdapterId={selectedAdapter?.id}
                    selectedCapabilityId={selectedCapability?.id}
                    adapterIcons={ADAPTER_ICONS}
                    onSelectCapability={handleSelectCapability}
                    onQuickTest={handleQuickTest}
                    hasQuickTest={hasQuickTest}
                />
            </div>

            <ToolTestDialog
                open={dialogOpen}
                adapter={selectedAdapter}
                capability={selectedCapability}
                params={testParams}
                result={testResult}
                testing={testing}
                history={testHistory}
                showHistory={showHistory}
                onToggleHistory={() => setShowHistory(!showHistory)}
                onClose={handleCloseDialog}
                onRunTest={handleTest}
                onQuickTest={quickTestHandler}
                onParamChange={updateParam}
            />
        </div>
    );
};

export default ToolsView;
