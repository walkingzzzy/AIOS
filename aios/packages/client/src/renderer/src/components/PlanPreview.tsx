/**
 * PlanPreview - 计划预览组件
 * 显示待确认的执行计划，包括步骤、风险评估和操作按钮
 */

import { useState } from 'react';
import './PlanPreview.css';

/** 执行步骤 */
interface ExecutionStep {
    id: number;
    description: string;
    action: string;
    params: Record<string, unknown>;
    requiresVision: boolean;
    dependsOn: number[];
}

/** 风险评估 */
interface PlanRisk {
    level: 'low' | 'medium' | 'high';
    description: string;
    mitigation?: string;
}

/** 计划草案 */
export interface PlanDraft {
    draftId: string;
    taskId: string;
    goal: string;
    summary?: string;
    rationale?: string;
    status: 'draft' | 'pending_approval' | 'approved' | 'rejected' | 'modified';
    version: number;
    createdAt: number;
    updatedAt: number;
    estimatedDuration: number;
    steps: ExecutionStep[];
    risks: PlanRisk[];
    requiredPermissions: string[];
    userFeedback?: string;
}

interface PlanPreviewProps {
    plan: PlanDraft;
    onApprove: () => void;
    onReject: (feedback?: string) => void;
    onModify?: (modifications: Partial<ExecutionStep>[]) => void;
    isLoading?: boolean;
}

import ReactMarkdown from 'react-markdown';

/** 格式化时长 */
function formatDuration(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    const seconds = Math.ceil(ms / 1000);
    if (seconds < 60) return `${seconds}秒`;
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return secs > 0 ? `${minutes}分${secs}秒` : `${minutes}分钟`;
}

/** 风险徽章组件 */
function RiskBadge({ risk }: { risk: PlanRisk }) {
    const levelColors = {
        low: 'risk-low',
        medium: 'risk-medium',
        high: 'risk-high',
    };

    const levelIcons = {
        low: 'ℹ️',
        medium: '⚠️',
        high: '🚨',
    };

    return (
        <div className={`risk-badge ${levelColors[risk.level]}`}>
            <span className="risk-icon">{levelIcons[risk.level]}</span>
            <span className="risk-description">{risk.description}</span>
            {risk.mitigation && (
                <span className="risk-mitigation">→ {risk.mitigation}</span>
            )}
        </div>
    );
}

