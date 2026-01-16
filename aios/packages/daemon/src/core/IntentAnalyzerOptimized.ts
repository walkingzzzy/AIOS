/**
 * IntentAnalyzer 性能优化版本
 * 添加 LRU 缓存机制以提高意图分析性能
 */

import type { AdapterRegistry } from './AdapterRegistry.js';
import { TaskType, type TaskAnalysis, type ToolCall, type TaskContext } from '../types/orchestrator.js';

/** LRU 缓存节点 */
class CacheNode {
    key: string;
    value: TaskAnalysis;
    prev: CacheNode | null = null;
    next: CacheNode | null = null;

    constructor(key: string, value: TaskAnalysis) {
        this.key = key;
        this.value = value;
    }
}

/** LRU 缓存实现 */
class LRUCache {
    private capacity: number;
    private cache: Map<string, CacheNode>;
    private head: CacheNode;
    private tail: CacheNode;

    constructor(capacity: number = 100) {
        this.capacity = capacity;
        this.cache = new Map();

        // 创建虚拟头尾节点
        this.head = new CacheNode('', {} as TaskAnalysis);
        this.tail = new CacheNode('', {} as TaskAnalysis);
        this.head.next = this.tail;
        this.tail.prev = this.head;
    }

    get(key: string): TaskAnalysis | null {
        const node = this.cache.get(key);
        if (!node) return null;

        // 移动到头部（最近使用）
        this.moveToHead(node);
        return node.value;
    }

    set(key: string, value: TaskAnalysis): void {
        const existingNode = this.cache.get(key);

        if (existingNode) {
            // 更新现有节点
            existingNode.value = value;
            this.moveToHead(existingNode);
        } else {
            // 创建新节点
            const newNode = new CacheNode(key, value);
            this.cache.set(key, newNode);
            this.addToHead(newNode);

            // 检查容量
            if (this.cache.size > this.capacity) {
                const removed = this.removeTail();
                if (removed) {
                    this.cache.delete(removed.key);
                }
            }
        }
    }

    private moveToHead(node: CacheNode): void {
        this.removeNode(node);
        this.addToHead(node);
    }

    private removeNode(node: CacheNode): void {
        if (node.prev) node.prev.next = node.next;
        if (node.next) node.next.prev = node.prev;
    }

    private addToHead(node: CacheNode): void {
        node.prev = this.head;
        node.next = this.head.next;
        if (this.head.next) this.head.next.prev = node;
        this.head.next = node;
    }

    private removeTail(): CacheNode | null {
        const node = this.tail.prev;
        if (node === this.head) return null;
        this.removeNode(node!);
        return node;
    }

    clear(): void {
        this.cache.clear();
        this.head.next = this.tail;
        this.tail.prev = this.head;
    }

    get size(): number {
        return this.cache.size;
    }
}

/** 工具匹配模式 */
interface ToolPattern {
    pattern: RegExp;
    tool: string;
    action: string;
    paramExtractor?: (input: string) => Record<string, unknown> | null;
}

/**
 * 意图分析器 - 带缓存优化
 */
export class IntentAnalyzerOptimized {
    private registry: AdapterRegistry;
    private cache: LRUCache;
    private cacheEnabled: boolean;
    private cacheHits: number = 0;
    private cacheMisses: number = 0;

    /** 直达工具匹配规则 */
    private toolPatterns: ToolPattern[] = [
        // 音量控制
        { pattern: /(调高|增加|提高|加大).*音量/, tool: 'com.aios.adapter.audio', action: 'set_volume', paramExtractor: () => ({ volume: 80 }) },
        { pattern: /(调低|减小|降低|减少).*音量/, tool: 'com.aios.adapter.audio', action: 'set_volume', paramExtractor: () => ({ volume: 30 }) },
        { pattern: /取消\s*静音/, tool: 'com.aios.adapter.audio', action: 'set_muted', paramExtractor: () => ({ muted: false }) },
        { pattern: /静音/, tool: 'com.aios.adapter.audio', action: 'set_muted', paramExtractor: () => ({ muted: true }) },
        {
            pattern: /音量.*(\d+)/, tool: 'com.aios.adapter.audio', action: 'set_volume', paramExtractor: (input) => {
                const match = input.match(/音量.*?(\d+)/);
                return match ? { volume: parseInt(match[1]) } : null;
            }
        },

        // 亮度控制
        { pattern: /(调高|增加|提高).*亮度/, tool: 'com.aios.adapter.display', action: 'set_brightness', paramExtractor: () => ({ brightness: 80 }) },
        { pattern: /(调低|减小|降低).*亮度/, tool: 'com.aios.adapter.display', action: 'set_brightness', paramExtractor: () => ({ brightness: 30 }) },
        {
            pattern: /亮度.*(\d+)/, tool: 'com.aios.adapter.display', action: 'set_brightness', paramExtractor: (input) => {
                const match = input.match(/亮度.*?(\d+)/);
                return match ? { brightness: parseInt(match[1]) } : null;
            }
        },

        // 应用控制
        {
            pattern: /打开\s*(.+)/, tool: 'com.aios.adapter.apps', action: 'open_app', paramExtractor: (input) => {
                const match = input.match(/打开\s*(.+)/);
                return match ? { name: match[1].trim() } : null;
            }
        },
        {
            pattern: /关闭\s*(.+)/, tool: 'com.aios.adapter.apps', action: 'close_app', paramExtractor: (input) => {
                const match = input.match(/关闭\s*(.+)/);
                return match ? { name: match[1].trim() } : null;
            }
        },

        // 电源控制
        { pattern: /锁屏|锁定屏幕/, tool: 'com.aios.adapter.power', action: 'lock_screen' },
        { pattern: /休眠|睡眠/, tool: 'com.aios.adapter.power', action: 'sleep' },
        { pattern: /关机/, tool: 'com.aios.adapter.power', action: 'shutdown', paramExtractor: () => ({ confirm: true, delay: 60 }) },
        { pattern: /重启/, tool: 'com.aios.adapter.power', action: 'restart', paramExtractor: () => ({ confirm: true, delay: 60 }) },

        // 桌面设置
        { pattern: /深色模式|暗色模式|夜间模式/, tool: 'com.aios.adapter.desktop', action: 'set_appearance', paramExtractor: () => ({ mode: 'dark' }) },
        { pattern: /浅色模式|亮色模式|日间模式/, tool: 'com.aios.adapter.desktop', action: 'set_appearance', paramExtractor: () => ({ mode: 'light' }) },
    ];

