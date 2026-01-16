/**
 * ToolTraceRepository - 工具追踪持久化仓库
 * 使用 better-sqlite3 存储工具调用记录
 */

import type Database from 'better-sqlite3';
import BetterSqlite3 from 'better-sqlite3';
import { join } from 'path';
import { homedir } from 'os';
import { mkdirSync, existsSync } from 'fs';
import type {
    ToolTrace,
    ToolTraceStatus,
    ToolTraceQueryOptions,
    ToolTraceStats,
    ToolTraceRepositoryConfig,
} from './types.js';

/**
 * 工具追踪持久化仓库
 */
export class ToolTraceRepository {
    private db: Database.Database;
    private config: Required<ToolTraceRepositoryConfig>;

    constructor(config: ToolTraceRepositoryConfig = {}) {
        const defaultDbPath = join(homedir(), '.aios', 'data', 'audit.db');

        this.config = {
            dbPath: config.dbPath ?? defaultDbPath,
            maxRecords: config.maxRecords ?? 100000,
            retentionDays: config.retentionDays ?? 30,
        };

        // 确保目录存在
        const dbDir = this.config.dbPath.substring(0, this.config.dbPath.lastIndexOf('/'));
        if (!existsSync(dbDir)) {
            mkdirSync(dbDir, { recursive: true });
        }

        this.db = new BetterSqlite3(this.config.dbPath);
        this.db.pragma('journal_mode = WAL');
        this.init();
    }

    /**
     * 初始化数据库表
     */
    private init(): void {
        this.db.exec(`
            CREATE TABLE IF NOT EXISTS tool_traces (
                tool_use_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                adapter_id TEXT NOT NULL,
                capability_id TEXT NOT NULL,
                input TEXT,
                output TEXT,
                error TEXT,
                status TEXT NOT NULL,
                started_at INTEGER NOT NULL,
                completed_at INTEGER,
                duration INTEGER,
                trace_id TEXT,
                created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
            );

            CREATE INDEX IF NOT EXISTS idx_tool_traces_session ON tool_traces(session_id);
            CREATE INDEX IF NOT EXISTS idx_tool_traces_task ON tool_traces(task_id);
            CREATE INDEX IF NOT EXISTS idx_tool_traces_adapter ON tool_traces(adapter_id);
            CREATE INDEX IF NOT EXISTS idx_tool_traces_started ON tool_traces(started_at);
        `);
    }

    /**
     * 创建或更新追踪记录（Upsert）
     */
    upsert(trace: ToolTrace): void {
        const stmt = this.db.prepare(`
            INSERT INTO tool_traces (
                tool_use_id, session_id, task_id, adapter_id, capability_id,
                input, output, error, status, started_at, completed_at, duration, trace_id
            ) VALUES (
                @toolUseId, @sessionId, @taskId, @adapterId, @capabilityId,
                @input, @output, @error, @status, @startedAt, @completedAt, @duration, @traceId
            )
            ON CONFLICT(tool_use_id) DO UPDATE SET
                output = COALESCE(@output, output),
                error = COALESCE(@error, error),
                status = @status,
                completed_at = COALESCE(@completedAt, completed_at),
                duration = COALESCE(@duration, duration)
        `);

        stmt.run({
            toolUseId: trace.toolUseId,
            sessionId: trace.sessionId,
            taskId: trace.taskId,
            adapterId: trace.adapterId,
            capabilityId: trace.capabilityId,
            input: JSON.stringify(trace.input),
            output: trace.output ? JSON.stringify(trace.output) : null,
            error: trace.error ?? null,
            status: trace.status,
            startedAt: trace.startedAt,
            completedAt: trace.completedAt ?? null,
            duration: trace.duration ?? null,
            traceId: trace.traceId ?? null,
        });
    }

    /**
     * 创建待处理记录
     */
    createPending(trace: Omit<ToolTrace, 'status' | 'output' | 'error' | 'completedAt' | 'duration'>): void {
        this.upsert({
            ...trace,
            status: 'pending',
        });
    }

    /**
     * 完成记录（成功）
     */
    complete(toolUseId: string, output: unknown, duration: number): void {
        const stmt = this.db.prepare(`
            UPDATE tool_traces SET
                output = @output,
                status = 'completed',
                completed_at = @completedAt,
                duration = @duration
            WHERE tool_use_id = @toolUseId
        `);

        stmt.run({
            toolUseId,
            output: JSON.stringify(output),
            completedAt: Date.now(),
            duration,
        });
    }

