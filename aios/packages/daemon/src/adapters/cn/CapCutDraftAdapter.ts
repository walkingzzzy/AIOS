/**
 * 剪映草稿适配器
 * 读取/写入草稿 JSON
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { promises as fs } from 'fs';
import { homedir, tmpdir } from 'os';
import { join, resolve } from 'path';

const DEFAULT_PROJECT_DIR = join(homedir(), 'Movies', 'CapCut', 'User Data', 'Projects');
const SAFE_ROOTS = [homedir(), '/tmp', '/var/tmp'];
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
    /password/i,
    /secret/i,
];

type DraftReadResult = {
    content: Record<string, unknown> | null;
    meta: Record<string, unknown> | null;
};

export class CapCutDraftAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.capcut';
    readonly name = '剪映草稿';
    readonly description = '剪映草稿 JSON 读写适配器';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'capcut_list_projects',
            name: '列出草稿项目',
            description: '列出剪映草稿目录',
            permissionLevel: 'low',
            parameters: [
                { name: 'base_path', type: 'string', required: false, description: '草稿根目录' },
            ],
        },
        {
            id: 'capcut_read_draft',
            name: '读取草稿',
            description: '读取草稿 JSON 内容',
            permissionLevel: 'low',
            parameters: [
                { name: 'project_path', type: 'string', required: true, description: '草稿目录路径' },
            ],
        },
        {
            id: 'capcut_write_draft',
            name: '写入草稿',
            description: '写入草稿 JSON 内容',
            permissionLevel: 'high',
            parameters: [
                { name: 'project_path', type: 'string', required: true, description: '草稿目录路径' },
                { name: 'draft_content', type: 'object', required: true, description: 'draft_content.json 内容' },
                { name: 'draft_meta', type: 'object', required: false, description: 'draft_meta_info.json 内容' },
            ],
        },
    ];

    async checkAvailability(): Promise<boolean> {
        return true;
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'capcut_list_projects':
                    return this.listProjects(args.base_path as string | undefined);
                case 'capcut_read_draft':
                    return this.readDraft(args.project_path as string);
                case 'capcut_write_draft':
                    return this.writeDraft(
                        args.project_path as string,
                        args.draft_content as Record<string, unknown>,
                        args.draft_meta as Record<string, unknown> | undefined
                    );
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async listProjects(basePath?: string): Promise<AdapterResult> {
        const root = this.resolvePath(basePath || DEFAULT_PROJECT_DIR);
        const entries = await fs.readdir(root, { withFileTypes: true });
        const projects = entries
            .filter((entry) => entry.isDirectory())
            .map((entry) => ({
                name: entry.name,
                path: join(root, entry.name),
            }));

        return this.success({ base_path: root, projects });
    }

    private async readDraft(projectPath: string): Promise<AdapterResult> {
        if (!projectPath) {
            return this.failure('INVALID_PARAM', 'project_path 为必填参数');
        }

        const root = this.resolvePath(projectPath);
        const result = await this.readDraftFiles(root);
        return this.success({ project_path: root, ...result });
    }

    private async writeDraft(
        projectPath: string,
        draftContent: Record<string, unknown>,
        draftMeta?: Record<string, unknown>
    ): Promise<AdapterResult> {
        if (!projectPath || !draftContent) {
            return this.failure('INVALID_PARAM', 'project_path 与 draft_content 为必填参数');
        }

        const root = this.resolvePath(projectPath);
        const contentPath = join(root, 'draft_content.json');
        const metaPath = join(root, 'draft_meta_info.json');

        await fs.writeFile(contentPath, JSON.stringify(draftContent, null, 2), 'utf8');
        if (draftMeta) {
            await fs.writeFile(metaPath, JSON.stringify(draftMeta, null, 2), 'utf8');
        }

        return this.success({ project_path: root, written: true });
    }

    private async readDraftFiles(projectPath: string): Promise<DraftReadResult> {
        const contentPath = join(projectPath, 'draft_content.json');
        const metaPath = join(projectPath, 'draft_meta_info.json');
        const legacyMetaPath = join(projectPath, 'draft_mate_info.json');

        const [content, meta] = await Promise.all([
            this.safeReadJson(contentPath),
            this.safeReadJson(metaPath),
        ]);

        if (!meta) {
            const legacy = await this.safeReadJson(legacyMetaPath);
            return { content, meta: legacy };
        }

        return { content, meta };
    }

    private async safeReadJson(filePath: string): Promise<Record<string, unknown> | null> {
        try {
            const text = await fs.readFile(filePath, 'utf8');
            return JSON.parse(text) as Record<string, unknown>;
        } catch {
            return null;
        }
    }

    private resolvePath(targetPath: string): string {
        const resolved = resolve(targetPath || tmpdir());
        if (!SAFE_ROOTS.some((root) => resolved.startsWith(root))) {
            throw new Error('路径不在允许范围内');
        }
        if (FORBIDDEN_PATTERNS.some((pattern) => pattern.test(resolved))) {
            throw new Error('路径存在敏感命中');
        }
        return resolved;
    }
}

export const capcutDraftAdapter = new CapCutDraftAdapter();
