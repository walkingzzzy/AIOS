/**
 * PlanConfirmationManager - 计划确认管理器
 * 管理计划草案的创建、审批、版本控制
 * 
 * 核心职责：
 * 1. 创建和管理计划草案
 * 2. 处理用户审批流程
 * 3. 维护计划版本历史
 * 4. 提供计划查询接口
 */

import { EventEmitter } from 'events';
import type {
    ExecutionPlan,
    ExecutionStep,
    PlanDraft,
    PlanStatus,
    PlanRisk,
    PlanApprovalRequest,
    PlanApprovalResponse,
    PlanEvent,
    PlanEventType,
} from '../../types/orchestrator.js';

/**
 * 计划确认管理器配置
 */
export interface PlanConfirmationConfig {
    /** 默认审批超时时间 (ms)，默认 5 分钟 */
    defaultTimeout?: number;
    /** 是否自动生成风险评估 */
    autoRiskAssessment?: boolean;
    /** 最大版本历史数量 */
    maxVersionHistory?: number;
}

/**
 * 等待中的审批回调
 */
interface PendingApproval {
    resolve: (response: PlanApprovalResponse) => void;
    reject: (error: Error) => void;
    timeoutId?: NodeJS.Timeout;
}

/**
 * 计划确认管理器
 */
export class PlanConfirmationManager extends EventEmitter {
    private pendingPlans: Map<string, PlanDraft> = new Map();
    private planHistory: Map<string, PlanDraft[]> = new Map();
    private approvalCallbacks: Map<string, PendingApproval> = new Map();
    private draftCounter: number = 0;
    private config: Required<PlanConfirmationConfig>;

    constructor(config: PlanConfirmationConfig = {}) {
        super();
        this.config = {
            defaultTimeout: config.defaultTimeout ?? 5 * 60 * 1000, // 5 minutes
            autoRiskAssessment: config.autoRiskAssessment ?? true,
            maxVersionHistory: config.maxVersionHistory ?? 10,
        };
    }

    /**
     * 生成草案 ID
     */
    private generateDraftId(): string {
        return `draft_${Date.now()}_${++this.draftCounter}`;
    }

    /**
     * 创建计划草案
     * @param taskId 任务 ID
     * @param plan 基础执行计划
     * @param options 可选配置
     */
    createDraft(
        taskId: string,
        plan: ExecutionPlan,
        options: {
            summary?: string;
            risks?: PlanRisk[];
            requiredPermissions?: string[];
        } = {}
    ): PlanDraft {
        const draftId = this.generateDraftId();
        const now = Date.now();

        // 计算预估时间
        const estimatedDuration = this.estimateDuration(plan.steps);

        // 自动生成风险评估（如果启用且未提供）
        const risks = options.risks ?? (this.config.autoRiskAssessment
            ? this.assessRisks(plan)
            : []);

        // 提取所需权限
        const requiredPermissions = options.requiredPermissions ??
            this.extractRequiredPermissions(plan.steps);

        const draft: PlanDraft = {
            ...plan,
            draftId,
            taskId,
            status: 'draft',
            version: 1,
            createdAt: now,
            updatedAt: now,
            summary: options.summary || this.generateSummary(plan),
            estimatedDuration,
            risks,
            requiredPermissions,
        };

        // 存储草案
        this.pendingPlans.set(draftId, draft);

        // 初始化版本历史
        this.planHistory.set(draftId, [{ ...draft }]);

        // 发送创建事件
        this.emitPlanEvent('plan.created', draft);

        console.log(`[PlanConfirmationManager] Created draft ${draftId} for task ${taskId}`);

        return draft;
    }

