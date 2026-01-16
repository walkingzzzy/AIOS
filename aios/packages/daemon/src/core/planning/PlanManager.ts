/**
 * PlanManager - 计划管理器
 * 负责计划的创建、持久化、状态管理
 */

import { writeFileSync, readFileSync, existsSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import type {
    TaskPlan,
    PlanStep,
    StepStatus,
    KnownIssue,
    DecompositionResult,
} from './types.js';

/**
 * 计划管理器配置
 */
export interface PlanManagerConfig {
    /** 计划文件目录 */
    planDir?: string;
    /** 是否启用文件持久化 */
    enableFilePersistence?: boolean;
}

/**
 * 计划管理器
 */
export class PlanManager {
    /** 内存中的计划缓存 */
    private plans: Map<string, TaskPlan> = new Map();

    /** 配置 */
    private config: Required<PlanManagerConfig>;

    constructor(config: PlanManagerConfig = {}) {
        this.config = {
            planDir: config.planDir ?? '.aios',
            enableFilePersistence: config.enableFilePersistence ?? true,
        };
    }

    /**
     * 获取或创建计划
     */
    getOrCreatePlan(taskId: string, goal: string, steps?: PlanStep[]): TaskPlan {
        // 尝试从缓存获取
        let plan = this.plans.get(taskId);
        if (plan) return plan;

        // 尝试从文件加载
        if (this.config.enableFilePersistence) {
            const loadedPlan = this.loadFromFile(taskId);
            if (loadedPlan) {
                this.plans.set(taskId, loadedPlan);
                return loadedPlan;
            }
        }

        // 创建新计划
        plan = this.createPlan(taskId, goal, steps);
        this.plans.set(taskId, plan);

        if (this.config.enableFilePersistence) {
            this.saveToFile(plan);
        }

        return plan;
    }

    /**
     * 创建新计划
     */
    createPlan(taskId: string, goal: string, steps?: PlanStep[]): TaskPlan {
        const now = Date.now();
        const plan: TaskPlan = {
            taskId,
            goal,
            steps: steps ?? [],
            currentStepIndex: 0,
            knownIssues: [],
            context: {},
            createdAt: now,
            updatedAt: now,
        };

        console.log(`[PlanManager] Created plan for task ${taskId}: "${goal}"`);
        return plan;
    }

    /**
     * 获取计划
     */
    getPlan(taskId: string): TaskPlan | null {
        return this.plans.get(taskId) ?? null;
    }

    /**
     * 更新计划步骤
     */
    updateStep(taskId: string, stepId: number, updates: Partial<PlanStep>): boolean {
        const plan = this.plans.get(taskId);
        if (!plan) return false;

        const step = plan.steps.find(s => s.id === stepId);
        if (!step) return false;

        Object.assign(step, updates);
        plan.updatedAt = Date.now();

        if (this.config.enableFilePersistence) {
            this.saveToFile(plan);
        }

        return true;
    }

    /**
     * 完成步骤
     */
    completeStep(taskId: string, stepId: number, result?: string): boolean {
        const updated = this.updateStep(taskId, stepId, {
            status: 'completed',
            result,
            completedAt: Date.now(),
        });

        if (updated) {
            const plan = this.plans.get(taskId)!;
            // 移动到下一个待执行步骤
            this.advanceToNextStep(plan);
            console.log(`[PlanManager] Completed step ${stepId} for task ${taskId}`);
        }

        return updated;
    }

    /**
     * 标记步骤失败
     */
    failStep(taskId: string, stepId: number, error: string): boolean {
        return this.updateStep(taskId, stepId, {
            status: 'failed',
            error,
            completedAt: Date.now(),
        });
    }

    /**
     * 开始步骤
     */
    startStep(taskId: string, stepId: number): boolean {
        return this.updateStep(taskId, stepId, {
            status: 'in_progress',
            startedAt: Date.now(),
        });
    }

    /**
     * 添加问题
     */
    addIssue(taskId: string, description: string, severity: KnownIssue['severity'] = 'medium'): boolean {
        const plan = this.plans.get(taskId);
        if (!plan) return false;

        const id = plan.knownIssues.length + 1;
        plan.knownIssues.push({
            id,
            description,
            severity,
            resolved: false,
        });
        plan.updatedAt = Date.now();

        if (this.config.enableFilePersistence) {
            this.saveToFile(plan);
        }

        console.log(`[PlanManager] Added issue #${id} to task ${taskId}: ${description}`);
        return true;
    }

    /**
     * 解决问题
     */
    resolveIssue(taskId: string, issueId: number, resolution: string): boolean {
        const plan = this.plans.get(taskId);
        if (!plan) return false;

        const issue = plan.knownIssues.find(i => i.id === issueId);
        if (!issue) return false;

        issue.resolved = true;
        issue.resolution = resolution;
        plan.updatedAt = Date.now();

        if (this.config.enableFilePersistence) {
            this.saveToFile(plan);
        }

        return true;
    }

    /**
     * 获取计划摘要
     */
    getPlanSummary(taskId: string): string {
        const plan = this.plans.get(taskId);
        if (!plan) return '';

        const completed = plan.steps.filter(s => s.status === 'completed').length;
        const failed = plan.steps.filter(s => s.status === 'failed').length;
        const pending = plan.steps.filter(s => s.status === 'pending').length;
        const openIssues = plan.knownIssues.filter(i => !i.resolved).length;

        return `Goal: ${plan.goal}
Progress: ${completed}/${plan.steps.length} steps completed
Failed: ${failed}, Pending: ${pending}
Open Issues: ${openIssues}
Current Step: ${plan.currentStepIndex < plan.steps.length
                ? plan.steps[plan.currentStepIndex].description
                : 'All steps completed'}`;
    }

    /**
     * 生成 PLAN.md 格式
     */
    toPlanMarkdown(taskId: string): string {
        const plan = this.plans.get(taskId);
        if (!plan) return '';

        const lines: string[] = [
            `# Task Plan: ${plan.goal}`,
            '',
            `> Task ID: ${plan.taskId}`,
            `> Created: ${new Date(plan.createdAt).toISOString()}`,
            `> Updated: ${new Date(plan.updatedAt).toISOString()}`,
            '',
            '## Steps',
            '',
        ];

        for (const step of plan.steps) {
            const marker = this.getStepMarker(step.status);
            lines.push(`${marker} ${step.id}. ${step.description}`);
            if (step.result) {
                lines.push(`   - Result: ${step.result}`);
            }
            if (step.error) {
                lines.push(`   - Error: ${step.error}`);
            }
        }

        if (plan.knownIssues.length > 0) {
            lines.push('', '## Known Issues', '');
            for (const issue of plan.knownIssues) {
                const marker = issue.resolved ? '[x]' : '[ ]';
                lines.push(`${marker} **${issue.severity.toUpperCase()}**: ${issue.description}`);
                if (issue.resolution) {
                    lines.push(`   - Resolution: ${issue.resolution}`);
                }
            }
        }

        return lines.join('\n');
    }

    /**
     * 移动到下一个步骤
     */
    private advanceToNextStep(plan: TaskPlan): void {
        for (let i = plan.currentStepIndex; i < plan.steps.length; i++) {
            if (plan.steps[i].status === 'pending') {
                plan.currentStepIndex = i;
                return;
            }
        }
        // 所有步骤已完成
        plan.currentStepIndex = plan.steps.length;
    }

    /**
     * 获取步骤状态标记
     */
    private getStepMarker(status: StepStatus): string {
        switch (status) {
            case 'completed': return '- [x]';
            case 'failed': return '- [!]';
            case 'in_progress': return '- [/]';
            case 'skipped': return '- [-]';
            default: return '- [ ]';
        }
    }

    /**
     * 获取计划文件路径
     */
    private getPlanFilePath(taskId: string): string {
        return join(this.config.planDir, `PLAN_${taskId}.md`);
    }

    /**
     * 保存到文件
     */
    private saveToFile(plan: TaskPlan): void {
        try {
            const filePath = this.getPlanFilePath(plan.taskId);
            const dir = dirname(filePath);

            if (!existsSync(dir)) {
                mkdirSync(dir, { recursive: true });
            }

            const content = this.toPlanMarkdown(plan.taskId);
            writeFileSync(filePath, content, 'utf-8');
            console.log(`[PlanManager] Saved plan to ${filePath}`);
        } catch (error) {
            console.error(`[PlanManager] Failed to save plan:`, error);
        }
    }

    /**
     * 从文件加载
     */
    private loadFromFile(taskId: string): TaskPlan | null {
        try {
            const filePath = this.getPlanFilePath(taskId);
            if (!existsSync(filePath)) return null;

            // 简单实现：这里可以解析 markdown 恢复状态
            // 但为了简化，我们只从内存/数据库加载
            console.log(`[PlanManager] Plan file exists: ${filePath}`);
            return null;
        } catch (error) {
            return null;
        }
    }

    /**
     * 删除计划
     */
    deletePlan(taskId: string): boolean {
        return this.plans.delete(taskId);
    }

    /**
     * 获取所有活跃计划
     */
    getActivePlans(): TaskPlan[] {
        return Array.from(this.plans.values())
            .filter(p => p.currentStepIndex < p.steps.length);
    }
}
