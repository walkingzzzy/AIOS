/**
 * Skills 系统类型定义
 */

/**
 * 技能分类
 */
export type SkillCategory =
    | 'development'   // 开发相关
    | 'productivity'  // 生产力工具
    | 'analysis'      // 分析任务
    | 'communication' // 沟通交流
    | 'automation'    // 自动化
    | 'creative'      // 创意内容
    | 'system'        // 系统操作
    | 'custom';       // 自定义

/**
 * 技能元数据
 */
export interface SkillMeta {
    /** 技能名称 */
    name: string;
    /** 技能版本 */
    version: string;
    /** 技能描述 */
    description: string;
    /** 技能分类 */
    category: SkillCategory;
    /** 关键词（用于匹配） */
    keywords: string[];
    /** 作者 */
    author?: string;
    /** 是否启用 */
    enabled: boolean;
    /** 优先级 (用于排序) */
    priority?: number;
}

/**
 * 技能指令
 */
export interface SkillInstructions {
    /** 使用说明 */
    usage: string;
    /** 示例 */
    examples?: string[];
    /** 注意事项 */
    notes?: string[];
    /** 限制条件 */
    constraints?: string[];
}

/**
 * 技能资源
 */
export interface SkillResources {
    /** 脚本路径 */
    scripts?: string[];
    /** 引用文档 */
    references?: string[];
    /** 资产文件 */
    assets?: string[];
    /** 依赖的其他技能 */
    dependencies?: string[];
}

/**
 * 完整技能定义
 */
export interface Skill {
    /** 技能 ID */
    id: string;
    /** 技能元数据 */
    meta: SkillMeta;
    /** 技能指令 */
    instructions: SkillInstructions;
    /** 技能资源 */
    resources?: SkillResources;
    /** 源文件路径 */
    sourcePath?: string;
    /** 加载时间 */
    loadedAt?: number;
}

/**
 * 技能匹配结果
 */
export interface SkillMatch {
    /** 匹配的技能 */
    skill: Skill;
    /** 匹配分数 (0-1) */
    score: number;
    /** 匹配的关键词 */
    matchedKeywords: string[];
}

/**
 * 技能摘要（用于上下文注入）
 */
export interface SkillSummary {
    /** 技能名称 */
    name: string;
    /** 技能描述 */
    description: string;
    /** 关键词 */
    keywords: string[];
}

/**
 * 项目记忆配置
 */
export interface ProjectMemory {
    /** 项目名称 */
    projectName?: string;
    /** 项目描述 */
    description?: string;
    /** 用户偏好 */
    preferences: Record<string, unknown>;
    /** 项目规范 */
    conventions: string[];
    /** 技术栈 */
    techStack?: string[];
    /** 自定义指令 */
    customInstructions?: string;
}