    /**
     * 提交计划待审批
     * 返回 Promise，在用户确认后 resolve
     */
    submitForApproval(
        taskId: string,
        draft: PlanDraft,
        timeout?: number
    ): Promise<PlanApprovalResponse> {
        return new Promise((resolve, reject) => {
            // 更新状态
            draft.status = 'pending_approval';
            draft.updatedAt = Date.now();
            this.pendingPlans.set(draft.draftId, draft);

            // 设置超时
            const timeoutMs = timeout ?? this.config.defaultTimeout;
            let timeoutId: NodeJS.Timeout | undefined;

            if (timeoutMs > 0) {
                timeoutId = setTimeout(() => {
                    this.approvalCallbacks.delete(draft.draftId);
                    this.emitPlanEvent('plan.expired', draft);
                    reject(new Error(`Plan approval timeout after ${timeoutMs}ms`));
                }, timeoutMs);
            }

            // 存储回调
            this.approvalCallbacks.set(draft.draftId, {
                resolve,
                reject,
                timeoutId,
            });

            // 发送审批请求事件
            const request: PlanApprovalRequest = {
                taskId,
                draftId: draft.draftId,
                plan: draft,
                prompt: this.generateApprovalPrompt(draft),
                timeout: timeoutMs,
            };

            this.emitPlanEvent('plan.approval_required', draft, request);

            console.log(`[PlanConfirmationManager] Submitted draft ${draft.draftId} for approval`);
        });
    }

    /**
     * 处理用户审批响应
     */
    handleApprovalResponse(draftId: string, response: PlanApprovalResponse): void {
        const callback = this.approvalCallbacks.get(draftId);
        if (!callback) {
            console.warn(`[PlanConfirmationManager] No pending approval for draft ${draftId}`);
            return;
        }

        // 清除超时
        if (callback.timeoutId) {
            clearTimeout(callback.timeoutId);
        }

        // 更新草案状态
        const draft = this.pendingPlans.get(draftId);
        if (draft) {
            if (response.approved) {
                draft.status = 'approved';
                this.emitPlanEvent('plan.approved', draft, response);
            } else {
                draft.status = 'rejected';
                draft.userFeedback = response.feedback;
                this.emitPlanEvent('plan.rejected', draft, response);
            }
            draft.updatedAt = Date.now();
            this.addToHistory(draftId, draft);
        }

        // 移除回调
        this.approvalCallbacks.delete(draftId);

        // resolve Promise
        callback.resolve(response);

        console.log(`[PlanConfirmationManager] Processed approval for ${draftId}: ${response.approved ? 'approved' : 'rejected'}`);
    }

    /**
     * 获取待审批计划
     */
    getPendingPlan(taskId: string): PlanDraft | undefined {
        for (const draft of this.pendingPlans.values()) {
            if (draft.taskId === taskId && draft.status === 'pending_approval') {
                return draft;
            }
        }
        return undefined;
    }

    /**
     * 根据草案 ID 获取计划
     */
    getDraft(draftId: string): PlanDraft | undefined {
        return this.pendingPlans.get(draftId);
    }

    /**
     * 更新计划版本
     */
    updatePlan(
        draftId: string,
        modifications: Partial<ExecutionPlan> & { userFeedback?: string }
    ): PlanDraft | null {
        const draft = this.pendingPlans.get(draftId);
        if (!draft) {
            console.warn(`[PlanConfirmationManager] Draft ${draftId} not found`);
            return null;
        }

        // 创建新版本
        const updatedDraft: PlanDraft = {
            ...draft,
            ...modifications,
            status: 'modified',
            version: draft.version + 1,
            updatedAt: Date.now(),
        };

        // 重新计算预估时间
        if (modifications.steps) {
            updatedDraft.estimatedDuration = this.estimateDuration(modifications.steps);
        }

        // 存储更新
        this.pendingPlans.set(draftId, updatedDraft);
        this.addToHistory(draftId, updatedDraft);

        // 发送修改事件
        this.emitPlanEvent('plan.modified', updatedDraft);

        console.log(`[PlanConfirmationManager] Updated draft ${draftId} to version ${updatedDraft.version}`);

        return updatedDraft;
    }

    /**
     * 取消待审批计划
     */
    cancelApproval(draftId: string, reason?: string): void {
        const callback = this.approvalCallbacks.get(draftId);
        if (callback) {
            if (callback.timeoutId) {
                clearTimeout(callback.timeoutId);
            }
            callback.reject(new Error(reason || 'Approval cancelled'));
            this.approvalCallbacks.delete(draftId);
        }

        const draft = this.pendingPlans.get(draftId);
        if (draft) {
            draft.status = 'rejected';
            draft.userFeedback = reason;
            draft.updatedAt = Date.now();
        }
    }

    /**
     * 获取计划版本历史
     */
    getVersionHistory(draftId: string): PlanDraft[] {
        return this.planHistory.get(draftId) || [];
    }

