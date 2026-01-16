/**
 * 任务规划器
 * Smart 层的核心能力：任务分解、失败处理、结果汇总
 */

import type { IAIEngine, InternalToolDefinition } from '@aios/shared';
import type {
    ExecutionPlan,
    ExecutionStep,
    StepResult,
    FailureDecision,
} from '../types/orchestrator.js';

/**
 * 任务规划器 - Smart 层
 */
export class TaskPlanner {
    private smartEngine: IAIEngine;

    constructor(smartEngine: IAIEngine) {
        this.smartEngine = smartEngine;
    }

    /**
     * 生成执行计划
     */
    async planTask(input: string, availableTools: InternalToolDefinition[]): Promise<ExecutionPlan> {
        const systemPrompt = `你是一个任务规划器。根据用户的请求，生成一个详细的执行计划。

## 可用工具
${this.formatTools(availableTools)}

## 输出格式
请以 JSON 格式输出执行计划：
{
  "goal": "任务目标描述",
  "steps": [
    {
      "id": 1,
      "description": "步骤描述",
      "action": "tool_name",
      "params": {},
      "requiresVision": false,
      "dependsOn": []
    }
  ]
}

## 规划原则
1. 将复杂任务分解为简单步骤
2. 每个步骤应该是原子操作
3. 标注步骤之间的依赖关系
4. 需要屏幕理解时设置 requiresVision: true
5. action 必须是上面“可用工具”列表中的 tool_name（例如：audio_set_volume、apps_open_app）
6. 如果没有合适工具且需要屏幕理解，将 requiresVision 设为 true，并用自然语言描述要观察/判断的内容`;

        try {
            const response = await this.smartEngine.chat([
                { role: 'system', content: systemPrompt },
                { role: 'user', content: input },
            ]);

            return this.parseExecutionPlan(response.content);
        } catch (error) {
            console.error('[TaskPlanner] planTask failed:', error);
            // 返回默认单步计划
            return {
                goal: input,
                steps: [{
                    id: 1,
                    description: input,
                    action: 'unknown',
                    params: {},
                    requiresVision: false,
                    dependsOn: [],
                }],
            };
        }
    }

    /**
     * 处理步骤失败
     */
    async handleFailure(step: ExecutionStep, error?: Error): Promise<FailureDecision> {
        const prompt = `执行步骤失败：
- 步骤：${step.description}
- 动作：${step.action}
- 错误：${error?.message || '未知错误'}

请决定下一步操作并以 JSON 格式回复：
{"decision": "retry|alternative|skip|abort", "reason": "原因"}`;

        try {
            const response = await this.smartEngine.chat([
                { role: 'user', content: prompt },
            ], { maxTokens: 256 });

            const json = this.extractJSON(response.content);
            if (json) {
                const result = JSON.parse(json);
                const validDecisions: FailureDecision[] = ['retry', 'alternative', 'skip', 'abort'];
                if (validDecisions.includes(result.decision)) {
                    return result.decision;
                }
            }
        } catch (parseError) {
            console.error('[TaskPlanner] handleFailure parse error:', parseError);
        }

        return 'abort';
    }

    /**
     * 汇总执行结果
     */
    async summarize(originalRequest: string, results: StepResult[]): Promise<string> {
        const successCount = results.filter(r => r.success).length;
        const failCount = results.length - successCount;

        const prompt = `用户请求：${originalRequest}

执行结果：
${this.formatResults(results)}

总计：${successCount} 成功，${failCount} 失败

请生成一个简洁、用户友好的结果摘要（中文）。`;

        try {
            const response = await this.smartEngine.chat([
                { role: 'user', content: prompt },
            ], { maxTokens: 512 });

            return response.content;
        } catch (error) {
            console.error('[TaskPlanner] summarize error:', error);
            // 降级简单摘要
            if (failCount === 0) {
                return `任务完成：已执行 ${successCount} 个步骤。`;
            } else {
                return `任务部分完成：${successCount} 成功，${failCount} 失败。`;
            }
        }
    }

    /**
     * 格式化工具列表
     */
    private formatTools(tools: InternalToolDefinition[]): string {
        if (tools.length === 0) {
            return '(无可用工具)';
        }
        return tools.slice(0, 30).map(t => `- ${t.name}: ${t.description}`).join('\n');
    }

    /**
     * 格式化结果列表
     */
    private formatResults(results: StepResult[]): string {
        return results.map(r =>
            `步骤 ${r.stepId}: ${r.success ? '✓ 成功' : '✗ 失败'}${r.error ? ` - ${r.error.message}` : ''}`
        ).join('\n');
    }

    /**
     * 解析执行计划
     */
    private parseExecutionPlan(text: string): ExecutionPlan {
        const json = this.extractJSON(text);
        if (!json) {
            throw new Error('无法从响应中提取 JSON');
        }

        const plan = JSON.parse(json);

        // 验证结构
        if (!plan.goal || !Array.isArray(plan.steps)) {
            throw new Error('执行计划结构无效');
        }

        // 规范化步骤
        plan.steps = plan.steps.map((step: Partial<ExecutionStep>, index: number) => ({
            id: step.id || index + 1,
            description: step.description || '未知步骤',
            action: step.action || 'unknown',
            params: step.params || {},
            requiresVision: step.requiresVision || false,
            dependsOn: step.dependsOn || [],
        }));

        return plan as ExecutionPlan;
    }

    /**
     * 从文本中提取 JSON
     */
    private extractJSON(text: string): string | null {
        // 1. 尝试 markdown 代码块
        const codeBlockMatch = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
        if (codeBlockMatch) {
            const candidate = codeBlockMatch[1].trim();
            try {
                JSON.parse(candidate);
                return candidate;
            } catch {
                // 继续尝试
            }
        }

        // 2. 尝试直接匹配 JSON 对象
        const jsonMatch = text.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
            try {
                JSON.parse(jsonMatch[0]);
                return jsonMatch[0];
            } catch {
                // 继续修复
            }
        }

        // 3. 尝试修复常见问题
        let cleaned = text
            .replace(/,\s*}/g, '}')   // 移除尾随逗号
            .replace(/,\s*]/g, ']')   // 移除数组尾随逗号
            .replace(/'/g, '"');      // 单引号转双引号

        const cleanedMatch = cleaned.match(/\{[\s\S]*\}/);
        if (cleanedMatch) {
            try {
                JSON.parse(cleanedMatch[0]);
                return cleanedMatch[0];
            } catch {
                // 最终失败
            }
        }

        return null;
    }
}
