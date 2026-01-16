/**
 * PromptGuard - 提示安全守卫
 * 检测和防止提示注入攻击
 */

import type { InjectionCheckResult } from './types.js';

/**
 * 可疑模式配置
 */
interface SuspiciousPattern {
    pattern: RegExp;
    name: string;
    riskLevel: 'low' | 'medium' | 'high';
}

/**
 * 提示守卫
 */
export class PromptGuard {
    private patterns: SuspiciousPattern[];

    constructor() {
        this.patterns = this.initializePatterns();
    }

    /**
     * 初始化可疑模式
     */
    private initializePatterns(): SuspiciousPattern[] {
        return [
            // 角色覆盖尝试
            {
                pattern: /ignore\s+(previous|all|above)\s+(instructions?|prompts?|rules?)/i,
                name: 'instruction_override',
                riskLevel: 'high',
            },
            {
                pattern: /you\s+are\s+(now|actually)\s+a/i,
                name: 'role_hijacking',
                riskLevel: 'high',
            },
            {
                pattern: /forget\s+(everything|all|your)\s+(you|instructions?)/i,
                name: 'memory_wipe',
                riskLevel: 'high',
            },
            // 系统提示泄露
            {
                pattern: /show\s+(me\s+)?(your|the)\s+(system\s+)?prompt/i,
                name: 'prompt_leak',
                riskLevel: 'medium',
            },
            {
                pattern: /print\s+(your\s+)?instructions/i,
                name: 'instruction_leak',
                riskLevel: 'medium',
            },
            // 危险命令
            {
                pattern: /\brm\s+-rf\s+\//i,
                name: 'destructive_command',
                riskLevel: 'high',
            },
            {
                pattern: /\bsudo\s+/i,
                name: 'privilege_escalation',
                riskLevel: 'medium',
            },
            // 编码绕过
            {
                pattern: /base64\s*decode|atob\s*\(/i,
                name: 'encoding_bypass',
                riskLevel: 'low',
            },
            // 分隔符注入
            {
                pattern: /```\s*(system|assistant|user)\s*\n/i,
                name: 'delimiter_injection',
                riskLevel: 'medium',
            },
        ];
    }

    /**
     * 检测提示注入
     */
    detectInjection(input: string): InjectionCheckResult {
        const detectedPatterns: string[] = [];
        let maxRiskLevel: 'none' | 'low' | 'medium' | 'high' = 'none';

        for (const { pattern, name, riskLevel } of this.patterns) {
            if (pattern.test(input)) {
                detectedPatterns.push(name);
                if (this.compareRiskLevel(riskLevel, maxRiskLevel) > 0) {
                    maxRiskLevel = riskLevel;
                }
            }
        }

        const detected = detectedPatterns.length > 0;

        return {
            detected,
            riskLevel: maxRiskLevel,
            patterns: detectedPatterns,
            recommendation: this.getRecommendation(maxRiskLevel, detectedPatterns),
        };
    }

    /**
     * 包装不可信数据
     */
    wrapUntrustedData(data: string, label: string = 'user_data'): string {
        // 使用清晰的分隔符标记不可信内容
        const sanitized = this.sanitize(data);
        return `<${label}>\n${sanitized}\n</${label}>`;
    }

    /**
     * 清理潜在危险字符
     */
    sanitize(input: string): string {
        return input
            // 移除潜在的 markdown 代码块分隔符
            .replace(/```/g, '`\u200B`\u200B`')
            // 转义特殊控制字符
            .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '')
            // 限制长度
            .substring(0, 100000);
    }

    /**
     * 比较风险级别
     */
    private compareRiskLevel(a: string, b: string): number {
        const levels: Record<string, number> = {
            none: 0,
            low: 1,
            medium: 2,
            high: 3,
        };
        return (levels[a] ?? 0) - (levels[b] ?? 0);
    }

    /**
     * 获取建议
     */
    private getRecommendation(riskLevel: string, patterns: string[]): string {
        if (riskLevel === 'none') {
            return '未检测到可疑模式';
        }

        if (riskLevel === 'high') {
            return `检测到高风险模式 (${patterns.join(', ')})。建议拒绝此输入或需要用户确认。`;
        }

        if (riskLevel === 'medium') {
            return `检测到中等风险模式 (${patterns.join(', ')})。建议谨慎处理并记录。`;
        }

        return `检测到低风险模式 (${patterns.join(', ')})。建议继续但保持警惕。`;
    }

    /**
     * 检查并记录
     */
    checkAndLog(input: string, context?: string): InjectionCheckResult {
        const result = this.detectInjection(input);

        if (result.detected) {
            console.warn(
                `[PromptGuard] Detected ${result.riskLevel} risk patterns:`,
                result.patterns,
                context ? `Context: ${context}` : ''
            );
        }

        return result;
    }

    /**
     * 添加自定义模式
     */
    addPattern(pattern: RegExp, name: string, riskLevel: 'low' | 'medium' | 'high'): void {
        this.patterns.push({ pattern, name, riskLevel });
    }
}

/**
 * 默认提示守卫实例
 */
export const promptGuard = new PromptGuard();
