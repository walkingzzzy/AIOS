/**
 * TaskDecomposer - 任务分解器
 * 将复杂任务分解为可并行执行的子任务
 */

import type { SubTask, TaskDecomposition } from './types.js';

/**
 * 任务分解器
 */
export class TaskDecomposer {
    private taskCounter: number = 0;

    /**
     * 生成子任务 ID
     */
    private generateSubTaskId(): string {
        return `subtask_${Date.now()}_${++this.taskCounter}`;
    }

    /**
     * 分解任务
     */
    decompose(task: string, hints?: string[]): TaskDecomposition {
        // 简单的规则分解（实际应用中可以使用 AI）
        const subTasks = this.extractSubTasks(task, hints);
        const strategy = this.determineStrategy(subTasks);
        const estimatedTotalTime = this.estimateTotalTime(subTasks, strategy);

        console.log(`[TaskDecomposer] Decomposed task into ${subTasks.length} subtasks (${strategy})`);

        return {
            originalTask: task,
            subTasks,
            strategy,
            estimatedTotalTime,
        };
    }

    /**
     * 提取子任务
     */
    private extractSubTasks(task: string, hints?: string[]): SubTask[] {
        const subTasks: SubTask[] = [];

        // 如果提供了提示，使用提示作为子任务
        if (hints && hints.length > 0) {
            for (const hint of hints) {
                subTasks.push({
                    id: this.generateSubTaskId(),
                    description: hint,
                    status: 'pending',
                    params: { originalTask: task },
                    estimatedTime: 5000,
                });
            }
            return subTasks;
        }

        // 基于关键词的简单分解
        const keywords = ['分析', '创建', '修改', '删除', '检查', '搜索', '生成', '优化'];
        const steps = this.splitByKeywords(task, keywords);

        if (steps.length > 1) {
            let prevId: string | undefined;
            for (const step of steps) {
                const id = this.generateSubTaskId();
                subTasks.push({
                    id,
                    description: step,
                    status: 'pending',
                    dependencies: prevId ? [prevId] : undefined,
                    params: { originalTask: task },
                    estimatedTime: 5000,
                });
                prevId = id;
            }
        } else {
            // 默认三步分解
            const analyzeId = this.generateSubTaskId();
            const executeId = this.generateSubTaskId();
            const verifyId = this.generateSubTaskId();

            subTasks.push(
                {
                    id: analyzeId,
                    description: `分析任务需求: ${task}`,
                    status: 'pending',
                    params: { phase: 'analyze' },
                    estimatedTime: 3000,
                },
                {
                    id: executeId,
                    description: `执行核心操作`,
                    status: 'pending',
                    dependencies: [analyzeId],
                    params: { phase: 'execute' },
                    estimatedTime: 10000,
                },
                {
                    id: verifyId,
                    description: `验证执行结果`,
                    status: 'pending',
                    dependencies: [executeId],
                    params: { phase: 'verify' },
                    estimatedTime: 2000,
                }
            );
        }

        return subTasks;
    }

    /**
     * 按关键词拆分任务
     */
    private splitByKeywords(task: string, keywords: string[]): string[] {
        const parts: string[] = [];
        let remaining = task;

        for (const keyword of keywords) {
            const index = remaining.indexOf(keyword);
            if (index > 0) {
                const before = remaining.substring(0, index).trim();
                if (before) parts.push(before);
                remaining = remaining.substring(index);
            }
        }

        if (remaining.trim()) {
            parts.push(remaining.trim());
        }

        return parts.length > 0 ? parts : [task];
    }

    /**
     * 确定执行策略
     */
    private determineStrategy(subTasks: SubTask[]): 'sequential' | 'parallel' | 'mixed' {
        // 检查是否有依赖关系
        const hasDependencies = subTasks.some(t => t.dependencies && t.dependencies.length > 0);

        if (!hasDependencies) {
            return 'parallel';
        }

        // 检查是否所有任务都是顺序依赖
        const isFullySequential = subTasks.every((t, idx) =>
            idx === 0 || (t.dependencies?.length === 1 && t.dependencies[0] === subTasks[idx - 1].id)
        );

        return isFullySequential ? 'sequential' : 'mixed';
    }

    /**
     * 估算总时间
     */
    private estimateTotalTime(subTasks: SubTask[], strategy: string): number {
        const times = subTasks.map(t => t.estimatedTime ?? 5000);

        if (strategy === 'parallel') {
            return Math.max(...times);
        } else if (strategy === 'sequential') {
            return times.reduce((a, b) => a + b, 0);
        } else {
            // mixed: 取中间值
            return times.reduce((a, b) => a + b, 0) / 2;
        }
    }

    /**
     * 获取可执行的子任务（依赖已满足）
     */
    getExecutableSubTasks(subTasks: SubTask[]): SubTask[] {
        const completedIds = new Set(
            subTasks.filter(t => t.status === 'completed').map(t => t.id)
        );

        return subTasks.filter(task => {
            if (task.status !== 'pending') return false;
            if (!task.dependencies || task.dependencies.length === 0) return true;
            return task.dependencies.every(depId => completedIds.has(depId));
        });
    }
}
