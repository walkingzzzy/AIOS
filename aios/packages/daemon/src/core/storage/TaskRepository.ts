/**
 * TaskRepository - 任务存储仓库
 */

import type Database from 'better-sqlite3';
import type {
    TaskRecord,
    StoredTaskStatus,
    PaginationOptions,
    PaginatedResult,
} from './types.js';

/**
 * 任务查询选项
 */
export interface TaskQueryOptions extends PaginationOptions {
    sessionId?: string;
    status?: StoredTaskStatus;
    type?: string;
    startTime?: number;
    endTime?: number;
}

/**
 * 任务存储仓库
 */
export class TaskRepository {
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
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                type TEXT,
                prompt TEXT,
                status TEXT DEFAULT 'pending',
                tier TEXT,
                response TEXT,
                error TEXT,
                model TEXT,
                execution_time INTEGER,
                metadata TEXT,
                created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
                started_at INTEGER,
                completed_at INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_session_id ON tasks(session_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
        `);
    }

    /**
     * 生成任务 ID
     */
    private generateId(): string {
        return `task_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * 创建任务
     */
    create(sessionId: string, prompt: string, type: string = 'simple', metadata?: Record<string, unknown>): TaskRecord {
        const id = this.generateId();
        const now = Date.now();

        this.db.prepare(`
            INSERT INTO tasks (id, session_id, type, prompt, status, metadata, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
        `).run(id, sessionId, type, prompt, metadata ? JSON.stringify(metadata) : null, now);

        return {
            id,
            sessionId,
            type,
            prompt,
            status: 'pending',
            metadata,
            createdAt: now,
        };
    }

    /**
     * 获取任务
     */
    get(id: string): TaskRecord | null {
        const row = this.db.prepare(`
            SELECT * FROM tasks WHERE id = ?
        `).get(id) as any;

        if (!row) return null;

        return this.mapRow(row);
    }

    /**
     * 更新任务状态
     */
    updateStatus(
        id: string,
        status: StoredTaskStatus,
        updates?: Partial<Pick<TaskRecord, 'tier' | 'response' | 'error' | 'model' | 'executionTime'>>
    ): boolean {
        const setClauses: string[] = ['status = ?'];
        const values: unknown[] = [status];
        const now = Date.now();

        if (status === 'running') {
            setClauses.push('started_at = ?');
            values.push(now);
        }
        if (status === 'completed' || status === 'failed' || status === 'cancelled') {
            setClauses.push('completed_at = ?');
            values.push(now);
        }

        if (updates) {
            if (updates.tier !== undefined) {
                setClauses.push('tier = ?');
                values.push(updates.tier);
            }
            if (updates.response !== undefined) {
                setClauses.push('response = ?');
                values.push(updates.response);
            }
            if (updates.error !== undefined) {
                setClauses.push('error = ?');
                values.push(updates.error);
            }
            if (updates.model !== undefined) {
                setClauses.push('model = ?');
                values.push(updates.model);
            }
            if (updates.executionTime !== undefined) {
                setClauses.push('execution_time = ?');
                values.push(updates.executionTime);
            }
        }

        values.push(id);

        const result = this.db.prepare(`
            UPDATE tasks SET ${setClauses.join(', ')} WHERE id = ?
        `).run(...values);

        return result.changes > 0;
    }

    /**
     * 删除任务
     */
    delete(id: string): boolean {
        const result = this.db.prepare('DELETE FROM tasks WHERE id = ?').run(id);
        return result.changes > 0;
    }

    /**
     * 查询任务列表
     */
    query(options: TaskQueryOptions = {}): PaginatedResult<TaskRecord> {
        const page = options.page ?? 1;
        const pageSize = options.pageSize ?? 20;
        const orderBy = options.orderBy ?? 'created_at';
        const orderDir = options.orderDir ?? 'desc';

        let whereClause = '1=1';
        const params: unknown[] = [];

        if (options.sessionId) {
            whereClause += ' AND session_id = ?';
            params.push(options.sessionId);
        }
        if (options.status) {
            whereClause += ' AND status = ?';
            params.push(options.status);
        }
        if (options.type) {
            whereClause += ' AND type = ?';
            params.push(options.type);
        }
        if (options.startTime) {
            whereClause += ' AND created_at >= ?';
            params.push(options.startTime);
        }
        if (options.endTime) {
            whereClause += ' AND created_at <= ?';
            params.push(options.endTime);
        }

        // 获取总数
        const countRow = this.db.prepare(`
            SELECT COUNT(*) as count FROM tasks WHERE ${whereClause}
        `).get(...params) as { count: number };
        const total = countRow.count;

        // 获取数据
        const offset = (page - 1) * pageSize;
        const rows = this.db.prepare(`
            SELECT * FROM tasks
            WHERE ${whereClause}
            ORDER BY ${orderBy} ${orderDir}
            LIMIT ? OFFSET ?
        `).all(...params, pageSize, offset) as any[];

        return {
            data: rows.map(row => this.mapRow(row)),
            total,
            page,
            pageSize,
            totalPages: Math.ceil(total / pageSize),
        };
    }

    /**
     * 获取会话的所有任务
     */
    getBySession(sessionId: string, limit?: number): TaskRecord[] {
        let sql = `
            SELECT * FROM tasks
            WHERE session_id = ?
            ORDER BY created_at DESC
        `;
        const params: unknown[] = [sessionId];

        if (limit) {
            sql += ' LIMIT ?';
            params.push(limit);
        }

        const rows = this.db.prepare(sql).all(...params) as any[];
        return rows.map(row => this.mapRow(row));
    }

    /**
     * 获取任务统计
     */
    getStats(sessionId?: string): { total: number; completed: number; failed: number; avgTime: number } {
        let whereClause = '1=1';
        const params: unknown[] = [];

        if (sessionId) {
            whereClause += ' AND session_id = ?';
            params.push(sessionId);
        }

        const row = this.db.prepare(`
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                AVG(CASE WHEN execution_time IS NOT NULL THEN execution_time ELSE NULL END) as avg_time
            FROM tasks
            WHERE ${whereClause}
        `).get(...params) as any;

        return {
            total: row.total || 0,
            completed: row.completed || 0,
            failed: row.failed || 0,
            avgTime: row.avg_time || 0,
        };
    }

    /**
     * 映射数据库行到记录
     */
    private mapRow(row: any): TaskRecord {
        return {
            id: row.id,
            sessionId: row.session_id,
            type: row.type,
            prompt: row.prompt,
            status: row.status,
            tier: row.tier,
            response: row.response,
            error: row.error,
            model: row.model,
            executionTime: row.execution_time,
            metadata: row.metadata ? JSON.parse(row.metadata) : undefined,
            createdAt: row.created_at,
            startedAt: row.started_at,
            completedAt: row.completed_at,
        };
    }
}
