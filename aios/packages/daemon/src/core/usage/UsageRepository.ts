/**
 * UsageRepository - 用量记录持久化仓库
 */

import type Database from 'better-sqlite3';
import BetterSqlite3 from 'better-sqlite3';
import { join } from 'path';
import { homedir } from 'os';
import { mkdirSync, existsSync } from 'fs';
import { randomUUID } from 'crypto';
import type {
    UsageRecord,
    AITier,
    UsageStats,
    UsageQueryOptions,
    UsageRepositoryConfig,
} from './types.js';

/**
 * 用量记录持久化仓库
 */
export class UsageRepository {
    private db: Database.Database;
    private config: Required<UsageRepositoryConfig>;

    constructor(config: UsageRepositoryConfig = {}) {
        const defaultDbPath = join(homedir(), '.aios', 'data', 'usage.db');

        this.config = {
            dbPath: config.dbPath ?? defaultDbPath,
            maxRecords: config.maxRecords ?? 100000,
            retentionDays: config.retentionDays ?? 90,
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
            CREATE TABLE IF NOT EXISTS usage_records (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                model TEXT NOT NULL,
                tier TEXT NOT NULL,
                token_input INTEGER NOT NULL,
                token_output INTEGER NOT NULL,
                token_total INTEGER NOT NULL,
                cost REAL NOT NULL,
                duration INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                trace_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_usage_session ON usage_records(session_id);
            CREATE INDEX IF NOT EXISTS idx_usage_task ON usage_records(task_id);
            CREATE INDEX IF NOT EXISTS idx_usage_model ON usage_records(model);
            CREATE INDEX IF NOT EXISTS idx_usage_tier ON usage_records(tier);
            CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_records(created_at);
        `);
    }

    /**
     * 创建用量记录
     */
    create(record: Omit<UsageRecord, 'id'>): UsageRecord {
        const id = randomUUID();
        const fullRecord: UsageRecord = { id, ...record };

        const stmt = this.db.prepare(`
            INSERT INTO usage_records (
                id, session_id, task_id, model, tier,
                token_input, token_output, token_total,
                cost, duration, created_at, trace_id
            ) VALUES (
                @id, @sessionId, @taskId, @model, @tier,
                @tokenInput, @tokenOutput, @tokenTotal,
                @cost, @duration, @createdAt, @traceId
            )
        `);

        stmt.run({
            id,
            sessionId: fullRecord.sessionId,
            taskId: fullRecord.taskId,
            model: fullRecord.model,
            tier: fullRecord.tier,
            tokenInput: fullRecord.tokenInput,
            tokenOutput: fullRecord.tokenOutput,
            tokenTotal: fullRecord.tokenTotal,
            cost: fullRecord.cost,
            duration: fullRecord.duration,
            createdAt: fullRecord.createdAt,
            traceId: fullRecord.traceId ?? null,
        });

        return fullRecord;
    }

    /**
     * 根据 ID 获取记录
     */
    get(id: string): UsageRecord | null {
        const stmt = this.db.prepare('SELECT * FROM usage_records WHERE id = ?');
        const row = stmt.get(id) as Record<string, unknown> | undefined;
        return row ? this.mapRow(row) : null;
    }

    /**
     * 查询记录
     */
    query(options: UsageQueryOptions = {}): UsageRecord[] {
        let sql = 'SELECT * FROM usage_records WHERE 1=1';
        const params: Record<string, unknown> = {};

        if (options.sessionId) {
            sql += ' AND session_id = @sessionId';
            params.sessionId = options.sessionId;
        }
        if (options.taskId) {
            sql += ' AND task_id = @taskId';
            params.taskId = options.taskId;
        }
        if (options.model) {
            sql += ' AND model = @model';
            params.model = options.model;
        }
        if (options.tier) {
            sql += ' AND tier = @tier';
            params.tier = options.tier;
        }
        if (options.startTime) {
            sql += ' AND created_at >= @startTime';
            params.startTime = options.startTime;
        }
        if (options.endTime) {
            sql += ' AND created_at <= @endTime';
            params.endTime = options.endTime;
        }

        sql += ' ORDER BY created_at DESC';
        sql += ` LIMIT ${options.limit ?? 100}`;
        sql += ` OFFSET ${options.offset ?? 0}`;

        const stmt = this.db.prepare(sql);
        const rows = stmt.all(params) as Record<string, unknown>[];
        return rows.map(row => this.mapRow(row));
    }

    /**
     * 获取统计信息
     */
    getStats(options: { sessionId?: string; taskId?: string; startTime?: number; endTime?: number } = {}): UsageStats {
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
        if (options.startTime) {
            whereClause += ' AND created_at >= @startTime';
            params.startTime = options.startTime;
        }
        if (options.endTime) {
            whereClause += ' AND created_at <= @endTime';
            params.endTime = options.endTime;
        }

        // 总体统计
        const overallStmt = this.db.prepare(`
            SELECT
                SUM(token_total) as total_tokens,
                SUM(cost) as total_cost,
                COUNT(*) as total_calls,
                AVG(duration) as avg_duration
            FROM usage_records
            WHERE ${whereClause}
        `);
        const overall = overallStmt.get(params) as Record<string, number>;

        // 按模型统计
        const modelStmt = this.db.prepare(`
            SELECT
                model,
                SUM(token_total) as tokens,
                SUM(cost) as cost,
                COUNT(*) as calls
            FROM usage_records
            WHERE ${whereClause}
            GROUP BY model
        `);
        const modelRows = modelStmt.all(params) as Record<string, unknown>[];

        const byModel: Record<string, { tokens: number; cost: number; calls: number }> = {};
        for (const row of modelRows) {
            byModel[row.model as string] = {
                tokens: row.tokens as number,
                cost: row.cost as number,
                calls: row.calls as number,
            };
        }

        // 按层级统计
        const tierStmt = this.db.prepare(`
            SELECT
                tier,
                SUM(token_total) as tokens,
                SUM(cost) as cost,
                COUNT(*) as calls
            FROM usage_records
            WHERE ${whereClause}
            GROUP BY tier
        `);
        const tierRows = tierStmt.all(params) as Record<string, unknown>[];

        const byTier: Record<AITier, { tokens: number; cost: number; calls: number }> = {
            fast: { tokens: 0, cost: 0, calls: 0 },
            vision: { tokens: 0, cost: 0, calls: 0 },
            smart: { tokens: 0, cost: 0, calls: 0 },
        };
        for (const row of tierRows) {
            const tier = row.tier as AITier;
            if (tier in byTier) {
                byTier[tier] = {
                    tokens: row.tokens as number,
                    cost: row.cost as number,
                    calls: row.calls as number,
                };
            }
        }

        return {
            totalTokens: overall.total_tokens ?? 0,
            totalCost: overall.total_cost ?? 0,
            totalCalls: overall.total_calls ?? 0,
            avgDuration: overall.avg_duration ?? 0,
            byModel,
            byTier,
        };
    }

    /**
     * 清理过期记录
     */
    cleanup(): number {
        const cutoff = Date.now() - this.config.retentionDays * 24 * 60 * 60 * 1000;
        const stmt = this.db.prepare('DELETE FROM usage_records WHERE created_at < ?');
        const result = stmt.run(cutoff);
        return result.changes;
    }

    /**
     * 映射数据库行到对象
     */
    private mapRow(row: Record<string, unknown>): UsageRecord {
        return {
            id: row.id as string,
            sessionId: row.session_id as string,
            taskId: row.task_id as string,
            model: row.model as string,
            tier: row.tier as AITier,
            tokenInput: row.token_input as number,
            tokenOutput: row.token_output as number,
            tokenTotal: row.token_total as number,
            cost: row.cost as number,
            duration: row.duration as number,
            createdAt: row.created_at as number,
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