    constructor(registry: AdapterRegistry, options?: { cacheSize?: number; cacheEnabled?: boolean }) {
        this.registry = registry;
        this.cache = new LRUCache(options?.cacheSize || 100);
        this.cacheEnabled = options?.cacheEnabled !== false;
    }

    /**
     * 分析用户输入的意图
     */
    async analyze(input: string, context?: TaskContext): Promise<TaskAnalysis> {
        const normalizedInput = input.trim().toLowerCase();

        // 检查缓存
        if (this.cacheEnabled) {
            const cached = this.cache.get(normalizedInput);
            if (cached) {
                this.cacheHits++;
                return { ...cached }; // 返回副本
            }
            this.cacheMisses++;
        }

        // 执行分析
        const analysis = await this.performAnalysis(normalizedInput, context);

        // 存入缓存
        if (this.cacheEnabled) {
            this.cache.set(normalizedInput, analysis);
        }

        return analysis;
    }

    /**
     * 执行实际的意图分析
     */
    private async performAnalysis(input: string, context?: TaskContext): Promise<TaskAnalysis> {
        // 1. 尝试直达工具匹配
        const directMatch = this.matchDirectTool(input);
        if (directMatch) {
            return {
                type: TaskType.Simple,
                confidence: 0.95,
                directToolCall: directMatch,
                requiresVision: false,
                complexity: 'low',
            };
        }

        // 2. 检测是否需要视觉能力
        const requiresVision = this.detectVisionRequirement(input);
        if (requiresVision) {
            return {
                type: TaskType.Visual,
                confidence: 0.9,
                requiresVision: true,
                complexity: 'medium',
            };
        }

        // 3. 检测任务复杂度
        const complexity = this.detectComplexity(input);
        if (complexity === 'high') {
            return {
                type: TaskType.Complex,
                confidence: 0.85,
                requiresVision: false,
                complexity: 'high',
            };
        }

        // 4. 默认为简单任务
        return {
            type: TaskType.Simple,
            confidence: 0.8,
            requiresVision: false,
            complexity: 'low',
        };
    }

    /**
     * 匹配直达工具
     */
    private matchDirectTool(input: string): ToolCall | null {
        for (const pattern of this.toolPatterns) {
            if (pattern.pattern.test(input)) {
                const params = pattern.paramExtractor ? pattern.paramExtractor(input) : {};
                if (params === null) continue;

                return {
                    tool: pattern.tool,
                    action: pattern.action,
                    parameters: params,
                };
            }
        }
        return null;
    }

    /**
     * 检测是否需要视觉能力
     */
    private detectVisionRequirement(input: string): boolean {
        const visionKeywords = [
            '屏幕', '看', '显示', '界面', '窗口', '图片', '图像',
            '截图', '分析', '识别', '检测', '查看', '观察'
        ];
        return visionKeywords.some(keyword => input.includes(keyword));
    }

    /**
     * 检测任务复杂度
     */
    private detectComplexity(input: string): 'low' | 'medium' | 'high' {
        // 多步骤关键词
        const multiStepKeywords = ['然后', '接着', '之后', '首先', '最后', '并且', '同时'];
        const hasMultiStep = multiStepKeywords.some(keyword => input.includes(keyword));

        // 复杂操作关键词
        const complexKeywords = ['分析', '总结', '比较', '优化', '生成', '创建', '设计'];
        const hasComplexOp = complexKeywords.some(keyword => input.includes(keyword));

        if (hasMultiStep || hasComplexOp) {
            return 'high';
        }

        if (input.length > 50) {
            return 'medium';
        }

        return 'low';
    }

    /**
     * 获取缓存统计信息
     */
    getCacheStats() {
        const total = this.cacheHits + this.cacheMisses;
        const hitRate = total > 0 ? (this.cacheHits / total) * 100 : 0;

        return {
            hits: this.cacheHits,
            misses: this.cacheMisses,
            total,
            hitRate: hitRate.toFixed(2) + '%',
            size: this.cache.size,
        };
    }

    /**
     * 清空缓存
     */
    clearCache(): void {
        this.cache.clear();
        this.cacheHits = 0;
        this.cacheMisses = 0;
    }

    /**
     * 启用/禁用缓存
     */
    setCacheEnabled(enabled: boolean): void {
        this.cacheEnabled = enabled;
        if (!enabled) {
            this.clearCache();
        }
    }
}