    /**
     * 清理过期计划
     */
    cleanup(maxAge: number = 24 * 60 * 60 * 1000): void {
        const now = Date.now();
        for (const [draftId, draft] of this.pendingPlans.entries()) {
            if (now - draft.createdAt > maxAge) {
                this.cancelApproval(draftId, 'Expired');
                this.pendingPlans.delete(draftId);
                this.planHistory.delete(draftId);
            }
        }
    }

    // =========================================================================
    // 私有辅助方法
    // =========================================================================

    /**
     * 估算执行时间
     */
    private estimateDuration(steps: ExecutionStep[]): number {
        // 基础估算：每步 5 秒，视觉任务额外 10 秒
        let total = 0;
        for (const step of steps) {
            total += step.requiresVision ? 15000 : 5000;
        }
        return total;
    }

    /**
     * 自动评估风险
     */
    private assessRisks(plan: ExecutionPlan): PlanRisk[] {
        const risks: PlanRisk[] = [];

        // 检查步骤数量
        if (plan.steps.length > 10) {
            risks.push({
                level: 'medium',
                description: `计划包含 ${plan.steps.length} 个步骤，执行时间可能较长`,
                mitigation: '建议分批执行或简化任务',
            });
        }

        // 检查视觉任务
        const visionSteps = plan.steps.filter(s => s.requiresVision);
        if (visionSteps.length > 0) {
            risks.push({
                level: 'low',
                description: `包含 ${visionSteps.length} 个视觉分析步骤`,
            });
        }

        // 检查文件操作
        const fileOps = plan.steps.filter(s =>
            s.action.includes('file') || s.action.includes('delete')
        );
        if (fileOps.length > 0) {
            risks.push({
                level: 'high',
                description: `包含 ${fileOps.length} 个文件操作，可能影响数据`,
                mitigation: '请确认操作目标正确',
            });
        }

        return risks;
    }

    /**
     * 提取所需权限
     */
    private extractRequiredPermissions(steps: ExecutionStep[]): string[] {
        const permissions = new Set<string>();

        for (const step of steps) {
            // 根据 action 推断所需权限
            if (step.action.includes('file')) {
                permissions.add('filesystem');
            }
            if (step.action.includes('browser') || step.action.includes('web')) {
                permissions.add('network');
            }
            if (step.action.includes('shell') || step.action.includes('exec')) {
                permissions.add('execute');
            }
            if (step.requiresVision) {
                permissions.add('screen_capture');
            }
        }

        return Array.from(permissions);
    }

    /**
     * 生成计划摘要
     */
    private generateSummary(plan: ExecutionPlan): string {
        if (plan.steps.length === 0) {
            return plan.goal;
        }
        return `${plan.goal}（共 ${plan.steps.length} 个步骤）`;
    }

    /**
     * 生成审批提示
     */
    private generateApprovalPrompt(draft: PlanDraft): string {
        let prompt = `请确认以下执行计划：\n\n`;
        prompt += `**目标**: ${draft.goal}\n`;
        prompt += `**步骤数**: ${draft.steps.length}\n`;
        prompt += `**预估时间**: ${Math.ceil(draft.estimatedDuration / 1000)}秒\n`;

        if (draft.risks.length > 0) {
            const highRisks = draft.risks.filter(r => r.level === 'high');
            if (highRisks.length > 0) {
                prompt += `\n⚠️ **注意**: 存在 ${highRisks.length} 个高风险项\n`;
            }
        }

        return prompt;
    }

    /**
     * 添加到版本历史
     */
    private addToHistory(draftId: string, draft: PlanDraft): void {
        let history = this.planHistory.get(draftId);
        if (!history) {
            history = [];
            this.planHistory.set(draftId, history);
        }

        history.push({ ...draft });

        // 限制历史数量
        if (history.length > this.config.maxVersionHistory) {
            history.shift();
        }
    }

    /**
     * 发送计划事件
     */
    private emitPlanEvent(
        type: PlanEventType,
        draft: PlanDraft,
        data?: PlanApprovalRequest | PlanApprovalResponse
    ): void {
        const event: PlanEvent = {
            type,
            taskId: draft.taskId,
            draftId: draft.draftId,
            timestamp: Date.now(),
            data: data || draft,
        };

        this.emit(type, event);
        this.emit('plan', event);
    }
}
