/**
 * SkillRegistry - 技能注册表
 * 负责技能的发现、加载、匹配
 */

import { existsSync, readdirSync, readFileSync } from 'fs';
import { join, basename } from 'path';
import { homedir } from 'os';
import type {
    Skill,
    SkillMeta,
    SkillInstructions,
    SkillResources,
    SkillMatch,
    SkillSummary,
    SkillCategory,
} from './types.js';

/**
 * 技能注册表配置
 */
export interface SkillRegistryConfig {
    /** 用户技能目录 */
    userSkillsDir?: string;
    /** 项目技能目录 */
    projectSkillsDir?: string;
    /** 是否自动发现 */
    autoDiscover?: boolean;
}

/**
 * 技能注册表
 */
export class SkillRegistry {
    private skills: Map<string, Skill> = new Map();
    private config: Required<SkillRegistryConfig>;

    constructor(config: SkillRegistryConfig = {}) {
        this.config = {
            userSkillsDir: config.userSkillsDir ?? join(homedir(), '.aios', 'skills'),
            projectSkillsDir: config.projectSkillsDir ?? '.aios/skills',
            autoDiscover: config.autoDiscover ?? true,
        };

        if (this.config.autoDiscover) {
            this.discoverSkills();
        }
    }

    /**
     * 自动发现技能
     */
    discoverSkills(): number {
        let count = 0;

        // 发现用户级技能
        count += this.discoverFromDirectory(this.config.userSkillsDir, 'user');

        // 发现项目级技能
        count += this.discoverFromDirectory(this.config.projectSkillsDir, 'project');

        console.log(`[SkillRegistry] Discovered ${count} skills`);
        return count;
    }

    /**
     * 从目录发现技能
     */
    private discoverFromDirectory(dir: string, scope: 'user' | 'project'): number {
        if (!existsSync(dir)) {
            return 0;
        }

        let count = 0;
        try {
            const files = readdirSync(dir);
            for (const file of files) {
                if (file.endsWith('.md') || file.endsWith('.skill.md')) {
                    const filePath = join(dir, file);
                    const skill = this.loadSkillFromFile(filePath);
                    if (skill) {
                        this.register(skill);
                        count++;
                    }
                }
            }
        } catch (error) {
            console.error(`[SkillRegistry] Error discovering skills from ${dir}:`, error);
        }

        return count;
    }

    /**
     * 从文件加载技能
     */
    loadSkillFromFile(filePath: string): Skill | null {
        try {
            const content = readFileSync(filePath, 'utf-8');
            return this.parseSkillMarkdown(content, filePath);
        } catch (error) {
            console.error(`[SkillRegistry] Failed to load skill from ${filePath}:`, error);
            return null;
        }
    }

    /**
     * 解析技能 Markdown 文件
     * 格式: YAML frontmatter + Markdown body
     */
    private parseSkillMarkdown(content: string, filePath: string): Skill | null {
        // 解析 YAML frontmatter
        const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
        if (!frontmatterMatch) {
            return null;
        }

        const frontmatter = this.parseYamlFrontmatter(frontmatterMatch[1]);
        const body = content.slice(frontmatterMatch[0].length).trim();

        const id = frontmatter.id || basename(filePath, '.md').replace('.skill', '');

        const meta: SkillMeta = {
            name: frontmatter.name || id,
            version: frontmatter.version || '1.0.0',
            description: frontmatter.description || '',
            category: (frontmatter.category as SkillCategory) || 'custom',
            keywords: frontmatter.keywords || [],
            author: frontmatter.author,
            enabled: frontmatter.enabled !== false,
            priority: frontmatter.priority,
        };

        const instructions: SkillInstructions = {
            usage: body,
            examples: frontmatter.examples,
            notes: frontmatter.notes,
            constraints: frontmatter.constraints,
        };

        const resources: SkillResources | undefined = frontmatter.scripts ||
            frontmatter.references || frontmatter.dependencies ? {
            scripts: frontmatter.scripts,
            references: frontmatter.references,
            dependencies: frontmatter.dependencies,
        } : undefined;

        return {
            id,
            meta,
            instructions,
            resources,
            sourcePath: filePath,
            loadedAt: Date.now(),
        };
    }

