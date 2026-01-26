/**
 * A2AConfigView - A2A 协议配置界面
 * 管理 AIOS 的 A2A Server 和 Agent Card
 */

import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';

interface AgentCard {
    id: string;
    name: string;
    description: string;
    capabilities: string[];
    endpoint: string;
}

interface A2AConfig {
    enabled: boolean;
    port: number | null;
    host: string;
}

interface A2AStatus {
    running: boolean;
    tasksProcessed: number;
}

const A2AConfigView: React.FC = () => {
    const [config, setConfig] = useState<A2AConfig | null>(null);
    const [status, setStatus] = useState<A2AStatus | null>(null);
    const [agentCard, setAgentCard] = useState<AgentCard | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);

    // Agent Card 编辑状态
    const [editingCard, setEditingCard] = useState(false);
    const [editName, setEditName] = useState('');
    const [editDescription, setEditDescription] = useState('');
    const [editCapabilities, setEditCapabilities] = useState('');

    // Token 生成状态
    const [tokenClientId, setTokenClientId] = useState('');
    const [generatedToken, setGeneratedToken] = useState<string | null>(null);
    const [generatingToken, setGeneratingToken] = useState(false);

    // 加载数据
    const loadData = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);

            const [configData, statusData, cardData] = await Promise.all([
                api.getA2AConfig(),
                api.getA2AStatus(),
                api.getAgentCard(),
            ]);

            setConfig(configData);
            setStatus(statusData);
            setAgentCard(cardData);

            // 初始化编辑状态
            if (cardData) {
                setEditName(cardData.name);
                setEditDescription(cardData.description);
                setEditCapabilities(cardData.capabilities.join(', '));
            }
        } catch (err: any) {
            setError(err.message || '加载 A2A 配置失败');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadData();
    }, [loadData]);

    // 保存 Agent Card
    const handleSaveAgentCard = async () => {
        try {
            setSaving(true);
            setError(null);

            const capabilities = editCapabilities
                .split(',')
                .map(s => s.trim())
                .filter(Boolean);

            const result = await api.setAgentCard({
                name: editName,
                description: editDescription,
                capabilities,
            });

            if (result.success) {
                setAgentCard(result.agentCard);
                setEditingCard(false);
            }
        } catch (err: any) {
            setError(err.message || '保存 Agent Card 失败');
        } finally {
            setSaving(false);
        }
    };

    // 生成 Token
    const handleGenerateToken = async () => {
        if (!tokenClientId.trim()) {
            setError('请输入客户端 ID');
            return;
        }

        try {
            setGeneratingToken(true);
            setError(null);

            const result = await api.generateA2AToken(tokenClientId.trim());

            if (result.success && result.token) {
                setGeneratedToken(result.token);
            } else {
                setError(result.error || '生成 Token 失败');
            }
        } catch (err: any) {
            setError(err.message || '生成 Token 失败');
        } finally {
            setGeneratingToken(false);
        }
    };

    // 复制 Token
    const handleCopyToken = async () => {
        if (generatedToken) {
            try {
                await navigator.clipboard.writeText(generatedToken);
                alert('Token 已复制到剪贴板');
            } catch {
                // 回退方案
                const textarea = document.createElement('textarea');
                textarea.value = generatedToken;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                alert('Token 已复制');
            }
        }
    };

    if (loading) {
        return (
            <div className="a2a-config-view">
                <h3>🤝 A2A 协议配置</h3>
                <div className="loading">加载中...</div>
            </div>
        );
    }

    return (
        <div className="a2a-config-view">
            <h3>🤝 A2A 协议配置</h3>

            {error && (
                <div className="error-banner">
                    ❌ {error}
                    <button onClick={() => setError(null)}>×</button>
                </div>
            )}

            {/* A2A Server 状态 */}
            <div className="config-section">
                <h4>A2A Server 状态</h4>
                <div className="status-card">
                    <div className="status-row">
                        <span className="status-label">状态:</span>
                        <span className={`status-value ${status?.running ? 'running' : 'stopped'}`}>
                            {status?.running ? '● 运行中' : '○ 未启动'}
                        </span>
                    </div>
                    {config?.enabled && (
                        <>
                            <div className="status-row">
                                <span className="status-label">端口:</span>
                                <span className="status-value">{config.port || '-'}</span>
                            </div>
                            <div className="status-row">
                                <span className="status-label">主机:</span>
                                <span className="status-value">{config.host}</span>
                            </div>
                            <div className="status-row">
                                <span className="status-label">已处理任务:</span>
                                <span className="status-value">{status?.tasksProcessed || 0}</span>
                            </div>
                            {agentCard?.endpoint && (
                                <div className="status-row">
                                    <span className="status-label">Agent Card URL:</span>
                                    <span className="status-value endpoint">
                                        {`http://${config.host}:${config.port}/.well-known/agent.json`}
                                    </span>
                                </div>
                            )}
                        </>
                    )}
                    {!config?.enabled && (
                        <div className="hint-text">
                            提示: 设置环境变量 AIOS_A2A_PORT 和 AIOS_A2A_TOKEN_SECRET 启动 A2A Server
                        </div>
                    )}
                </div>
            </div>

            {/* Agent Card 配置 */}
            <div className="config-section">
                <h4>
                    Agent Card 配置
                    {!editingCard && (
                        <button
                            className="btn-small btn-edit"
                            onClick={() => setEditingCard(true)}
                        >
                            ✏️ 编辑
                        </button>
                    )}
                </h4>
                {editingCard ? (
                    <div className="agent-card-form">
                        <div className="form-row">
                            <label>Agent ID:</label>
                            <input
                                type="text"
                                value={agentCard?.id || ''}
                                disabled
                                className="disabled-input"
                            />
                        </div>
                        <div className="form-row">
                            <label>名称:</label>
                            <input
                                type="text"
                                value={editName}
                                onChange={(e) => setEditName(e.target.value)}
                                placeholder="AIOS"
                            />
                        </div>
                        <div className="form-row">
                            <label>描述:</label>
                            <textarea
                                value={editDescription}
                                onChange={(e) => setEditDescription(e.target.value)}
                                placeholder="AIOS Agent - Intelligent Operating System Assistant"
                                rows={3}
                            />
                        </div>
                        <div className="form-row">
                            <label>能力:</label>
                            <input
                                type="text"
                                value={editCapabilities}
                                onChange={(e) => setEditCapabilities(e.target.value)}
                                placeholder="system_control, file_management, ..."
                            />
                            <span className="hint">用逗号分隔</span>
                        </div>
                        <div className="form-actions">
                            <button
                                className="btn-primary"
                                onClick={handleSaveAgentCard}
                                disabled={saving}
                            >
                                {saving ? '保存中...' : '💾 保存配置'}
                            </button>
                            <button
                                className="btn-secondary"
                                onClick={() => {
                                    setEditingCard(false);
                                    if (agentCard) {
                                        setEditName(agentCard.name);
                                        setEditDescription(agentCard.description);
                                        setEditCapabilities(agentCard.capabilities.join(', '));
                                    }
                                }}
                            >
                                取消
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="agent-card-display">
                        <div className="card-row">
                            <span className="card-label">Agent ID:</span>
                            <span className="card-value">{agentCard?.id || '-'}</span>
                        </div>
                        <div className="card-row">
                            <span className="card-label">名称:</span>
                            <span className="card-value">{agentCard?.name || '-'}</span>
                        </div>
                        <div className="card-row">
                            <span className="card-label">描述:</span>
                            <span className="card-value">{agentCard?.description || '-'}</span>
                        </div>
                        <div className="card-row">
                            <span className="card-label">能力:</span>
                            <span className="card-value capabilities">
                                {agentCard?.capabilities?.slice(0, 5).map((cap, i) => (
                                    <span key={i} className="capability-tag">{cap}</span>
                                ))}
                                {(agentCard?.capabilities?.length || 0) > 5 && (
                                    <span className="capability-more">
                                        +{(agentCard?.capabilities?.length || 0) - 5} 更多
                                    </span>
                                )}
                            </span>
                        </div>
                    </div>
                )}
            </div>

            {/* Token 管理 */}
            <div className="config-section">
                <h4>Token 管理</h4>
                {config?.enabled ? (
                    <div className="token-section">
                        <div className="form-row">
                            <label>客户端 ID:</label>
                            <input
                                type="text"
                                value={tokenClientId}
                                onChange={(e) => setTokenClientId(e.target.value)}
                                placeholder="例如: my-client-app"
                            />
                            <button
                                className="btn-primary"
                                onClick={handleGenerateToken}
                                disabled={generatingToken}
                            >
                                {generatingToken ? '生成中...' : '🔑 生成 Token'}
                            </button>
                        </div>
                        {generatedToken && (
                            <div className="generated-token">
                                <div className="token-display">
                                    <code>{generatedToken.substring(0, 50)}...</code>
                                    <button
                                        className="btn-small"
                                        onClick={handleCopyToken}
                                    >
                                        📋 复制
                                    </button>
                                </div>
                                <span className="token-hint">
                                    ⚠️ 请妥善保存此 Token，它不会再次显示
                                </span>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="hint-text">
                        A2A Server 未运行，无法生成 Token
                    </div>
                )}
            </div>
        </div>
    );
};

export default A2AConfigView;
