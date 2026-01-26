import React from 'react';
import type { ToolAdapter, ToolCapability, ToolTestHistoryItem, ToolTestResult } from './types';
import './ToolTestDialog.css';

interface ToolTestDialogProps { open: boolean; adapter: ToolAdapter | null; capability: ToolCapability | null; params: Record<string, string>; result: ToolTestResult | null; testing: boolean; history: ToolTestHistoryItem[]; showHistory: boolean; onToggleHistory: () => void; onClose: () => void; onRunTest: () => void; onQuickTest?: () => void; onParamChange: (name: string, value: string) => void; }

function renderParamInput(param: NonNullable<ToolCapability['parameters']>[number], value: string, onChange: (value: string) => void) {
    const label = (<label>{param.name}{param.required && <span className="required">*</span>}</label>);
    if (param.enum && param.enum.length > 0) {
        return (
            <div className="param-input" key={param.name}>
                {label}
                <select value={value} onChange={(e) => onChange(e.target.value)}>
                    <option value="">请选择</option>
                    {param.enum.map((item) => (<option key={item} value={item}>{item}</option>))}
                </select>
            </div>
        );
    }
    if (param.type === 'boolean') {
        return (
            <div className="param-input" key={param.name}>
                {label}
                <select value={value} onChange={(e) => onChange(e.target.value)}>
                    <option value="">请选择</option>
                    <option value="true">true</option>
                    <option value="false">false</option>
                </select>
            </div>
        );
    }
    return (
        <div className="param-input" key={param.name}>
            {label}
            <input type={param.type === 'number' ? 'number' : 'text'} placeholder={param.description} value={value} onChange={(e) => onChange(e.target.value)} />
        </div>
    );
}

export const ToolTestDialog: React.FC<ToolTestDialogProps> = ({ open, adapter, capability, params, result, testing, history, showHistory, onToggleHistory, onClose, onRunTest, onQuickTest, onParamChange }) => {
    if (!open || !adapter || !capability) return null;
    return (
        <div className="tool-test-overlay" onClick={onClose}>
            <div className="tool-test-dialog" onClick={(e) => e.stopPropagation()}>
                <div className="tool-test-header">
                    <div>
                        <h3>{adapter.name} · {capability.name}</h3>
                        <p>{capability.description}</p>
                    </div>
                    <button className="tool-test-close" onClick={onClose}>✕</button>
                </div>
                {capability.parameters && capability.parameters.length > 0 && (
                    <div className="tool-test-params">
                        {capability.parameters.map((param) => renderParamInput(param, params[param.name] || '', (value) => onParamChange(param.name, value)))}
                    </div>
                )}
                <div className="tool-test-actions">
                    {onQuickTest && (<button className="tool-test-quick" onClick={onQuickTest} disabled={testing}>⚡ 快速测试</button>)}
                    <button className="tool-test-run" onClick={onRunTest} disabled={testing}>{testing ? '⏳ 测试中...' : '🚀 执行测试'}</button>
                    <button className="tool-test-history" onClick={onToggleHistory}>📜 历史 ({history.length})</button>
                </div>
                {result && (
                    <div className={`tool-test-result ${result.success ? 'success' : 'error'}`}>
                        <h4>{result.success ? '✅ 成功' : '❌ 失败'}</h4>
                        <pre>{result.success ? JSON.stringify(result.result, null, 2) : result.error}</pre>
                    </div>
                )}
                {showHistory && history.length > 0 && (
                    <div className="tool-test-history-panel">
                        {history.map((item) => (
                            <div key={item.id} className="tool-test-history-item">
                                <div className="history-title">{item.capabilityName}</div>
                                <div className="history-meta">{item.timestamp.toLocaleTimeString('zh-CN')}</div>
                                <pre>{JSON.stringify(item.result.success ? item.result.result : item.result.error, null, 2)}</pre>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};
