/**
 * CheckpointManager - 检查点管理器
 * 用于保存和恢复任务执行状态
 */

import type Database from 'better-sqlite3';
import type { CheckpointState } from './types.js';

/**
 * 检查点管理器
 */
export class CheckpointManager {
    private db: Database.Database;

    constructor(db: Database.Database) {
        this.db = db;
        this.initTable();
    }

    /**
     * 初始化表结构
     */
    private initTable(): void {
        this.db.exec(`
            CREATE TABLE IF NOT EXISTS checkpoints (
                task_id TEXT PRIMARY KEY,
                step_index INTEGER DEFAULT 0,
                total_steps INTEGER DEFAULT 0,
                completed_results TEXT,
                context TEXT,
                created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
                updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
            );
            CREATE INDEX IF NOT EXISTS idx_checkpoints_updated_at ON checkpoints(updated_at);
        `);
    }

    /**
     * 保存检查点
     */
    save(state: CheckpointState): void {
        const now = Date.now();

        this.db.prepare(`
            INSERT INTO checkpoints (task_id, step_index, total_steps, completed_results, context, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                step_index = excluded.step_index,
                total_steps = excluded.total_steps,
                completed_results = excluded.completed_results,
                context = excluded.context,
                updated_at = excluded.updated_at
        `).run(
            state.taskId,
            state.stepIndex,
            state.totalSteps,
            JSON.stringify(state.completedResults),
            JSON.stringify(state.context),
            state.createdAt || now,
            now
        );

        console.log(`[CheckpointManager] Saved checkpoint for task ${state.taskId} at step ${state.stepIndex}/${state.totalSteps}`);
    }

    /**
     * 加载检查点
     */
    load(taskId: string): CheckpointState | null {
        const row = this.db.prepare(`
            SELECT * FROM checkpoints WHERE task_id = ?
        `).get(taskId) as any;

        if (!row) return null;

        return {
            taskId: row.task_id,
            stepIndex: row.step_index,
            totalSteps: row.total_steps,
            completedResults: JSON.parse(row.completed_results || '[]'),
            context: JSON.parse(row.context || '{}'),
            createdAt: row.created_at,
            updatedAt: row.updated_at,
        };
    }

    /**
     * 检查是否存在检查点
     */
    exists(taskId: string): boolean {
        const row = this.db.prepare(`
            SELECT 1 FROM checkpoints WHERE task_id = ?
        `).get(taskId);
        return !!row;
    }

    /**
     * 删除检查点
     */
    delete(taskId: string): boolean {
        const result = this.db.prepare(`
            DELETE FROM checkpoints WHERE task_id = ?
        `).run(taskId);
        return result.changes > 0;
    }

    /**
     * 更新步骤进度
     */
    updateProgress(taskId: string, stepIndex: number, stepResult?: unknown): boolean {
        const existing = this.load(taskId);
        if (!existing) return false;

        const completedResults = [...existing.completedResults];
        if (stepResult !== undefined) {
            completedResults.push({
                stepId: stepIndex,
                result: stepResult,
                timestamp: Date.now(),
            });
        }

        this.save({
            ...existing,
            stepIndex,
            completedResults,
            updatedAt: Date.now(),
        });

        return true;
    }

    /**
     * 创建新检查点
     */
    create(taskId: string, totalSteps: number, context: Record<string, unknown> = {}): CheckpointState {
        const state: CheckpointState = {
            taskId,
            stepIndex: 0,
            totalSteps,
            completedResults: [],
            context,
            createdAt: Date.now(),
            updatedAt: Date.now(),
        };

        this.save(state);
        return state;
    }

    /**
     * 清理过期检查点
     */
    cleanup(maxAge: number = 24 * 3600 * 1000): number {
        const cutoff = Date.now() - maxAge;
        const result = this.db.prepare(`
            DELETE FROM checkpoints WHERE updated_at < ?
        `).run(cutoff);

        if (result.changes > 0) {
            console.log(`[CheckpointManager] Cleaned up ${result.changes} old checkpoints`);
        }

        return result.changes;
    }

    /**
     * 获取所有未完成的检查点
     */
    getIncomplete(): CheckpointState[] {
        const rows = this.db.prepare(`
            SELECT * FROM checkpoints WHERE step_index < total_steps
            ORDER BY updated_at DESC
        `).all() as any[];

        return rows.map(row => ({
            taskId: row.task_id,
            stepIndex: row.step_index,
            totalSteps: row.total_steps,
            completedResults: JSON.parse(row.completed_results || '[]'),
            context: JSON.parse(row.context || '{}'),
            createdAt: row.created_at,
            updatedAt: row.updated_at,
        }));
    }
}
