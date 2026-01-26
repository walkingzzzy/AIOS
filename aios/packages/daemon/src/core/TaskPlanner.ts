/**
 * 任务规划器
 * Smart 层的核心能力：任务分解、失败处理、结果汇总
 * 
 * 增强功能：
 * - 支持生成 PlanDraft（包含风险评估、时间估算）
 * - 增强的 AI 提示词生成更详细的计划
 */

import type { IAIEngine, InternalToolDefinition } from '@aios/shared';
import type {
    ExecutionPlan,
    ExecutionStep,
    StepResult,
    FailureDecision,
    PlanDraft,
    PlanRisk,
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

    // =========================================================================
    // 计划确认工作流增强方法 (Plan Confirmation Workflow)
    // =========================================================================

    /**
     * 生成详细执行计划（用于计划确认流程）
     * 返回包含风险评估、时间估算等详细信息的 PlanDraft
     */
    async planTaskDetailed(
        taskId: string,
        input: string,
        availableTools: InternalToolDefinition[]
    ): Promise<PlanDraft> {
        const systemPrompt = this.buildDetailedPlanningPrompt(availableTools);

        try {
            const response = await this.smartEngine.chat([
                { role: 'system', content: systemPrompt },
                { role: 'user', content: input },
            ]);

            const basePlan = this.parseExecutionPlan(response.content);
            return this.createPlanDraft(taskId, basePlan, response.content);
        } catch (error) {
            console.error('[TaskPlanner] planTaskDetailed failed:', error);
            const fallbackPlan = this.createFallbackPlan(input);
            return this.createPlanDraft(taskId, fallbackPlan);
        }
    }

    /**
     * 构建详细规划提示词
     */
    private buildDetailedPlanningPrompt(availableTools: InternalToolDefinition[]): string {
        return `你是一个高级任务规划器，负责为用户创建详尽、透明且安全的执行方案。

## 可用工具
${this.formatTools(availableTools)}

## 输出格式
请以 JSON 格式输出执行计划：
{
  "goal": "任务目标的一句话描述",
  "summary": "给用户看的简洁计划摘要（50字以内）",
  "rationale": "详细的方案分析（Markdown 格式，见下方要求）",
  "risks": [
    {"level": "low|medium|high", "description": "风险描述", "mitigation": "缓解措施"}
  ],
  "requiredPermissions": ["file_write", "network_access", "system_control"],
  "estimatedDuration": 30000,
  "steps": [
    {
      "id": 1,
      "description": "步骤描述",
      "action": "tool_name",
      "params": {},
      "requiresVision": false,
      "dependsOn": [],
      "estimatedTime": 5000
    }
  ]
}

## Rationale 编写要求（重要）
rationale 字段必须使用 Markdown 格式，结构如下：

\`\`\`markdown
# 方案分析

## 任务理解
- 用户想要达成什么目标？
- 有哪些隐含的需求或约束？
- 当前系统状态如何影响执行？

## 实施策略
- 为什么选择这些步骤而不是其他方法？
- 步骤的执行顺序有什么讲究？
- 各步骤之间如何协作？

## 风险与应对
- 可能出现什么问题？
- 如何最小化风险？

## 预期结果
- 执行完成后用户会看到什么？
- 如何验证任务成功？
\`\`\`

## 风险评估指南
- **low**: 只读操作、信息查询、无副作用操作
- **medium**: 文件创建/修改、系统设置更改、网络请求
- **high**: 文件删除、敏感数据访问、不可逆操作、管理员权限操作

## 权限声明
requiredPermissions 可选值：
- file_read: 读取文件
- file_write: 创建或修改文件
- file_delete: 删除文件
- network_access: 网络请求
- system_control: 系统设置（音量、亮度等）
- app_control: 应用程序控制
- screenshot: 屏幕截图

## 规划原则
1. **透明思考**：在 rationale 中详细展示分析过程，让用户理解你的决策。
2. **最小权限**：只请求完成任务所必需的权限。
3. **原子步骤**：每个步骤应该是可独立验证的原子操作。
4. **明确依赖**：用 dependsOn 数组标注步骤间的依赖关系。
5. **合理估时**：estimatedTime 以毫秒为单位，网络操作通常 2000-10000ms，本地操作通常 500-2000ms。
6. **风险优先**：高风险步骤应排在前面，以便用户优先审核。
7. **工具匹配**：action 必须使用可用工具列表中的 tool_name。`;
    }

    /**
     * 创建 PlanDraft
     */
    private createPlanDraft(
        taskId: string,
        plan: ExecutionPlan,
        rawResponse?: string
    ): PlanDraft {
        const now = Date.now();

        // 尝试从 AI 响应中提取信息
        let risks: PlanRisk[] = [];
        let rationale: string | undefined;

        if (rawResponse) {
            risks = this.extractRisksFromResponse(rawResponse);
            // 尝试提取 rationale，如果 plan 对象里没有解析出来
            const json = this.extractJSON(rawResponse);
            if (json) {
                try {
                    const parsed = JSON.parse(json);
                    if (parsed.rationale) {
                        rationale = parsed.rationale;
                    }
                } catch {
                    // ignore
                }
            }
        }

        if (risks.length === 0) {
            risks = this.assessRisks(plan);
        }

        // 提取所需权限
        const requiredPermissions = this.extractRequiredPermissions(plan.steps);

        // 计算预估时间
        const estimatedDuration = this.estimateDuration(plan.steps);

        return {
            ...plan,
            draftId: `draft_${now}_${Math.random().toString(36).substr(2, 9)}`,
            taskId,
            status: 'draft',
            version: 1,
            createdAt: now,
            updatedAt: now,
            summary: this.generatePlanSummary(plan),
            rationale,
            estimatedDuration,
            risks,
            requiredPermissions,
        };
    }

    /**
     * 创建降级计划
     */
    private createFallbackPlan(input: string): ExecutionPlan {
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

    /**
     * 估算执行时间
     */
    private estimateDuration(steps: ExecutionStep[]): number {
        let total = 0;
        for (const step of steps) {
            // 基础时间 5 秒，视觉任务额外 10 秒
            const baseTime = (step as ExecutionStep & { estimatedTime?: number }).estimatedTime || 5000;
            total += step.requiresVision ? baseTime + 10000 : baseTime;
        }
        return total;
    }

    /**
     * 评估计划风险
     */
    private assessRisks(plan: ExecutionPlan): PlanRisk[] {
        const risks: PlanRisk[] = [];

        // 检查步骤数量
        if (plan.steps.length > 10) {
            risks.push({
                level: 'medium',
                description: `计划包含 ${plan.steps.length} 个步骤，执行时间可能较长`,
                mitigation: '建议分批执行或简化任务',
            });
        }

        // 检查视觉任务
        const visionSteps = plan.steps.filter(s => s.requiresVision);
        if (visionSteps.length > 0) {
            risks.push({
                level: 'low',
                description: `包含 ${visionSteps.length} 个视觉分析步骤`,
            });
        }

        // 检查文件/系统操作
        const riskyActions = plan.steps.filter(s =>
            s.action.includes('file') ||
            s.action.includes('delete') ||
            s.action.includes('shell') ||
            s.action.includes('exec')
        );
        if (riskyActions.length > 0) {
            risks.push({
                level: 'high',
                description: `包含 ${riskyActions.length} 个系统/文件操作，可能影响数据`,
                mitigation: '请确认操作目标正确',
            });
        }

        return risks;
    }

    /**
     * 从 AI 响应中提取风险评估
     */
    private extractRisksFromResponse(response: string): PlanRisk[] {
        try {
            const json = this.extractJSON(response);
            if (json) {
                const parsed = JSON.parse(json);
                if (parsed.risks && Array.isArray(parsed.risks)) {
                    return parsed.risks.filter((r: { level?: string; description?: string }) =>
                        r.level && r.description
                    );
                }
            }
        } catch {
            // 忽略解析错误
        }
        return [];
    }

    /**
     * 提取所需权限
     */
    private extractRequiredPermissions(steps: ExecutionStep[]): string[] {
        const permissions = new Set<string>();

        for (const step of steps) {
            if (step.action.includes('file')) permissions.add('filesystem');
            if (step.action.includes('browser') || step.action.includes('web')) permissions.add('network');
            if (step.action.includes('shell') || step.action.includes('exec')) permissions.add('execute');
            if (step.requiresVision) permissions.add('screen_capture');
        }

        return Array.from(permissions);
    }

    /**
     * 生成计划摘要
     */
    private generatePlanSummary(plan: ExecutionPlan): string {
        if (plan.steps.length === 0) return plan.goal;
        if (plan.steps.length === 1) return plan.goal;
        return `${plan.goal}（共 ${plan.steps.length} 个步骤）`;
    }
}
