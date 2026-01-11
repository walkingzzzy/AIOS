/**
 * 文件管理适配器
 * 文件操作、搜索等
 */

import { promises as fs } from 'fs';
import { join, dirname, basename, extname, resolve, relative } from 'path';
import { homedir } from 'os';
import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// 安全路径白名单（允许访问的目录）
const ALLOWED_PATHS = [
    homedir(),
    '/tmp',
    '/var/tmp',
];

// 禁止访问的路径模式
const FORBIDDEN_PATTERNS = [
    /^\/etc/,
    /^\/usr/,
    /^\/bin/,
    /^\/sbin/,
    /^\/boot/,
    /^\/root/,
    /^\/sys/,
    /^\/proc/,
    /^\/dev/,
    /\.ssh/,
    /\.gnupg/,
    /\.aws/,
    /\.config\/.*credentials/,
    /password/i,
    /secret/i,
];

export class FileAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.file';
    readonly name = '文件管理';
    readonly description = '文件操作、搜索等功能';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'read_file',
            name: '读取文件',
            description: '读取文件内容',
            permissionLevel: 'medium',
            parameters: [
                { name: 'path', type: 'string', required: true, description: '文件路径' },
            ],
        },
        {
            id: 'write_file',
            name: '写入文件',
            description: '写入内容到文件',
            permissionLevel: 'medium',
            parameters: [
                { name: 'path', type: 'string', required: true, description: '文件路径' },
                { name: 'content', type: 'string', required: true, description: '文件内容' },
            ],
        },
        {
            id: 'list_dir',
            name: '列出目录',
            description: '列出目录中的文件和子目录',
            permissionLevel: 'low',
            parameters: [
                { name: 'path', type: 'string', required: true, description: '目录路径' },
            ],
        },
        {
            id: 'create_dir',
            name: '创建目录',
            description: '创建目录',
            permissionLevel: 'medium',
            parameters: [
                { name: 'path', type: 'string', required: true, description: '目录路径' },
            ],
        },
        {
            id: 'delete_file',
            name: '删除文件',
            description: '删除文件或目录',
            permissionLevel: 'high',
            parameters: [
                { name: 'path', type: 'string', required: true, description: '文件/目录路径' },
            ],
        },
        {
            id: 'copy_file',
            name: '复制文件',
            description: '复制文件到新位置',
            permissionLevel: 'medium',
            parameters: [
                { name: 'source', type: 'string', required: true, description: '源文件路径' },
                { name: 'destination', type: 'string', required: true, description: '目标路径' },
            ],
        },
        {
            id: 'move_file',
            name: '移动文件',
            description: '移动或重命名文件',
            permissionLevel: 'medium',
            parameters: [
                { name: 'source', type: 'string', required: true, description: '源文件路径' },
                { name: 'destination', type: 'string', required: true, description: '目标路径' },
            ],
        },
        {
            id: 'get_file_info',
            name: '获取文件信息',
            description: '获取文件元数据',
            permissionLevel: 'low',
            parameters: [
                { name: 'path', type: 'string', required: true, description: '文件路径' },
            ],
        },
    ];

    async checkAvailability(): Promise<boolean> {
        return true; // Node.js fs 始终可用
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            const path = this.resolvePath(args.path as string);
            
            // 安全检查
            const securityCheck = this.checkPathSecurity(path);
            if (!securityCheck.allowed) {
                return this.failure('SECURITY_DENIED', securityCheck.reason || '路径访问被拒绝');
            }

            switch (capability) {
                case 'read_file':
                    return this.readFile(path);
                case 'write_file':
                    return this.writeFile(path, args.content as string);
                case 'list_dir':
                    return this.listDir(path);
                case 'create_dir':
                    return this.createDir(path);
                case 'delete_file':
                    return this.deleteFile(path);
                case 'copy_file': {
                    const destPath = this.resolvePath(args.destination as string);
                    const destCheck = this.checkPathSecurity(destPath);
                    if (!destCheck.allowed) {
                        return this.failure('SECURITY_DENIED', destCheck.reason || '目标路径访问被拒绝');
                    }
                    return this.copyFile(path, destPath);
                }
                case 'move_file': {
                    const destPath = this.resolvePath(args.destination as string);
                    const destCheck = this.checkPathSecurity(destPath);
                    if (!destCheck.allowed) {
                        return this.failure('SECURITY_DENIED', destCheck.reason || '目标路径访问被拒绝');
                    }
                    return this.moveFile(path, destPath);
                }
                case 'get_file_info':
                    return this.getFileInfo(path);
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    /**
     * 解析路径（支持 ~ 展开）
     */
    private resolvePath(inputPath: string): string {
        if (inputPath.startsWith('~')) {
            return resolve(join(homedir(), inputPath.slice(1)));
        }
        return resolve(inputPath);
    }

    /**
     * 检查路径安全性
     */
    private checkPathSecurity(path: string): { allowed: boolean; reason?: string } {
        const normalizedPath = resolve(path);

        // 检查是否匹配禁止模式
        for (const pattern of FORBIDDEN_PATTERNS) {
            if (pattern.test(normalizedPath)) {
                return { allowed: false, reason: `路径包含敏感内容: ${normalizedPath}` };
            }
        }

        // 检查是否在允许的路径下
        const isAllowed = ALLOWED_PATHS.some(allowedPath => {
            const rel = relative(allowedPath, normalizedPath);
            return rel && !rel.startsWith('..') && !resolve(rel).startsWith('/');
        });

        if (!isAllowed) {
            return { allowed: false, reason: `路径不在允许范围内: ${normalizedPath}` };
        }

        return { allowed: true };
    }

    private async readFile(path: string): Promise<AdapterResult> {
        // 限制文件大小（10MB）
        const stat = await fs.stat(path);
        if (stat.size > 10 * 1024 * 1024) {
            return this.failure('FILE_TOO_LARGE', '文件大小超过 10MB 限制');
        }
        
        const content = await fs.readFile(path, 'utf-8');
        return this.success({ content, path, size: stat.size });
    }

    private async writeFile(path: string, content: string): Promise<AdapterResult> {
        // 限制写入大小（10MB）
        if (content.length > 10 * 1024 * 1024) {
            return this.failure('CONTENT_TOO_LARGE', '内容大小超过 10MB 限制');
        }
        
        await fs.mkdir(dirname(path), { recursive: true });
        await fs.writeFile(path, content, 'utf-8');
        return this.success({ path, written: true, size: content.length });
    }

    private async listDir(path: string): Promise<AdapterResult> {
        const entries = await fs.readdir(path, { withFileTypes: true });
        const items = entries.map((entry) => ({
            name: entry.name,
            isDirectory: entry.isDirectory(),
            isFile: entry.isFile(),
        }));
        return this.success({ path, items, count: items.length });
    }

    private async createDir(path: string): Promise<AdapterResult> {
        await fs.mkdir(path, { recursive: true });
        return this.success({ path, created: true });
    }

    private async deleteFile(path: string): Promise<AdapterResult> {
        const stat = await fs.stat(path);
        if (stat.isDirectory()) {
            // 限制删除目录的深度
            const entries = await fs.readdir(path, { recursive: true });
            if (entries.length > 100) {
                return this.failure('DIR_TOO_LARGE', '目录包含超过 100 个文件，拒绝删除');
            }
            await fs.rm(path, { recursive: true });
        } else {
            await fs.unlink(path);
        }
        return this.success({ path, deleted: true });
    }

    private async copyFile(source: string, destination: string): Promise<AdapterResult> {
        await fs.mkdir(dirname(destination), { recursive: true });
        await fs.copyFile(source, destination);
        return this.success({ source, destination, copied: true });
    }

    private async moveFile(source: string, destination: string): Promise<AdapterResult> {
        await fs.mkdir(dirname(destination), { recursive: true });
        await fs.rename(source, destination);
        return this.success({ source, destination, moved: true });
    }

    private async getFileInfo(path: string): Promise<AdapterResult> {
        const stat = await fs.stat(path);
        return this.success({
            path,
            name: basename(path),
            extension: extname(path),
            size: stat.size,
            isDirectory: stat.isDirectory(),
            isFile: stat.isFile(),
            created: stat.birthtime.toISOString(),
            modified: stat.mtime.toISOString(),
        });
    }
}

export const fileAdapter = new FileAdapter();
