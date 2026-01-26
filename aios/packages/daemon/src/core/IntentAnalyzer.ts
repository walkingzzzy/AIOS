/**
 * 意图分析器
 * 增强版：支持直达工具匹配 + 任务类型分类
 */

import type { AdapterRegistry } from './AdapterRegistry.js';
import { TaskType, type TaskAnalysis, type ToolCall, type TaskContext } from '../types/orchestrator.js';

/** 工具匹配模式 */
interface ToolPattern {
    pattern: RegExp;
    tool: string;
    action: string;
    paramExtractor?: (input: string) => Record<string, unknown> | null;
}

/**
 * 意图分析器 - 三层 AI 协调的入口
 */
export class IntentAnalyzer {
    private registry: AdapterRegistry;

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

        // 应用控制 - 修正 action ID
        // 使用非贪婪匹配，遇到逗号/句号/分号等停止
        {
            pattern: /打开\s*([^，。；！？,.:;!?\s]+)/, tool: 'com.aios.adapter.apps', action: 'open_app', paramExtractor: (input) => {
                const match = input.match(/打开\s*([^，。；！？,.:;!?\s]+)/);
                return match ? { name: match[1].trim() } : null;
            }
        },
        {
            pattern: /关闭\s*([^，。；！？,.:;!?\s]+)/, tool: 'com.aios.adapter.apps', action: 'close_app', paramExtractor: (input) => {
                const match = input.match(/关闭\s*([^，。；！？,.:;!?\s]+)/);
                return match ? { name: match[1].trim() } : null;
            }
        },
        {
            pattern: /启动\s*([^，。；！？,.:;!?\s]+)/, tool: 'com.aios.adapter.apps', action: 'open_app', paramExtractor: (input) => {
                const match = input.match(/启动\s*([^，。；！？,.:;!?\s]+)/);
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

        // 语音
        {
            pattern: /说[：:]\s*(.+)/, tool: 'com.aios.adapter.speech', action: 'speak', paramExtractor: (input) => {
                const match = input.match(/说[：:]\s*(.+)/);
                return match ? { text: match[1] } : null;
            }
        },
        {
            pattern: /朗读[：:]\s*(.+)/, tool: 'com.aios.adapter.speech', action: 'speak', paramExtractor: (input) => {
                const match = input.match(/朗读[：:]\s*(.+)/);
                return match ? { text: match[1] } : null;
            }
        },

        // 通知
        {
            pattern: /发送?通知[：:]?\s*(.*)/, tool: 'com.aios.adapter.notification', action: 'notify', paramExtractor: (input) => {
                const match = input.match(/发送?通知[：:]?\s*(.*)/);
                return { title: '提醒', message: match?.[1] || input };
            }
        },
        {
            pattern: /提醒我[：:]?\s*(.+)/, tool: 'com.aios.adapter.notification', action: 'notify', paramExtractor: (input) => {
                const match = input.match(/提醒我[：:]?\s*(.+)/);
                return { title: '提醒', message: match?.[1] || input };
            }
        },

        // 计算
        {
            pattern: /计算\s*(.+)/, tool: 'com.aios.adapter.calculator', action: 'calculate', paramExtractor: (input) => {
                const match = input.match(/计算\s*(.+)/);
                return match ? { expression: match[1] } : null;
            }
        },
        {
            pattern: /算一下\s*(.+)/, tool: 'com.aios.adapter.calculator', action: 'calculate', paramExtractor: (input) => {
                const match = input.match(/算一下\s*(.+)/);
                return match ? { expression: match[1] } : null;
            }
        },

        // 系统信息
        { pattern: /电池|电量/, tool: 'com.aios.adapter.systeminfo', action: 'get_battery' },
        { pattern: /CPU|处理器/, tool: 'com.aios.adapter.systeminfo', action: 'get_cpu' },
        { pattern: /内存/, tool: 'com.aios.adapter.systeminfo', action: 'get_memory' },
        { pattern: /磁盘|硬盘/, tool: 'com.aios.adapter.systeminfo', action: 'get_disk' },

        // 天气
        {
            pattern: /(.+)天气/, tool: 'com.aios.adapter.weather', action: 'get_current_weather', paramExtractor: (input) => {
                const match = input.match(/(.+?)(?:的)?天气/);
                return match ? { city: match[1].trim() } : null;
            }
        },

        // 翻译
        {
            pattern: /翻译[：:]\s*(.+)/, tool: 'com.aios.adapter.translate', action: 'translate', paramExtractor: (input) => {
                const match = input.match(/翻译[：:]\s*(.+)/);
                return match ? { text: match[1], targetLang: 'en' } : null;
            }
        },
    ];

    /** 视觉关键词 */
    private visionKeywords = [
        '屏幕上', '看看', '显示', '界面', '窗口',
        '点击', '按钮', '菜单', '图片', '识别',
        '什么内容', '当前画面', '屏幕显示',
    ];

    /** 复杂任务模式 */
    private complexPatterns = [
        /先.*然后/, /首先.*接着/, /第一步.*第二步/,
        /和.*比较/, /在.*和.*/, /从.*到.*/,
        /分析/, /总结/, /比较/, /评估/, /规划/,
        /如果.*就/, /当.*时/,
        /帮我.*多个/, /批量/,
    ];

    constructor(registry: AdapterRegistry) {
        this.registry = registry;
    }

    /**
     * 分析用户输入
     */
    async analyze(input: string, context: TaskContext = {}): Promise<TaskAnalysis> {
        // 0. 检查是否是多动作命令（如"打开浏览器，搜索新闻"）
        // 这类命令应该交给 AI 层处理，而不是直达匹配
        if (this.isMultiActionCommand(input)) {
            return {
                taskType: TaskType.Simple,
                requiresPlanning: false,
                confidence: 0.8,
            };
        }

        // 1. 尝试直达工具匹配
        const directMatch = this.matchDirectTool(input);
        if (directMatch) {
            return {
                taskType: TaskType.Simple,
                directToolCall: directMatch,
                requiresPlanning: false,
                confidence: 0.95,
            };
        }

        // 2. 检查是否需要视觉
        if (this.requiresVision(input, context)) {
            return {
                taskType: TaskType.Visual,
                visionPrompt: this.generateVisionPrompt(input),
                requiresPlanning: false,
                confidence: 0.85,
            };
        }

        // 3. 检查是否是复杂任务
        if (this.isComplexTask(input)) {
            return {
                taskType: TaskType.Complex,
                requiresPlanning: true,
                confidence: 0.75,
            };
        }

        // 4. 默认简单任务（走 Fast 层 AI）
        return {
            taskType: TaskType.Simple,
            requiresPlanning: false,
            confidence: 0.6,
        };
    }

    /**
     * 直达工具匹配
     */
    matchDirectTool(input: string): ToolCall | null {
        for (const { pattern, tool, action, paramExtractor } of this.toolPatterns) {
            if (pattern.test(input)) {
                const params = paramExtractor?.(input) || {};
                // 验证适配器存在
                if (this.registry.get(tool)) {
                    return { tool, action, params };
                }
            }
        }
        return null;
    }

    /**
     * 判断是否需要视觉
     */
    private requiresVision(input: string, context: TaskContext): boolean {
        // 如果已经有截图，倾向于使用视觉
        if (context.hasScreenshot) {
            return true;
        }
        return this.visionKeywords.some(keyword => input.includes(keyword));
    }

    /**
     * 判断是否是复杂任务
     */
    private isComplexTask(input: string): boolean {
        return this.complexPatterns.some(pattern => pattern.test(input));
    }

    /**
     * 生成视觉提示
     */
    private generateVisionPrompt(input: string): string {
        return `分析屏幕内容，完成用户请求：${input}`;
    }

    /**
     * 判断是否是多动作命令
     * 例如："打开浏览器，搜索今天的新闻" 包含两个动作
     */
    private isMultiActionCommand(input: string): boolean {
        // 检查是否包含中文或英文逗号/分号分隔的多个部分
        const parts = input.split(/[，,；;]/);
        if (parts.length < 2) return false;

        // 第二部分是否包含动作关键词
        const actionKeywords = ['搜索', '查找', '查看', '打开', '关闭', '发送', '下载', '播放', '暂停', '停止', '保存', '导出'];
        const secondPart = parts.slice(1).join('').trim();

        return actionKeywords.some(keyword => secondPart.includes(keyword));
    }
}
