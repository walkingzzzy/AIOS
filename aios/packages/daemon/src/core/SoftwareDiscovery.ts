import { execSync } from 'child_process';
import { readdirSync, existsSync } from 'fs';
import { join } from 'path';

export interface InstalledApp {
    name: string;
    path: string;
    bundleId?: string;
    version?: string;
}

export class SoftwareDiscovery {
    private cache: InstalledApp[] | null = null;
    private lastScan: number = 0;
    private cacheTTL: number = 60000; // 1分钟缓存

    async scan(forceRefresh = false): Promise<InstalledApp[]> {
        const now = Date.now();
        if (!forceRefresh && this.cache && (now - this.lastScan) < this.cacheTTL) {
            return this.cache;
        }

        let apps: InstalledApp[] = [];
        
        if (process.platform === 'darwin') {
            apps = this.scanMacOS();
        } else if (process.platform === 'win32') {
            apps = this.scanWindows();
        } else if (process.platform === 'linux') {
            apps = this.scanLinux();
        }

        this.cache = apps;
        this.lastScan = now;
        return apps;
    }

    async search(query: string): Promise<InstalledApp[]> {
        const apps = await this.scan();
        const lowerQuery = query.toLowerCase();
        return apps.filter(app => app.name.toLowerCase().includes(lowerQuery));
    }

    async findByBundleId(bundleId: string): Promise<InstalledApp | undefined> {
        const apps = await this.scan();
        return apps.find(app => app.bundleId === bundleId);
    }

    private scanMacOS(): InstalledApp[] {
        const apps: InstalledApp[] = [];
        const appDirs = ['/Applications', join(process.env.HOME || '', 'Applications')];

        for (const dir of appDirs) {
            if (!existsSync(dir)) continue;
            try {
                const entries = readdirSync(dir);
                for (const entry of entries) {
                    if (!entry.endsWith('.app')) continue;
                    const appPath = join(dir, entry);
                    const app = this.parseMacApp(appPath, entry);
                    if (app) apps.push(app);
                }
            } catch { /* ignore */ }
        }
        return apps;
    }

    private parseMacApp(appPath: string, entry: string): InstalledApp | null {
        const name = entry.replace('.app', '');
        const app: InstalledApp = { name, path: appPath };

        try {
            const bundleId = execSync(
                `defaults read "${appPath}/Contents/Info" CFBundleIdentifier 2>/dev/null`,
                { encoding: 'utf-8' }
            ).trim();
            if (bundleId) app.bundleId = bundleId;
        } catch { /* ignore */ }

        try {
            const version = execSync(
                `defaults read "${appPath}/Contents/Info" CFBundleShortVersionString 2>/dev/null`,
                { encoding: 'utf-8' }
            ).trim();
            if (version) app.version = version;
        } catch { /* ignore */ }

        return app;
    }

    private scanLinux(): InstalledApp[] {
        const apps: InstalledApp[] = [];
        const desktopDirs = [
            '/usr/share/applications',
            join(process.env.HOME || '', '.local/share/applications')
        ];

        for (const dir of desktopDirs) {
            if (!existsSync(dir)) continue;
            try {
                const entries = readdirSync(dir);
                for (const entry of entries) {
                    if (!entry.endsWith('.desktop')) continue;
                    const app = this.parseDesktopFile(join(dir, entry));
                    if (app) apps.push(app);
                }
            } catch { /* ignore */ }
        }
        return apps;
    }

    private parseDesktopFile(filePath: string): InstalledApp | null {
        try {
            const content = execSync(`cat "${filePath}"`, { encoding: 'utf-8' });
            const nameMatch = content.match(/^Name=(.+)$/m);
            const execMatch = content.match(/^Exec=(.+)$/m);
            
            if (!nameMatch) return null;
            
            return {
                name: nameMatch[1],
                path: execMatch ? execMatch[1].split(' ')[0] : filePath
            };
        } catch {
            return null;
        }
    }

    private scanWindows(): InstalledApp[] {
        try {
            const output = execSync(
                'powershell -NoProfile -Command "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Depth 2"',
                { encoding: 'utf-8' }
            ).trim();

            if (!output) return [];

            const parsed = JSON.parse(output) as unknown;
            const items = Array.isArray(parsed) ? parsed : [parsed];

            return items
                .map((item: any) => ({
                    name: String(item?.Name ?? ''),
                    path: String(item?.AppID ?? ''),
                    bundleId: item?.AppID ? String(item.AppID) : undefined,
                }))
                .filter((app: InstalledApp) => app.name && app.path);
        } catch {
            return [];
        }
    }
}
