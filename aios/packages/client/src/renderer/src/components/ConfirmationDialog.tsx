/**
 * ConfirmationDialog - 确认对话框组件
 */

import React from 'react';
import type { ConfirmationRequest } from '../hooks/useConfirmation';
import './ConfirmationDialog.css';

interface ConfirmationDialogProps {
    request: ConfirmationRequest | null;
    onConfirm: (requestId: string) => void;
    onReject: (requestId: string, reason?: string) => void;
    onDismiss: () => void;
}

const RISK_LEVEL_COLORS = {
    medium: '#f59e0b',  // 橙色
    high: '#ef4444',    // 红色
    critical: '#dc2626', // 深红色
};

const RISK_LEVEL_LABELS = {
    medium: '中等风险',
    high: '高风险',
    critical: '严重风险',
};

export const ConfirmationDialog: React.FC<ConfirmationDialogProps> = ({
    request,
    onConfirm,
    onReject,
    onDismiss,
}) => {
    if (!request) return null;

    const riskColor = RISK_LEVEL_COLORS[request.riskLevel];
    const riskLabel = RISK_LEVEL_LABELS[request.riskLevel];

    // 计算剩余时间
    const elapsed = Date.now() - request.createdAt;
    const remaining = Math.max(0, request.timeout - elapsed);
    const remainingSeconds = Math.ceil(remaining / 1000);

    return (
        <div className="confirmation-overlay" onClick={onDismiss}>
            <div className="confirmation-dialog" onClick={e => e.stopPropagation()}>
                <div className="confirmation-header" style={{ borderColor: riskColor }}>
                    <div className="risk-badge" style={{ backgroundColor: riskColor }}>
                        {riskLabel}
                    </div>
                    <h3>{request.operation}</h3>
                </div>

                <div className="confirmation-body">
                    <p className="description">{request.description}</p>

                    {Object.keys(request.details).length > 0 && (
                        <div className="details">
                            <h4>详细信息</h4>
                            <pre>{JSON.stringify(request.details, null, 2)}</pre>
                        </div>
                    )}

                    <div className="timeout-warning">
                        ⏱️ 将在 {remainingSeconds} 秒后自动拒绝
                    </div>
                </div>

                <div className="confirmation-actions">
                    <button
                        className="btn-reject"
                        onClick={() => onReject(request.id)}
                    >
                        拒绝
                    </button>
                    <button
                        className="btn-confirm"
                        style={{ backgroundColor: riskColor }}
                        onClick={() => onConfirm(request.id)}
                    >
                        确认执行
                    </button>
                </div>
            </div>
        </div>
    );
};
