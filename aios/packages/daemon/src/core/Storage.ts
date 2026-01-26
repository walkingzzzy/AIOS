import Database from 'better-sqlite3';
import { join } from 'path';
import { homedir } from 'os';
import { mkdirSync, existsSync, chmodSync } from 'fs';

export interface StorageOptions {
    dbPath?: string;
}

export class Storage {
    private db: Database.Database;
    
    constructor(options: StorageOptions = {}) {
        const dataDir = join(homedir(), '.aios');
        if (!existsSync(dataDir)) {
            mkdirSync(dataDir, { recursive: true, mode: 0o700 });
        }
        const dbPath = options.dbPath || join(dataDir, 'aios.db');
        this.db = new Database(dbPath);
        try {
            chmodSync(dataDir, 0o700);
        } catch {
            // Ignore permission errors on unsupported platforms.
        }
        try {
            chmodSync(dbPath, 0o600);
        } catch {
            // Ignore permission errors on unsupported platforms.
        }
        this.init();
    }
    
    private init(): void {
        this.db.exec(`
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        `);
        
        this.db.exec(`
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER DEFAULT (strftime('%s', 'now')),
                level TEXT,
                action TEXT,
                adapter TEXT,
                capability TEXT,
                params TEXT,
                result TEXT,
                user_id TEXT
            )
        `);
    }
    
    get(key: string): string | null {
        const row = this.db.prepare('SELECT value FROM kv_store WHERE key = ?').get(key) as { value: string } | undefined;
        return row?.value ?? null;
    }
    
    set(key: string, value: string): void {
        this.db.prepare('INSERT OR REPLACE INTO kv_store (key, value, updated_at) VALUES (?, ?, strftime("%s", "now"))').run(key, value);
    }
    
    delete(key: string): void {
        this.db.prepare('DELETE FROM kv_store WHERE key = ?').run(key);
    }
    
    getJSON<T>(key: string): T | null {
        const value = this.get(key);
        return value ? JSON.parse(value) : null;
    }
    
    setJSON(key: string, value: unknown): void {
        this.set(key, JSON.stringify(value));
    }
    
    getDatabase(): Database.Database {
        return this.db;
    }
    
    close(): void {
        this.db.close();
    }
}