    /**
     * 简单的 YAML 解析器
     */
    private parseYamlFrontmatter(yaml: string): Record<string, any> {
        const result: Record<string, any> = {};
        const lines = yaml.split('\n');

        for (const line of lines) {
            const match = line.match(/^(\w+):\s*(.*)$/);
            if (match) {
                const [, key, value] = match;
                // 处理数组
                if (value.startsWith('[') && value.endsWith(']')) {
                    result[key] = value.slice(1, -1).split(',').map(s => s.trim().replace(/['"]/g, ''));
                } else if (value === 'true') {
                    result[key] = true;
                } else if (value === 'false') {
                    result[key] = false;
                } else if (!isNaN(Number(value))) {
                    result[key] = Number(value);
                } else {
                    result[key] = value.replace(/['"]/g, '');
                }
            }
        }

        return result;
    }

    /**
     * 注册技能
     */
    register(skill: Skill): void {
        this.skills.set(skill.id, skill);
        console.log(`[SkillRegistry] Registered skill: ${skill.meta.name} (${skill.id})`);
    }

    /**
     * 注销技能
     */
    unregister(id: string): boolean {
        return this.skills.delete(id);
    }

    /**
     * 获取技能
     */
    get(id: string): Skill | undefined {
        return this.skills.get(id);
    }

    /**
     * 获取所有技能
     */
    getAll(): Skill[] {
        return Array.from(this.skills.values());
    }

    /**
     * 获取启用的技能
     */
    getEnabled(): Skill[] {
        return this.getAll().filter(s => s.meta.enabled);
    }

    /**
     * 获取技能摘要列表（~100 tokens / skill）
     */
    getSummaries(): SkillSummary[] {
        return this.getEnabled().map(skill => ({
            name: skill.meta.name,
            description: skill.meta.description,
            keywords: skill.meta.keywords,
        }));
    }

    /**
     * 估算技能的 Token 数量
     */
    estimateTokens(skill: Skill, level: 'metadata' | 'instructions' | 'full'): number {
        // 简单估算：每4个字符约1个token
        const tokensPerChar = 0.25;

        let content = '';

        // Metadata 层 (~100 tokens)
        content += skill.meta.name + skill.meta.description + skill.meta.keywords.join('');

        if (level === 'metadata') {
            return Math.ceil(content.length * tokensPerChar);
        }

        // Instructions 层 (~2-5K tokens)
        content += skill.instructions.usage;
        if (skill.instructions.examples) {
            content += skill.instructions.examples.join('');
        }
        if (skill.instructions.notes) {
            content += skill.instructions.notes.join('');
        }

        if (level === 'instructions') {
            return Math.ceil(content.length * tokensPerChar);
        }

        // Full 层 (包含资源引用)
        if (skill.resources) {
            content += JSON.stringify(skill.resources);
        }

        return Math.ceil(content.length * tokensPerChar);
    }

    /**
     * 渐进式加载技能（按需加载策略）
     * @param id 技能 ID  
     * @param level 加载级别
     * @param maxTokens 最大 Token 限制
     */
    loadProgressive(
        id: string,
        level: 'metadata' | 'instructions' | 'full',
        maxTokens?: number
    ): { content: string; tokens: number; truncated: boolean } {
        const skill = this.skills.get(id);
        if (!skill) {
            return { content: '', tokens: 0, truncated: false };
        }

        let content = '';
        let truncated = false;

        // Metadata 层
        content += `## ${skill.meta.name}\n${skill.meta.description}\nKeywords: ${skill.meta.keywords.join(', ')}\n\n`;

        if (level === 'metadata') {
            const tokens = this.estimateTokens(skill, 'metadata');
            return { content, tokens, truncated: false };
        }

        // Instructions 层
        content += `### Usage\n${skill.instructions.usage}\n`;

        if (skill.instructions.examples && skill.instructions.examples.length > 0) {
            content += `\n### Examples\n${skill.instructions.examples.map(e => `- ${e}`).join('\n')}\n`;
        }

        const currentTokens = this.estimateTokens(skill, 'instructions');

        // 检查是否超出限制
        if (maxTokens && currentTokens > maxTokens) {
            truncated = true;
            // 截断到限制
            const ratio = maxTokens / currentTokens;
            content = content.substring(0, Math.floor(content.length * ratio)) + '\n...[truncated]';
        }

        if (level === 'instructions' || truncated) {
            return { content, tokens: Math.min(currentTokens, maxTokens || currentTokens), truncated };
        }

        // Full 层 - 添加资源信息
        if (skill.resources) {
            if (skill.resources.scripts) {
                content += `\n### Scripts\n${skill.resources.scripts.join('\n')}\n`;
            }
            if (skill.resources.references) {
                content += `\n### References\n${skill.resources.references.join('\n')}\n`;
            }
        }

        const fullTokens = this.estimateTokens(skill, 'full');
        return { content, tokens: fullTokens, truncated: false };
    }

    /**
     * 匹配技能
     */
    match(query: string, limit: number = 5): SkillMatch[] {
        const queryLower = query.toLowerCase();
        const queryWords = queryLower.split(/\s+/);
        const matches: SkillMatch[] = [];

        for (const skill of this.getEnabled()) {
            const matchedKeywords: string[] = [];
            let score = 0;

            // 关键词匹配
            for (const keyword of skill.meta.keywords) {
                const keywordLower = keyword.toLowerCase();
                if (queryLower.includes(keywordLower)) {
                    matchedKeywords.push(keyword);
                    score += 0.3;
                }
            }

            // 名称匹配
            if (queryLower.includes(skill.meta.name.toLowerCase())) {
                score += 0.4;
            }

            // 描述词匹配
            const descLower = skill.meta.description.toLowerCase();
            for (const word of queryWords) {
                if (word.length > 2 && descLower.includes(word)) {
                    score += 0.1;
                }
            }

            // 分类匹配
            if (queryLower.includes(skill.meta.category)) {
                score += 0.2;
            }

            if (score > 0) {
                matches.push({
                    skill,
                    score: Math.min(score, 1),
                    matchedKeywords,
                });
            }
        }

        // 按分数排序，取前 N 个
        return matches
            .sort((a, b) => b.score - a.score)
            .slice(0, limit);
    }

    /**
     * 按分类获取技能
     */
    getByCategory(category: SkillCategory): Skill[] {
        return this.getEnabled().filter(s => s.meta.category === category);
    }

    /**
     * 加载技能详情（完整指令）
     */
    loadSkillDetails(id: string): Skill | undefined {
        const skill = this.skills.get(id);
        if (!skill) return undefined;

        // 如果需要，可以从文件重新加载完整内容
        console.log(`[SkillRegistry] Loaded details for skill: ${id}`);
        return skill;
    }

    /**
     * 刷新技能
     */
    refresh(): number {
        this.skills.clear();
        return this.discoverSkills();
    }

    /**
     * 获取技能数量
     */
    get count(): number {
        return this.skills.size;
    }
}