    /**
     * 标记失败
     */
    fail(toolUseId: string, error: string, duration: number): void {
        const stmt = this.db.prepare(`
            UPDATE tool_traces SET
                error = @error,
                status = 'failed',
                completed_at = @completedAt,
                duration = @duration
            WHERE tool_use_id = @toolUseId
        `);

        stmt.run({
            toolUseId,
            error,
            completedAt: Date.now(),
            duration,
        });
    }

    /**
     * 根据 ID 获取记录
     */
    get(toolUseId: string): ToolTrace | null {
        const stmt = this.db.prepare('SELECT * FROM tool_traces WHERE tool_use_id = ?');
        const row = stmt.get(toolUseId) as Record<string, unknown> | undefined;
        return row ? this.mapRow(row) : null;
    }

    /**
     * 查询记录
     */
    query(options: ToolTraceQueryOptions = {}): ToolTrace[] {
        let sql = 'SELECT * FROM tool_traces WHERE 1=1';
        const params: Record<string, unknown> = {};

        if (options.sessionId) {
            sql += ' AND session_id = @sessionId';
            params.sessionId = options.sessionId;
        }
        if (options.taskId) {
            sql += ' AND task_id = @taskId';
            params.taskId = options.taskId;
        }
        if (options.adapterId) {
            sql += ' AND adapter_id = @adapterId';
            params.adapterId = options.adapterId;
        }
        if (options.status) {
            sql += ' AND status = @status';
            params.status = options.status;
        }
        if (options.startTime) {
            sql += ' AND started_at >= @startTime';
            params.startTime = options.startTime;
        }
        if (options.endTime) {
            sql += ' AND started_at <= @endTime';
            params.endTime = options.endTime;
        }

        sql += ' ORDER BY started_at DESC';
        sql += ` LIMIT ${options.limit ?? 100}`;
        sql += ` OFFSET ${options.offset ?? 0}`;

        const stmt = this.db.prepare(sql);
        const rows = stmt.all(params) as Record<string, unknown>[];
        return rows.map(row => this.mapRow(row));
    }

    /**
     * 获取统计信息
     */
    getStats(options: { sessionId?: string; taskId?: string } = {}): ToolTraceStats {
        let whereClause = '1=1';
        const params: Record<string, unknown> = {};

        if (options.sessionId) {
            whereClause += ' AND session_id = @sessionId';
            params.sessionId = options.sessionId;
        }
        if (options.taskId) {
            whereClause += ' AND task_id = @taskId';
            params.taskId = options.taskId;
        }

        // 总体统计
        const overallStmt = this.db.prepare(`
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                AVG(duration) as avg_duration
            FROM tool_traces
            WHERE ${whereClause}
        `);
        const overall = overallStmt.get(params) as Record<string, number>;

        // 按适配器统计
        const adapterStmt = this.db.prepare(`
            SELECT
                adapter_id,
                COUNT(*) as calls,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success,
                AVG(duration) as avg_duration
            FROM tool_traces
            WHERE ${whereClause}
            GROUP BY adapter_id
        `);
        const adapterRows = adapterStmt.all(params) as Record<string, unknown>[];

        const byAdapter: Record<string, { calls: number; successRate: number; avgDuration: number }> = {};
        for (const row of adapterRows) {
            byAdapter[row.adapter_id as string] = {
                calls: row.calls as number,
                successRate: (row.success as number) / (row.calls as number),
                avgDuration: (row.avg_duration as number) ?? 0,
            };
        }

        return {
            totalCalls: overall.total ?? 0,
            successCount: overall.success ?? 0,
            failureCount: overall.failed ?? 0,
            pendingCount: overall.pending ?? 0,
            avgDuration: overall.avg_duration ?? 0,
            byAdapter,
        };
    }

    /**
     * 清理过期记录
     */
    cleanup(): number {
        const cutoff = Date.now() - this.config.retentionDays * 24 * 60 * 60 * 1000;
        const stmt = this.db.prepare('DELETE FROM tool_traces WHERE started_at < ?');
        const result = stmt.run(cutoff);
        return result.changes;
    }

    /**
     * 映射数据库行到对象
     */
    private mapRow(row: Record<string, unknown>): ToolTrace {
        return {
            toolUseId: row.tool_use_id as string,
            sessionId: row.session_id as string,
            taskId: row.task_id as string,
            adapterId: row.adapter_id as string,
            capabilityId: row.capability_id as string,
            input: row.input ? JSON.parse(row.input as string) : {},
            output: row.output ? JSON.parse(row.output as string) : undefined,
            error: row.error as string | undefined,
            status: row.status as ToolTraceStatus,
            startedAt: row.started_at as number,
            completedAt: row.completed_at as number | undefined,
            duration: row.duration as number | undefined,
            traceId: row.trace_id as string | undefined,
        };
    }

    /**
     * 关闭数据库连接
     */
    close(): void {
        this.db.close();
    }
}
