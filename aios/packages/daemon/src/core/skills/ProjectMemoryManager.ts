/**
 * ProjectMemoryManager - 项目记忆管理器
 * 加载和管理 AIOS.md 项目配置
 */

import { existsSync, readFileSync } from 'fs';
import { join } from 'path';
import type { ProjectMemory } from './types.js';

/**
 * 项目记忆管理器配置
 */
export interface ProjectMemoryManagerConfig {
    /** 项目目录 */
    projectDir?: string;
    /** 配置文件名 */
    configFileName?: string;
}

/**
 * 项目记忆管理器
 */
export class ProjectMemoryManager {
    private config: Required<ProjectMemoryManagerConfig>;
    private memory: ProjectMemory | null = null;
    private loadedAt: number | null = null;

    constructor(config: ProjectMemoryManagerConfig = {}) {
        this.config = {
            projectDir: config.projectDir ?? process.cwd(),
            configFileName: config.configFileName ?? 'AIOS.md',
        };
    }

    /**
     * 加载项目记忆
     */
    load(): ProjectMemory | null {
        const configPath = this.getConfigPath();

        if (!existsSync(configPath)) {
            console.log(`[ProjectMemory] No AIOS.md found at ${configPath}`);
            return null;
        }

        try {
            const content = readFileSync(configPath, 'utf-8');
            this.memory = this.parseAIOSMarkdown(content);
            this.loadedAt = Date.now();
            console.log(`[ProjectMemory] Loaded project memory from ${configPath}`);
            return this.memory;
        } catch (error) {
            console.error(`[ProjectMemory] Failed to load AIOS.md:`, error);
            return null;
        }
    }

    /**
     * 获取当前项目记忆
     */
    get(): ProjectMemory | null {
        return this.memory;
    }

    /**
     * 获取配置文件路径
     */
    getConfigPath(): string {
        return join(this.config.projectDir, '.aios', this.config.configFileName);
    }

    /**
     * 解析 AIOS.md 文件
     */
    private parseAIOSMarkdown(content: string): ProjectMemory {
        const memory: ProjectMemory = {
            preferences: {},
            conventions: [],
        };

        // 解析 YAML frontmatter
        const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
        if (frontmatterMatch) {
            const frontmatter = this.parseYamlFrontmatter(frontmatterMatch[1]);
            memory.projectName = frontmatter.name;
            memory.description = frontmatter.description;
            memory.techStack = frontmatter.techStack;
        }

        // 解析各个部分
        const sections = this.parseSections(content);

        // 偏好设置
        if (sections['preferences'] || sections['偏好']) {
            memory.preferences = this.parseKeyValueSection(sections['preferences'] || sections['偏好']);
        }

        // 规范
        if (sections['conventions'] || sections['规范']) {
            memory.conventions = this.parseListSection(sections['conventions'] || sections['规范']);
        }

        // 自定义指令
        if (sections['instructions'] || sections['指令']) {
            memory.customInstructions = sections['instructions'] || sections['指令'];
        }

        return memory;
    }

    /**
     * 解析 YAML frontmatter
     */
    private parseYamlFrontmatter(yaml: string): Record<string, any> {
        const result: Record<string, any> = {};
        const lines = yaml.split('\n');

        for (const line of lines) {
            const match = line.match(/^(\w+):\s*(.*)$/);
            if (match) {
                const [, key, value] = match;
                if (value.startsWith('[') && value.endsWith(']')) {
                    result[key] = value.slice(1, -1).split(',').map(s => s.trim().replace(/['"]/g, ''));
                } else {
                    result[key] = value.replace(/['"]/g, '');
                }
            }
        }

        return result;
    }

    /**
     * 解析文档各部分
     */
    private parseSections(content: string): Record<string, string> {
        const sections: Record<string, string> = {};
        const sectionRegex = /^##\s+(.+)$/gm;
        let match;
        const matches: { title: string; start: number }[] = [];

        while ((match = sectionRegex.exec(content)) !== null) {
            matches.push({
                title: match[1].toLowerCase().trim(),
                start: match.index + match[0].length,
            });
        }

        for (let i = 0; i < matches.length; i++) {
            const start = matches[i].start;
            const end = matches[i + 1]?.start ?? content.length;
            sections[matches[i].title] = content.slice(start, end).trim();
        }

        return sections;
    }

    /**
     * 解析键值对部分
     */
    private parseKeyValueSection(content: string): Record<string, unknown> {
        const result: Record<string, unknown> = {};
        const lines = content.split('\n');

        for (const line of lines) {
            const match = line.match(/^-\s*\*\*(.+?)\*\*:\s*(.+)$/);
            if (match) {
                const [, key, value] = match;
                result[key.toLowerCase()] = value;
            }
        }

        return result;
    }

    /**
     * 解析列表部分
     */
    private parseListSection(content: string): string[] {
        const items: string[] = [];
        const lines = content.split('\n');

        for (const line of lines) {
            const match = line.match(/^-\s+(.+)$/);
            if (match) {
                items.push(match[1].trim());
            }
        }

        return items;
    }

    /**
     * 生成用于系统提示的上下文
     */
    toSystemPromptContext(): string {
        if (!this.memory) return '';

        const parts: string[] = [];

        if (this.memory.projectName) {
            parts.push(`Project: ${this.memory.projectName}`);
        }

        if (this.memory.description) {
            parts.push(`Description: ${this.memory.description}`);
        }

        if (this.memory.techStack && this.memory.techStack.length > 0) {
            parts.push(`Tech Stack: ${this.memory.techStack.join(', ')}`);
        }

        if (this.memory.conventions.length > 0) {
            parts.push(`Conventions:\n${this.memory.conventions.map(c => `- ${c}`).join('\n')}`);
        }

        if (this.memory.customInstructions) {
            parts.push(`Custom Instructions:\n${this.memory.customInstructions}`);
        }

        return parts.join('\n\n');
    }

    /**
     * 检查是否已加载
     */
    isLoaded(): boolean {
        return this.memory !== null;
    }

    /**
     * 刷新项目记忆
     */
    refresh(): ProjectMemory | null {
        this.memory = null;
        this.loadedAt = null;
        return this.load();
    }
}
