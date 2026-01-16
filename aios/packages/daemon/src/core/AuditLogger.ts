import { Storage } from './Storage.js';

export type LogLevel = 'info' | 'warn' | 'error' | 'security';

export interface AuditLogEntry {
    id?: number;
    timestamp: number;
    level: LogLevel;
    action: string;
    adapter?: string;
    capability?: string;
    params?: Record<string, unknown>;
    result?: unknown;
    userId?: string;
}

export interface AuditLogQuery {
    level?: LogLevel;
    adapter?: string;
    startTime?: number;
    endTime?: number;
    limit?: number;
}

export class AuditLogger {
    private storage: Storage;

    constructor(storage: Storage) {
        this.storage = storage;
    }

    log(entry: Omit<AuditLogEntry, 'id' | 'timestamp'>): void {
        const db = this.storage.getDatabase();
        db.prepare(`
            INSERT INTO audit_logs (level, action, adapter, capability, params, result, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        `).run(
            entry.level,
            entry.action,
            entry.adapter || null,
            entry.capability || null,
            entry.params ? JSON.stringify(entry.params) : null,
            entry.result ? JSON.stringify(entry.result) : null,
            entry.userId || null
        );
    }

    info(action: string, details?: Partial<AuditLogEntry>): void {
        this.log({ level: 'info', action, ...details });
    }

    warn(action: string, details?: Partial<AuditLogEntry>): void {
        this.log({ level: 'warn', action, ...details });
    }

    error(action: string, details?: Partial<AuditLogEntry>): void {
        this.log({ level: 'error', action, ...details });
    }

    security(action: string, details?: Partial<AuditLogEntry>): void {
        this.log({ level: 'security', action, ...details });
    }

    query(options: AuditLogQuery = {}): AuditLogEntry[] {
        const db = this.storage.getDatabase();
        let sql = 'SELECT * FROM audit_logs WHERE 1=1';
        const params: unknown[] = [];

        if (options.level) {
            sql += ' AND level = ?';
            params.push(options.level);
        }
        if (options.adapter) {
            sql += ' AND adapter = ?';
            params.push(options.adapter);
        }
        if (options.startTime) {
            sql += ' AND timestamp >= ?';
            params.push(options.startTime);
        }
        if (options.endTime) {
            sql += ' AND timestamp <= ?';
            params.push(options.endTime);
        }

        sql += ' ORDER BY timestamp DESC';

        if (options.limit) {
            sql += ' LIMIT ?';
            params.push(options.limit);
        }

        const rows = db.prepare(sql).all(...params) as any[];
        return rows.map(row => ({
            id: row.id,
            timestamp: row.timestamp,
            level: row.level,
            action: row.action,
            adapter: row.adapter,
            capability: row.capability,
            params: row.params ? JSON.parse(row.params) : undefined,
            result: row.result ? JSON.parse(row.result) : undefined,
            userId: row.user_id,
        }));
    }
}