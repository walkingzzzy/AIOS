/**
 * MessageRepository - 消息存储仓库
 */

import type Database from 'better-sqlite3';
import type {
    MessageRecord,
    MessageRole,
    PaginationOptions,
    PaginatedResult,
} from './types.js';

/**
 * 消息查询选项
 */
export interface MessageQueryOptions extends PaginationOptions {
    sessionId?: string;
    taskId?: string;
    role?: MessageRole;
    startTime?: number;
    endTime?: number;
}

/**
 * 消息存储仓库
 */
export class MessageRepository {
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
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                task_id TEXT,
                role TEXT,
                content TEXT,
                metadata TEXT,
                created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_task_id ON messages(task_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
        `);
    }

    /**
     * 生成消息 ID
     */
    private generateId(): string {
        return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * 创建消息
     */
    create(
        sessionId: string,
        role: MessageRole,
        content: string,
        taskId?: string,
        metadata?: Record<string, unknown>
    ): MessageRecord {
        const id = this.generateId();
        const now = Date.now();

        this.db.prepare(`
            INSERT INTO messages (id, session_id, task_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        `).run(id, sessionId, taskId || null, role, content, metadata ? JSON.stringify(metadata) : null, now);

        return {
            id,
            sessionId,
            taskId,
            role,
            content,
            metadata,
            createdAt: now,
        };
    }

    /**
     * 获取消息
     */
    get(id: string): MessageRecord | null {
        const row = this.db.prepare(`
            SELECT * FROM messages WHERE id = ?
        `).get(id) as any;

        if (!row) return null;

        return this.mapRow(row);
    }

    /**
     * 删除消息
     */
    delete(id: string): boolean {
        const result = this.db.prepare('DELETE FROM messages WHERE id = ?').run(id);
        return result.changes > 0;
    }

    /**
     * 查询消息列表
     */
    query(options: MessageQueryOptions = {}): PaginatedResult<MessageRecord> {
        const page = options.page ?? 1;
        const pageSize = options.pageSize ?? 50;
        const orderBy = options.orderBy ?? 'created_at';
        const orderDir = options.orderDir ?? 'asc';

        let whereClause = '1=1';
        const params: unknown[] = [];

        if (options.sessionId) {
            whereClause += ' AND session_id = ?';
            params.push(options.sessionId);
        }
        if (options.taskId) {
            whereClause += ' AND task_id = ?';
            params.push(options.taskId);
        }
        if (options.role) {
            whereClause += ' AND role = ?';
            params.push(options.role);
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
            SELECT COUNT(*) as count FROM messages WHERE ${whereClause}
        `).get(...params) as { count: number };
        const total = countRow.count;

        // 获取数据
        const offset = (page - 1) * pageSize;
        const rows = this.db.prepare(`
            SELECT * FROM messages
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
     * 获取会话的所有消息
     */
    getBySession(sessionId: string, limit?: number): MessageRecord[] {
        let sql = `
            SELECT * FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
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
     * 获取最近的消息（用于上下文）
     */
    getRecentForContext(sessionId: string, limit: number = 10): MessageRecord[] {
        const rows = this.db.prepare(`
            SELECT * FROM (
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ) sub ORDER BY created_at ASC
        `).all(sessionId, limit) as any[];

        return rows.map(row => this.mapRow(row));
    }

    /**
     * 删除会话的所有消息
     */
    deleteBySession(sessionId: string): number {
        const result = this.db.prepare('DELETE FROM messages WHERE session_id = ?').run(sessionId);
        return result.changes;
    }

    /**
     * 获取消息统计
     */
    getStats(sessionId: string): { total: number; userMessages: number; assistantMessages: number } {
        const row = this.db.prepare(`
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) as user_messages,
                SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END) as assistant_messages
            FROM messages
            WHERE session_id = ?
        `).get(sessionId) as any;

        return {
            total: row.total || 0,
            userMessages: row.user_messages || 0,
            assistantMessages: row.assistant_messages || 0,
        };
    }

    /**
     * 映射数据库行到记录
     */
    private mapRow(row: any): MessageRecord {
        return {
            id: row.id,
            sessionId: row.session_id,
            taskId: row.task_id,
            role: row.role,
            content: row.content,
            metadata: row.metadata ? JSON.parse(row.metadata) : undefined,
            createdAt: row.created_at,
        };
    }
}
