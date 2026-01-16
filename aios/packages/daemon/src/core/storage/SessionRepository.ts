/**
 * SessionRepository - 会话存储仓库
 */

import type Database from 'better-sqlite3';
import type {
    SessionRecord,
    SessionStatus,
    PaginationOptions,
    PaginatedResult,
} from './types.js';

/**
 * 会话查询选项
 */
export interface SessionQueryOptions extends PaginationOptions {
    status?: SessionStatus;
    startTime?: number;
    endTime?: number;
}

/**
 * 会话存储仓库
 */
export class SessionRepository {
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
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                status TEXT DEFAULT 'active',
                metadata TEXT,
                created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
                updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
            CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);
        `);
    }

    /**
     * 生成会话 ID
     */
    private generateId(): string {
        return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * 创建会话
     */
    create(title?: string, metadata?: Record<string, unknown>): SessionRecord {
        const id = this.generateId();
        const now = Date.now();

        this.db.prepare(`
            INSERT INTO sessions (id, title, status, metadata, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?, ?)
        `).run(id, title || null, metadata ? JSON.stringify(metadata) : null, now, now);

        return {
            id,
            title,
            status: 'active',
            metadata,
            createdAt: now,
            updatedAt: now,
        };
    }

    /**
     * 获取会话
     */
    get(id: string): SessionRecord | null {
        const row = this.db.prepare(`
            SELECT id, title, status, metadata, created_at, updated_at
            FROM sessions WHERE id = ?
        `).get(id) as any;

        if (!row) return null;

        return this.mapRow(row);
    }

    /**
     * 更新会话
     */
    update(id: string, updates: Partial<Pick<SessionRecord, 'title' | 'status' | 'metadata'>>): boolean {
        const setClauses: string[] = ['updated_at = ?'];
        const values: unknown[] = [Date.now()];

        if (updates.title !== undefined) {
            setClauses.push('title = ?');
            values.push(updates.title);
        }
        if (updates.status !== undefined) {
            setClauses.push('status = ?');
            values.push(updates.status);
        }
        if (updates.metadata !== undefined) {
            setClauses.push('metadata = ?');
            values.push(JSON.stringify(updates.metadata));
        }

        values.push(id);

        const result = this.db.prepare(`
            UPDATE sessions SET ${setClauses.join(', ')} WHERE id = ?
        `).run(...values);

        return result.changes > 0;
    }

    /**
     * 删除会话
     */
    delete(id: string): boolean {
        const result = this.db.prepare('DELETE FROM sessions WHERE id = ?').run(id);
        return result.changes > 0;
    }

    /**
     * 查询会话列表
     */
    query(options: SessionQueryOptions = {}): PaginatedResult<SessionRecord> {
        const page = options.page ?? 1;
        const pageSize = options.pageSize ?? 20;
        const orderBy = options.orderBy ?? 'created_at';
        const orderDir = options.orderDir ?? 'desc';

        let whereClause = '1=1';
        const params: unknown[] = [];

        if (options.status) {
            whereClause += ' AND status = ?';
            params.push(options.status);
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
            SELECT COUNT(*) as count FROM sessions WHERE ${whereClause}
        `).get(...params) as { count: number };
        const total = countRow.count;

        // 获取数据
        const offset = (page - 1) * pageSize;
        const rows = this.db.prepare(`
            SELECT id, title, status, metadata, created_at, updated_at
            FROM sessions
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
     * 获取最近的会话
     */
    getRecent(limit: number = 10): SessionRecord[] {
        const rows = this.db.prepare(`
            SELECT id, title, status, metadata, created_at, updated_at
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ?
        `).all(limit) as any[];

        return rows.map(row => this.mapRow(row));
    }

    /**
     * 获取活跃会话
     */
    getActive(): SessionRecord | null {
        const row = this.db.prepare(`
            SELECT id, title, status, metadata, created_at, updated_at
            FROM sessions
            WHERE status = 'active'
            ORDER BY updated_at DESC
            LIMIT 1
        `).get() as any;

        return row ? this.mapRow(row) : null;
    }

    /**
     * 清理过期会话
     */
    cleanupExpired(maxAge: number = 7 * 24 * 3600 * 1000): number {
        const cutoff = Date.now() - maxAge;
        const result = this.db.prepare(`
            UPDATE sessions SET status = 'expired'
            WHERE status = 'active' AND updated_at < ?
        `).run(cutoff);
        return result.changes;
    }

    /**
     * 映射数据库行到记录
     */
    private mapRow(row: any): SessionRecord {
        return {
            id: row.id,
            title: row.title,
            status: row.status,
            metadata: row.metadata ? JSON.parse(row.metadata) : undefined,
            createdAt: row.created_at,
            updatedAt: row.updated_at,
        };
    }
}
