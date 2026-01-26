/**
 * MCPConfigView - MCP 协议配置界面
 * 管理 AIOS 的 MCP Server 和连接的外部 MCP 服务器
 */

import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';

interface MCPServer {
    name: string;
    type: 'stdio' | 'websocket';
    command?: string;
    args?: string[];
    url?: string;
    status: 'disconnected' | 'connecting' | 'connected' | 'error';
    tools: string[];
    lastError?: string;
}

interface MCPConfig {
    enabled: boolean;
    port: number | null;
    host: string;
}

interface MCPStatus {
    running: boolean;
    connectedClients: number;
    exposedTools: string[];
}

const MCPConfigView: React.FC = () => {
    const [config, setConfig] = useState<MCPConfig | null>(null);
    const [status, setStatus] = useState<MCPStatus | null>(null);
    const [servers, setServers] = useState<MCPServer[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // 添加服务器表单状态
    const [newServerName, setNewServerName] = useState('');
    const [newServerType, setNewServerType] = useState<'stdio' | 'websocket'>('stdio');
    const [newServerCommand, setNewServerCommand] = useState('');
    const [newServerArgs, setNewServerArgs] = useState('');
    const [newServerUrl, setNewServerUrl] = useState('');
    const [adding, setAdding] = useState(false);

    // 加载数据
    const loadData = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);

            const [configData, statusData, serversData] = await Promise.all([
                api.getMCPConfig(),
                api.getMCPStatus(),
                api.listMCPServers(),
            ]);

            setConfig(configData);
            setStatus(statusData);
            setServers(serversData);
        } catch (err: any) {
            setError(err.message || '加载 MCP 配置失败');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadData();
    }, [loadData]);

    // 添加服务器
    const handleAddServer = async () => {
        if (!newServerName.trim()) {
            setError('请输入服务器名称');
            return;
        }

        if (newServerType === 'stdio' && !newServerCommand.trim()) {
            setError('stdio 类型需要输入命令');
            return;
        }

        if (newServerType === 'websocket' && !newServerUrl.trim()) {
            setError('websocket 类型需要输入 URL');
            return;
        }

        try {
            setAdding(true);
            setError(null);

            await api.addMCPServer({
                name: newServerName.trim(),
                type: newServerType,
                command: newServerType === 'stdio' ? newServerCommand.trim() : undefined,
                args: newServerType === 'stdio' && newServerArgs.trim()
                    ? newServerArgs.split(' ').filter(Boolean)
                    : undefined,
                url: newServerType === 'websocket' ? newServerUrl.trim() : undefined,
            });

            // 清空表单
            setNewServerName('');
            setNewServerCommand('');
            setNewServerArgs('');
            setNewServerUrl('');

            // 重新加载
            await loadData();
        } catch (err: any) {
            setError(err.message || '添加服务器失败');
        } finally {
            setAdding(false);
        }
    };

    // 移除服务器
    const handleRemoveServer = async (name: string) => {
        try {
            await api.removeMCPServer(name);
            await loadData();
        } catch (err: any) {
            setError(err.message || '移除服务器失败');
        }
    };

    // 测试连接
    const handleTestConnection = async (name: string) => {
        try {
            setError(null);
            const result = await api.testMCPConnection(name);
            if (result.success) {
                alert(`连接成功！发现 ${result.tools?.length || 0} 个工具`);
            } else {
                setError(`测试失败: ${result.error}`);
            }
            await loadData();
        } catch (err: any) {
            setError(err.message || '测试连接失败');
        }
    };

    // 连接/断开服务器
    const handleToggleConnection = async (server: MCPServer) => {
        try {
            setError(null);
            if (server.status === 'connected') {
                await api.disconnectMCPServer(server.name);
            } else {
                const result = await api.connectMCPServer(server.name);
                if (!result.success) {
                    setError(`连接失败: ${result.error}`);
                }
            }
            await loadData();
        } catch (err: any) {
            setError(err.message || '操作失败');
        }
    };

    // 获取状态样式
    const getStatusStyle = (status: MCPServer['status']): string => {
        switch (status) {
            case 'connected': return 'status-connected';
            case 'connecting': return 'status-connecting';
            case 'error': return 'status-error';
            default: return 'status-disconnected';
        }
    };

    // 获取状态图标
    const getStatusIcon = (status: MCPServer['status']): string => {
        switch (status) {
            case 'connected': return '🟢';
            case 'connecting': return '🟡';
            case 'error': return '🔴';
            default: return '⚪';
        }
    };

    if (loading) {
        return (
            <div className="mcp-config-view">
                <h3>🔌 MCP 协议配置</h3>
                <div className="loading">加载中...</div>
            </div>
        );
    }

    return (
        <div className="mcp-config-view">
            <h3>🔌 MCP 协议配置</h3>

            {error && (
                <div className="error-banner">
                    ❌ {error}
                    <button onClick={() => setError(null)}>×</button>
                </div>
            )}

            {/* AIOS MCP Server 状态 */}
            <div className="config-section">
                <h4>AIOS MCP Server 状态</h4>
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
                        </>
                    )}
                    {status?.exposedTools && status.exposedTools.length > 0 && (
                        <div className="status-row tools-row">
                            <span className="status-label">暴露工具:</span>
                            <span className="status-value tools-list">
                                {status.exposedTools.slice(0, 5).join(', ')}
                                {status.exposedTools.length > 5 && ` ... 等 ${status.exposedTools.length} 个`}
                            </span>
                        </div>
                    )}
                    {!config?.enabled && (
                        <div className="hint-text">
                            提示: 设置环境变量 AIOS_MCP_PORT 和 AIOS_MCP_TOKEN 启动 MCP Server
                        </div>
                    )}
                </div>
            </div>

            {/* 已连接的外部 MCP 服务器 */}
            <div className="config-section">
                <h4>已配置的外部 MCP 服务器</h4>
                {servers.length === 0 ? (
                    <div className="empty-state">
                        暂无配置的外部 MCP 服务器
                    </div>
                ) : (
                    <div className="server-list">
                        {servers.map((server) => (
                            <div key={server.name} className={`server-card ${getStatusStyle(server.status)}`}>
                                <div className="server-header">
                                    <span className="server-status">{getStatusIcon(server.status)}</span>
                                    <span className="server-name">{server.name}</span>
                                    <span className="server-type">[{server.type}]</span>
                                </div>
                                <div className="server-info">
                                    {server.type === 'stdio' && (
                                        <span className="server-command">
                                            {server.command} {server.args?.join(' ')}
                                        </span>
                                    )}
                                    {server.type === 'websocket' && (
                                        <span className="server-url">{server.url}</span>
                                    )}
                                </div>
                                {server.status === 'connected' && server.tools.length > 0 && (
                                    <div className="server-tools">
                                        🔧 {server.tools.length} 个工具
                                    </div>
                                )}
                                {server.status === 'error' && server.lastError && (
                                    <div className="server-error">
                                        ❌ {server.lastError}
                                    </div>
                                )}
                                <div className="server-actions">
                                    <button
                                        className="btn-small"
                                        onClick={() => handleTestConnection(server.name)}
                                    >
                                        🧪 测试
                                    </button>
                                    <button
                                        className="btn-small"
                                        onClick={() => handleToggleConnection(server)}
                                    >
                                        {server.status === 'connected' ? '🔌 断开' : '🔗 连接'}
                                    </button>
                                    <button
                                        className="btn-small btn-danger"
                                        onClick={() => handleRemoveServer(server.name)}
                                    >
                                        🗑️ 删除
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* 添加 MCP 服务器 */}
            <div className="config-section">
                <h4>添加 MCP 服务器</h4>
                <div className="add-server-form">
                    <div className="form-row">
                        <label>名称:</label>
                        <input
                            type="text"
                            value={newServerName}
                            onChange={(e) => setNewServerName(e.target.value)}
                            placeholder="例如: filesystem-server"
                        />
                    </div>
                    <div className="form-row">
                        <label>类型:</label>
                        <div className="radio-group">
                            <label>
                                <input
                                    type="radio"
                                    name="serverType"
                                    value="stdio"
                                    checked={newServerType === 'stdio'}
                                    onChange={() => setNewServerType('stdio')}
                                />
                                stdio
                            </label>
                            <label>
                                <input
                                    type="radio"
                                    name="serverType"
                                    value="websocket"
                                    checked={newServerType === 'websocket'}
                                    onChange={() => setNewServerType('websocket')}
                                />
                                WebSocket
                            </label>
                        </div>
                    </div>
                    {newServerType === 'stdio' && (
                        <>
                            <div className="form-row">
                                <label>命令:</label>
                                <input
                                    type="text"
                                    value={newServerCommand}
                                    onChange={(e) => setNewServerCommand(e.target.value)}
                                    placeholder="例如: npx"
                                />
                            </div>
                            <div className="form-row">
                                <label>参数:</label>
                                <input
                                    type="text"
                                    value={newServerArgs}
                                    onChange={(e) => setNewServerArgs(e.target.value)}
                                    placeholder="例如: -y @modelcontextprotocol/server-filesystem"
                                />
                            </div>
                        </>
                    )}
                    {newServerType === 'websocket' && (
                        <div className="form-row">
                            <label>URL:</label>
                            <input
                                type="text"
                                value={newServerUrl}
                                onChange={(e) => setNewServerUrl(e.target.value)}
                                placeholder="例如: ws://localhost:9000"
                            />
                        </div>
                    )}
                    <div className="form-actions">
                        <button
                            className="btn-primary"
                            onClick={handleAddServer}
                            disabled={adding}
                        >
                            {adding ? '添加中...' : '➕ 添加服务器'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default MCPConfigView;
