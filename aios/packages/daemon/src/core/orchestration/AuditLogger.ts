/**
 * AuditLogger - 审计日志记录器
 * 记录高风险操作和安全事件
 */

import type Database from 'better-sqlite3';
import type { AuditEvent } from './types.js';

/**
 * 审计日志记录器
 */
export class AuditLogger {
    private db?: Database.Database;
    private inMemoryLogs: AuditEvent[] = [];
    private eventCounter = 0;

    constructor(db?: Database.Database) {
        this.db = db;
        if (db) {
            this.initTable();
        }
    }

    /**
     * 初始化表结构
     */
    private initTable(): void {
        this.db?.exec(`
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                timestamp INTEGER,
                type TEXT,
                risk_level TEXT,
                actor TEXT,
                resource TEXT,
                details TEXT,
                requires_confirmation INTEGER DEFAULT 0,
                confirmed INTEGER DEFAULT 0,
                confirmed_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_risk_level ON audit_events(risk_level);
        `);
    }

    /**
     * 生成事件 ID
     */
    private generateEventId(): string {
        return `audit_${Date.now()}_${++this.eventCounter}`;
    }

    /**
     * 记录事件
     */
    log(event: Omit<AuditEvent, 'id' | 'timestamp'>): AuditEvent {
        const fullEvent: AuditEvent = {
            id: this.generateEventId(),
            timestamp: Date.now(),
            ...event,
        };

        // 保存到内存
        this.inMemoryLogs.push(fullEvent);

        // 保存到数据库
        if (this.db) {
            this.db.prepare(`
                INSERT INTO audit_events (id, timestamp, type, risk_level, actor, resource, details, requires_confirmation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            `).run(
                fullEvent.id,
                fullEvent.timestamp,
                fullEvent.type,
                fullEvent.riskLevel,
                fullEvent.actor,
                fullEvent.resource,
                JSON.stringify(fullEvent.details),
                fullEvent.requiresConfirmation ? 1 : 0
            );
        }

        // 高风险事件打印警告
        if (fullEvent.riskLevel === 'high' || fullEvent.riskLevel === 'critical') {
            console.warn(`[AuditLogger] ${fullEvent.riskLevel.toUpperCase()} risk event:`, {
                type: fullEvent.type,
                resource: fullEvent.resource,
                actor: fullEvent.actor,
            });
        }

        return fullEvent;
    }

    /**
     * 记录工具调用
     */
    logToolCall(
        toolName: string,
        params: Record<string, unknown>,
        actor: string = 'system'
    ): AuditEvent {
        const riskLevel = this.assessToolRisk(toolName, params);

        return this.log({
            type: 'tool_call',
            riskLevel,
            actor,
            resource: toolName,
            details: { params },
            requiresConfirmation: riskLevel === 'high' || riskLevel === 'critical',
        });
    }

    /**
     * 记录安全警告
     */
    logSecurityAlert(
        description: string,
        details: Record<string, unknown>,
        riskLevel: AuditEvent['riskLevel'] = 'high'
    ): AuditEvent {
        return this.log({
            type: 'security_alert',
            riskLevel,
            actor: 'system',
            resource: 'security',
            details: { description, ...details },
            requiresConfirmation: true,
        });
    }

    /**
     * 评估工具风险
     */
    private assessToolRisk(toolName: string, params: Record<string, unknown>): AuditEvent['riskLevel'] {
        // 高风险操作
        const highRiskTools = ['file_delete', 'system_command', 'database_drop', 'send_email'];
        if (highRiskTools.some(t => toolName.toLowerCase().includes(t))) {
            return 'high';
        }

        // 中风险操作
        const mediumRiskTools = ['file_write', 'http_request', 'database_update'];
        if (mediumRiskTools.some(t => toolName.toLowerCase().includes(t))) {
            return 'medium';
        }

        // 检查参数中的敏感路径
        const paramsStr = JSON.stringify(params).toLowerCase();
        if (paramsStr.includes('/etc/') || paramsStr.includes('password') || paramsStr.includes('secret')) {
            return 'medium';
        }

        return 'low';
    }

    /**
     * 查询审计日志
     */
    query(options: {
        startTime?: number;
        endTime?: number;
        riskLevel?: AuditEvent['riskLevel'];
        type?: AuditEvent['type'];
        limit?: number;
    } = {}): AuditEvent[] {
        if (this.db) {
            let whereClause = '1=1';
            const params: unknown[] = [];

            if (options.startTime) {
                whereClause += ' AND timestamp >= ?';
                params.push(options.startTime);
            }
            if (options.endTime) {
                whereClause += ' AND timestamp <= ?';
                params.push(options.endTime);
            }
            if (options.riskLevel) {
                whereClause += ' AND risk_level = ?';
                params.push(options.riskLevel);
            }
            if (options.type) {
                whereClause += ' AND type = ?';
                params.push(options.type);
            }

            const limit = options.limit ?? 100;
            params.push(limit);

            const rows = this.db.prepare(`
                SELECT * FROM audit_events
                WHERE ${whereClause}
                ORDER BY timestamp DESC
                LIMIT ?
            `).all(...params) as any[];

            return rows.map(row => ({
                id: row.id,
                timestamp: row.timestamp,
                type: row.type,
                riskLevel: row.risk_level,
                actor: row.actor,
                resource: row.resource,
                details: JSON.parse(row.details),
                requiresConfirmation: !!row.requires_confirmation,
            }));
        }

        // 从内存返回
        return this.inMemoryLogs
            .filter(e => {
                if (options.startTime && e.timestamp < options.startTime) return false;
                if (options.endTime && e.timestamp > options.endTime) return false;
                if (options.riskLevel && e.riskLevel !== options.riskLevel) return false;
                if (options.type && e.type !== options.type) return false;
                return true;
            })
            .slice(-(options.limit ?? 100));
    }

    /**
     * 获取高风险事件
     */
    getHighRiskEvents(limit: number = 50): AuditEvent[] {
        return this.query({ riskLevel: 'high', limit })
            .concat(this.query({ riskLevel: 'critical', limit }));
    }

    /**
     * 确认事件
     */
    confirm(eventId: string): boolean {
        if (this.db) {
            const result = this.db.prepare(`
                UPDATE audit_events 
                SET confirmed = 1, confirmed_at = ?
                WHERE id = ?
            `).run(Date.now(), eventId);
            return result.changes > 0;
        }
        return false;
    }

    /**
     * 清除旧日志
     */
    cleanup(maxAge: number = 30 * 24 * 3600 * 1000): number {
        const cutoff = Date.now() - maxAge;

        if (this.db) {
            const result = this.db.prepare(`
                DELETE FROM audit_events WHERE timestamp < ?
            `).run(cutoff);
            return result.changes;
        }

        const before = this.inMemoryLogs.length;
        this.inMemoryLogs = this.inMemoryLogs.filter(e => e.timestamp >= cutoff);
        return before - this.inMemoryLogs.length;
    }
}