/** 计划步骤组件 */
function PlanStep({ step, index }: { step: ExecutionStep; index: number }) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="plan-step" onClick={() => setExpanded(!expanded)}>
            <div className="step-header">
                <span className="step-number">{index + 1}</span>
                <span className="step-description">{step.description}</span>
                {step.requiresVision && <span className="step-tag vision">👁️ 视觉</span>}
                {step.dependsOn.length > 0 && (
                    <span className="step-tag dependency">
                        依赖: {step.dependsOn.join(', ')}
                    </span>
                )}
            </div>
            {expanded && (
                <div className="step-details">
                    <div className="step-detail-row">
                        <span className="detail-label">动作:</span>
                        <code className="detail-value">{step.action}</code>
                    </div>
                    {Object.keys(step.params).length > 0 && (
                        <div className="step-detail-row">
                            <span className="detail-label">参数:</span>
                            <code className="detail-value">
                                {JSON.stringify(step.params, null, 2)}
                            </code>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

/** 权限标签组件 */
function PermissionTag({ permission }: { permission: string }) {
    const icons: Record<string, string> = {
        filesystem: '📁',
        network: '🌐',
        execute: '⚡',
        screen_capture: '📸',
    };

    return (
        <span className="permission-tag">
            {icons[permission] || '🔐'} {permission}
        </span>
    );
}

export function PlanPreview({
    plan,
    onApprove,
    onReject,
    isLoading = false,
}: PlanPreviewProps) {
    const [showRejectInput, setShowRejectInput] = useState(false);
    const [rejectFeedback, setRejectFeedback] = useState('');
    const [activeTab, setActiveTab] = useState<'scheme' | 'steps'>('scheme');

    const handleReject = () => {
        if (showRejectInput) {
            onReject(rejectFeedback || undefined);
            setShowRejectInput(false);
            setRejectFeedback('');
        } else {
            setShowRejectInput(true);
        }
    };

    const hasHighRisks = plan.risks.some(r => r.level === 'high');
    const hasMediumRisks = plan.risks.some(r => r.level === 'medium');

    return (
        <div className={`plan-preview ${hasHighRisks ? 'has-high-risk' : hasMediumRisks ? 'has-medium-risk' : ''}`}>
            <div className="plan-header">
                <div className="plan-title">
                    <span className="plan-icon">📋</span>
                    <h3>执行计划</h3>
                    <span className={`plan-status status-${plan.status}`}>
                        {plan.status === 'pending_approval' ? '待确认' : plan.status}
                    </span>
                </div>
                {plan.version > 1 && (
                    <span className="plan-version">v{plan.version}</span>
                )}
            </div>

            <div className="plan-tabs">
                <button
                    className={`tab-btn ${activeTab === 'scheme' ? 'active' : ''}`}
                    onClick={() => setActiveTab('scheme')}
                >
                    📝 方案说明
                </button>
                <button
                    className={`tab-btn ${activeTab === 'steps' ? 'active' : ''}`}
                    onClick={() => setActiveTab('steps')}
                >
                    👣 执行步骤 ({plan.steps.length})
                </button>
            </div>

            <div className="plan-content-body">
                {activeTab === 'scheme' && (
                    <div className="plan-scheme">
                        {plan.rationale ? (
                            <div className="markdown-content">
                                <ReactMarkdown>{plan.rationale}</ReactMarkdown>
                            </div>
                        ) : (
                            <div className="empty-scheme">
                                <p className="plan-goal">{plan.summary || plan.goal}</p>
                                <p className="scheme-placeholder">（该计划未提供详细方案说明）</p>
                            </div>
                        )}


                        <div className="plan-meta-inline">
                            <div className="meta-item">
                                <span className="meta-icon">⏱️</span>
                                <span className="meta-label">预估时间:</span>
                                <span className="meta-value">{formatDuration(plan.estimatedDuration)}</span>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'steps' && (
                    <div className="plan-steps-view">
                        {/* 风险提示 */}
                        {plan.risks.length > 0 && (
                            <div className="plan-risks">
                                <h4 className="section-title">⚠️ 风险提示</h4>
                                {plan.risks.map((risk, i) => (
                                    <RiskBadge key={i} risk={risk} />
                                ))}
                            </div>
                        )}

                        {/* 步骤列表 */}
                        <div className="plan-steps-list">
                            {plan.steps.map((step, index) => (
                                <PlanStep key={step.id} step={step} index={index} />
                            ))}
                        </div>

                        {/* 所需权限 */}
                        {plan.requiredPermissions.length > 0 && (
                            <div className="plan-permissions">
                                <h4 className="section-title">所需权限</h4>
                                <div className="permission-list">
                                    {plan.requiredPermissions.map((perm) => (
                                        <PermissionTag key={perm} permission={perm} />
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* 拒绝反馈输入 */}
            {showRejectInput && (
                <div className="reject-input-container">
                    <textarea
                        className="reject-input"
                        placeholder="请输入拒绝原因（可选）..."
                        value={rejectFeedback}
                        onChange={(e) => setRejectFeedback(e.target.value)}
                        rows={3}
                    />
                </div>
            )}

            {/* 操作按钮 */}
            <div className="plan-actions">
                <button
                    className="btn-approve"
                    onClick={onApprove}
                    disabled={isLoading}
                >
                    {isLoading ? '处理中...' : '✓ 确认执行'}
                </button>
                <button
                    className={`btn-reject ${showRejectInput ? 'confirm' : ''}`}
                    onClick={handleReject}
                    disabled={isLoading}
                >
                    {showRejectInput ? '确认拒绝' : '✗ 取消'}
                </button>
                {showRejectInput && (
                    <button
                        className="btn-cancel-reject"
                        onClick={() => {
                            setShowRejectInput(false);
                            setRejectFeedback('');
                        }}
                    >
                        返回
                    </button>
                )}
            </div>
        </div>
    );
}

export default PlanPreview;
