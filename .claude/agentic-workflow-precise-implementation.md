# AIOS Agentic Workflow 精确实施方案

> 基于实际代码审查的准确实施计划  
> 日期: 2026-01-21

## 执行摘要

经过深入代码审查，发现 **AIOS 已经实现了 90% 的 Agentic Workflow 功能**：
- ✅ 后端完整（PlanConfirmationManager, TaskPlanner, TaskOrchestrator）
- ✅ IPC 通信完整（Preload API, Main Process handlers, JSON-RPC methods）
- ✅ 前端组件完整（PlanPreview, TaskBoard, usePlanApproval Hook）
- ❌ **唯一缺失**: ChatView 没有集成 PlanPreview 组件

**预计完成时间**: 4-6 小时（而非原估计的 7-10 天）

## 一、当前状态详细分析

### 1.1 已实现的组件

#### 后端 (Daemon)

**文件**: `aios/packages/daemon/src/core/planning/PlanConfirmationManager.ts`
- ✅ `createDraft()` - 创建计划草案
- ✅ `submitForApproval()` - 提交审批（返回 Promise）
- ✅ `handleApprovalResponse()` - 处理用户响应
- ✅ `updatePlan()` - 修改计划
- ✅ `getPendingPlan()` - 获取待审批计划
- ✅ 事件发送（`plan.created`, `plan.approval_required`, `plan.approved`, `plan.rejected`）

**文件**: `aios/packages/daemon/src/core/TaskPlanner.ts`
- ✅ `planTaskDetailed()` - 生成详细计划（包含 rationale, risks, permissions）
- ✅ `toPlanMarkdown()` - Markdown 格式化
- ✅ `assessRisks()` - 风险评估
- ✅ `extractRequiredPermissions()` - 权限提取

**文件**: `aios/packages/daemon/src/core/TaskOrchestrator.ts`
- ✅ `executeComplex()` - 复杂任务执行流程
- ✅ `isPlanSignificant()` - 判断是否需要审批
- ✅ `emitPlanApprovalRequired()` - 发送审批请求事件
- ✅ 集成 PlanConfirmationManager

**文件**: `aios/packages/daemon/src/index.ts`
- ✅ JSON-RPC 方法注册:
  - `plan.getPending`
  - `plan.approve`
  - `plan.reject`
  - `plan.modify`

#### IPC 层

**文件**: `aios/packages/client/src/preload/index.ts`
- ✅ `onPlanApprovalRequired()` - 监听审批请求
- ✅ `approvePlan()` - 确认计划
- ✅ `rejectPlan()` - 拒绝计划
- ✅ `modifyPlan()` - 修改计划
- ✅ `getPendingPlan()` - 获取待审批计划

**文件**: `aios/packages/client/src/main/index.ts`
- ✅ `DAEMON_EVENT_CHANNELS` 包含 `plan:approval-required`
- ✅ IPC Handlers 完整注册
- ✅ 事件转发到 Renderer Process

#### 前端组件

**文件**: `aios/packages/client/src/renderer/src/components/PlanPreview.tsx`
- ✅ 完整的 UI 组件（300+ 行）
- ✅ 支持 Rationale 展示（Markdown 渲染）
- ✅ 风险评估可视化（颜色编码）
- ✅ 步骤列表（可展开详情）
- ✅ 所需权限展示
- ✅ Approve/Reject 按钮
- ✅ 拒绝反馈输入
- ✅ Tab 切换（方案说明 / 执行步骤）

**文件**: `aios/packages/client/src/renderer/src/components/TaskBoard.tsx`
- ✅ 任务组展示
- ✅ 子任务进度
- ✅ 状态图标（⏳ 🔄 ✅ ❌）
- ✅ 可展开/折叠
- ✅ 取消/重试按钮

**文件**: `aios/packages/client/src/renderer/src/hooks/usePlanApproval.ts`
- ✅ 监听 `plan:approval-required` 事件
- ✅ `approvePlan()` 方法
- ✅ `rejectPlan()` 方法
- ✅ `modifyPlan()` 方法
- ✅ 加载状态管理
- ✅ 错误处理

### 1.2 缺失的部分

#### ❌ ChatView 集成

**文件**: `aios/packages/client/src/renderer/src/views/ChatView.tsx`

**问题**: 
- 没有导入 `PlanPreview` 组件
- 没有导入 `usePlanApproval` Hook
- 没有渲染计划预览界面

**需要添加**:
```tsx
import PlanPreview from '../components/PlanPreview';
import { usePlanApproval } from '../hooks/usePlanApproval';

// 在组件内部
const { pendingPlan, isLoading, approvePlan, rejectPlan } = usePlanApproval();

// 在 JSX 中
{pendingPlan && (
    <div className="plan-preview-overlay">
        <PlanPreview
            plan={pendingPlan}
            onApprove={() => approvePlan()}
            onReject={(feedback) => rejectPlan(feedback)}
            isLoading={isLoading}
        />
    </div>
)}
```


#### ⚠️ 步骤级进度事件（可选）

**文件**: `aios/packages/daemon/src/core/TaskOrchestrator.ts`

**当前状态**: `executeStep()` 方法存在，但没有发送步骤级事件

**需要添加**:
```typescript
private async executeStep(step: ExecutionStep, execCtx: ExecutionContext): Promise<StepResult> {
    // 发送步骤开始事件
    this.emitStepEvent('step:started', {
        taskId: execCtx.taskId,
        stepId: step.id,
        description: step.description,
    });
    
    try {
        // ... 执行步骤
        const result = await this.toolExecutor.execute(...);
        
        // 发送步骤完成事件
        this.emitStepEvent('step:completed', {
            taskId: execCtx.taskId,
            stepId: step.id,
            success: result.success,
        });
        
        return result;
    } catch (error) {
        // 发送步骤失败事件
        this.emitStepEvent('step:failed', {
            taskId: execCtx.taskId,
            stepId: step.id,
            error: error.message,
        });
        throw error;
    }
}

private emitStepEvent(method: string, params: unknown): void {
    const notification = {
        jsonrpc: '2.0',
        method,
        params,
    };
    try {
        process.stdout.write(JSON.stringify(notification) + '\n');
    } catch (error) {
        console.error(`[TaskOrchestrator] Failed to emit ${method}:`, error);
    }
}
```

#### ⚠️ 配置启用

**文件**: `aios/packages/daemon/src/index.ts`

**需要确认**: TaskOrchestrator 初始化时是否启用了 `enablePlanConfirmation`

**查找代码**:
```typescript
// 搜索 TaskOrchestrator 初始化
const orchestrator = new TaskOrchestrator({
    fastEngine,
    visionEngine,
    smartEngine,
    adapterRegistry,
    enablePlanConfirmation: true,  // 确认这个配置
    planConfirmationTimeout: 5 * 60 * 1000,
    // ...
});
```

## 二、精确实施步骤

### 阶段 1: ChatView 集成（1-2 小时）

#### 步骤 1.1: 修改 ChatView.tsx

**文件**: `aios/packages/client/src/renderer/src/views/ChatView.tsx`

**修改内容**:

```typescript
// 1. 添加导入
import PlanPreview from '../components/PlanPreview';
import { usePlanApproval } from '../hooks/usePlanApproval';

// 2. 在组件内部添加 Hook
const ChatView: React.FC<ChatViewProps> = ({ quickLauncherOpen, onQuickLauncherClose }) => {
    // ... 现有状态
    
    // 添加计划审批 Hook
    const { pendingPlan, isLoading: isPlanLoading, approvePlan, rejectPlan, error: planError } = usePlanApproval();
    
    // ... 其他代码
};

// 3. 在 JSX 中添加 PlanPreview 渲染（在 chat-view div 内部）
return (
    <div className="chat-view">
        {/* 计划预览覆盖层 */}
        {pendingPlan && (
            <div className="plan-preview-overlay">
                <div className="plan-preview-modal">
                    <PlanPreview
                        plan={pendingPlan}
                        onApprove={() => approvePlan()}
                        onReject={(feedback) => rejectPlan(feedback)}
                        isLoading={isPlanLoading}
                    />
                </div>
            </div>
        )}
        
        {/* 现有的消息区域等 */}
        <div className="chat-messages-area">
            {/* ... */}
        </div>
        
        {/* ... */}
    </div>
);
```

#### 步骤 1.2: 添加 CSS 样式

**文件**: `aios/packages/client/src/renderer/src/views/ChatView.css` (或在 App.css 中)

```css
/* 计划预览覆盖层 */
.plan-preview-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 20px;
}

.plan-preview-modal {
    max-width: 800px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    background: var(--bg-primary, #ffffff);
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
    .plan-preview-modal {
        background: var(--bg-primary, #1e1e1e);
    }
}
```

#### 步骤 1.3: 测试

1. 启动 AIOS
2. 输入复杂任务（例如："创建一个包含 5 个步骤的文件处理流程"）
3. 应该看到 PlanPreview 弹出
4. 测试 Approve/Reject 按钮

**预计时间**: 1-2 小时

### 阶段 2: 添加步骤级进度事件（2-3 小时）

#### 步骤 2.1: 修改 TaskOrchestrator.ts

**文件**: `aios/packages/daemon/src/core/TaskOrchestrator.ts`

**在 `executeStep()` 方法中添加事件发送**:

```typescript
private async executeStep(step: ExecutionStep, execCtx: ExecutionContext): Promise<StepResult> {
    // 发送步骤开始事件
    this.emitStepEvent('step:started', {
        taskId: execCtx.taskId,
        stepId: step.id,
        description: step.description,
        timestamp: Date.now(),
    });
    
    try {
        // 视觉步骤
        if (step.requiresVision) {
            const screenshotBase64 = await this.captureScreenshotBase64();
            const visionResult = await this.visionEngine.chat([
                { role: 'user', content: step.description, ...(screenshotBase64 ? { images: [screenshotBase64] } : {}) },
            ]);
            
            // 发送完成事件
            this.emitStepEvent('step:completed', {
                taskId: execCtx.taskId,
                stepId: step.id,
                success: true,
                output: visionResult.content,
                timestamp: Date.now(),
            });
            
            return {
                stepId: step.id,
                success: true,
                output: visionResult.content,
            };
        }

        // 工具步骤
        const actionSpec = step.action.trim();
        if (!actionSpec) {
            this.emitStepEvent('step:failed', {
                taskId: execCtx.taskId,
                stepId: step.id,
                error: '步骤缺少 action',
                timestamp: Date.now(),
            });
            
            return {
                stepId: step.id,
                success: false,
                error: new Error('步骤缺少 action'),
            };
        }

        let tool = actionSpec;
        let action = '';
        const lastDot = actionSpec.lastIndexOf('.');
        if (lastDot > 0 && lastDot < actionSpec.length - 1) {
            tool = actionSpec.slice(0, lastDot);
            action = actionSpec.slice(lastDot + 1);
        }

        // Phase 8: 高危操作检查和确认
        if (this.enableConfirmation && this.confirmationManager) {
            const riskCheck = promptGuard.checkAndLog(step.description, 'executeStep');
            if (riskCheck.riskLevel === 'high' || riskCheck.riskLevel === 'medium') {
                const approved = await this.confirmationManager.requestConfirmation({
                    taskId: `step-${step.id}`,
                    action: step.description,
                    riskLevel: riskCheck.riskLevel as 'medium' | 'high',
                    details: {
                        tool,
                        action,
                        params: step.params,
                        patterns: riskCheck.patterns,
                    },
                });

                if (!approved) {
                    this.emitStepEvent('step:failed', {
                        taskId: execCtx.taskId,
                        stepId: step.id,
                        error: '用户拒绝执行此高危操作',
                        timestamp: Date.now(),
                    });
                    
                    return {
                        stepId: step.id,
                        success: false,
                        error: new Error('用户拒绝执行此高危操作'),
                    };
                }
            }
        }

        const result = await this.toolExecutor.execute({
            tool,
            action,
            params: step.params,
        }, execCtx);

        // 发送完成事件
        this.emitStepEvent(result.success ? 'step:completed' : 'step:failed', {
            taskId: execCtx.taskId,
            stepId: step.id,
            success: result.success,
            output: result.data,
            error: result.success ? undefined : result.message,
            timestamp: Date.now(),
        });

        return {
            stepId: step.id,
            success: result.success,
            output: result.data,
            error: result.success ? undefined : new Error(result.message),
        };
    } catch (error) {
        this.emitStepEvent('step:failed', {
            taskId: execCtx.taskId,
            stepId: step.id,
            error: error instanceof Error ? error.message : String(error),
            timestamp: Date.now(),
        });
        
        return {
            stepId: step.id,
            success: false,
            error: error instanceof Error ? error : new Error(String(error)),
        };
    }
}

// 添加辅助方法
private emitStepEvent(method: string, params: unknown): void {
    const notification = {
        jsonrpc: '2.0',
        method,
        params,
    };
    
    try {
        process.stdout.write(JSON.stringify(notification) + '\n');
    } catch (error) {
        console.error(`[TaskOrchestrator] Failed to emit ${method}:`, error);
    }
}
```

#### 步骤 2.2: 更新 Main Process 事件通道

**文件**: `aios/packages/client/src/main/index.ts`

**确认 `DAEMON_EVENT_CHANNELS` 包含步骤事件**:

```typescript
const DAEMON_EVENT_CHANNELS = new Set([
    'task:progress',
    'task:complete',
    'task:error',
    'task:update',
    'confirmation:request',
    'task:stream-chunk',
    'task:stream-complete',
    'plan:approval-required',
    'plan:approved',
    'plan:rejected',
    'plan:modified',
    // 添加步骤事件
    'step:started',
    'step:completed',
    'step:failed',
]);
```

#### 步骤 2.3: 更新 Preload API

**文件**: `aios/packages/client/src/preload/index.ts`

**确认步骤事件监听器已存在**:

```typescript
// 已存在，无需修改
step: {
    onStarted: (callback: (data: any) => void) => {
        ipcRenderer.on('step:started', (event, data) => callback(data));
    },
    onCompleted: (callback: (data: any) => void) => {
        ipcRenderer.on('step:completed', (event, data) => callback(data));
    },
    onFailed: (callback: (data: any) => void) => {
        ipcRenderer.on('step:failed', (event, data) => callback(data));
    },
},
```

**预计时间**: 2-3 小时


### 阶段 3: 优化 AI 提示词（1 小时）

#### 步骤 3.1: 改进 TaskPlanner 提示词

**文件**: `aios/packages/daemon/src/core/TaskPlanner.ts`

**当前 `buildDetailedPlanningPrompt()` 方法已经很好，但可以微调**:

```typescript
private buildDetailedPlanningPrompt(availableTools: InternalToolDefinition[]): string {
    return `你是一个高级任务规划器。请仔细分析用户的请求，制定一个详尽的执行方案。

## 可用工具
${this.formatTools(availableTools)}

## 输出格式
请以 JSON 格式输出执行计划：
{
  "goal": "任务目标描述",
  "summary": "给用户看的简洁计划摘要（一句话）",
  "rationale": "# 方案分析\\n\\n## 任务理解\\n\\n[详细分析用户的核心需求和期望结果，说明你对任务的理解]\\n\\n## 技术选型\\n\\n[解释为什么选择这些工具和方法，有什么优势]\\n\\n## 实施策略\\n\\n[说明步骤设计的逻辑和顺序，为什么这样安排]\\n\\n## 风险考虑\\n\\n[识别潜在问题和应对措施，让用户了解可能的风险]\\n\\n## 预期结果\\n\\n[说明执行后会达到什么效果]",
  "risks": [
    {
      "level": "low|medium|high",
      "description": "风险描述",
      "mitigation": "缓解措施（可选）"
    }
  ],
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

## 规划原则
1. **先思考，后行动**：在 rationale 字段中详细展示你的思考过程
2. 将复杂任务分解为简单步骤（每步应该是原子操作）
3. 标注步骤之间的依赖关系（dependsOn 数组）
4. 需要屏幕理解时设置 requiresVision: true
5. action 必须是上面"可用工具"列表中的 tool_name
6. 识别并评估潜在风险（特别关注文件操作、系统命令、网络请求）
7. 为每个步骤估算执行时间（毫秒）
8. 考虑步骤失败的可能性和恢复方案

## Rationale 编写要求
- 使用 Markdown 格式，分为 4-5 个小节
- 每节 2-4 段，简洁清晰
- 重点说明"为什么"而不是"是什么"
- 帮助用户理解 AI 的思考过程和决策依据
- 如果有多种实现方式，说明为什么选择当前方案
- 用通俗易懂的语言，避免过于技术化

## 风险评估指南
- **high**: 可能导致数据丢失、系统崩溃、安全问题
- **medium**: 可能影响性能、需要较长时间、依赖外部服务
- **low**: 一般性提示，不影响核心功能

## 示例
用户请求："创建一个包含用户信息的 JSON 文件"

{
  "goal": "创建包含用户信息的 JSON 文件",
  "summary": "在当前目录创建 users.json 文件并写入示例数据",
  "rationale": "# 方案分析\\n\\n## 任务理解\\n\\n用户希望创建一个 JSON 文件来存储用户信息。这是一个常见的数据持久化需求，通常用于配置管理或数据导出。\\n\\n## 技术选型\\n\\n我们将使用文件系统适配器的 write_file 能力。JSON 格式易于阅读和编辑，且被广泛支持。\\n\\n## 实施策略\\n\\n1. 首先准备 JSON 数据结构（包含常见的用户字段）\\n2. 使用 file_write 工具写入文件\\n3. 验证文件是否成功创建\\n\\n## 风险考虑\\n\\n如果当前目录已存在同名文件，将被覆盖。建议用户确认文件路径。\\n\\n## 预期结果\\n\\n执行后将在当前目录生成 users.json 文件，包含示例用户数据。",
  "risks": [
    {
      "level": "medium",
      "description": "如果文件已存在，将被覆盖",
      "mitigation": "建议先检查文件是否存在"
    }
  ],
  "steps": [
    {
      "id": 1,
      "description": "创建 users.json 文件并写入用户数据",
      "action": "file_write",
      "params": {
        "path": "./users.json",
        "content": "[{\\"id\\": 1, \\"name\\": \\"张三\\", \\"email\\": \\"zhangsan@example.com\\"}]"
      },
      "requiresVision": false,
      "dependsOn": [],
      "estimatedTime": 2000
    }
  ]
}
`;
}
```

**预计时间**: 1 小时

### 阶段 4: 确认配置启用（10 分钟）

#### 步骤 4.1: 检查 daemon 初始化配置

**文件**: `aios/packages/daemon/src/index.ts`

**搜索 TaskOrchestrator 初始化代码**:

```bash
# 在项目根目录执行
grep -n "new TaskOrchestrator" aios/packages/daemon/src/index.ts
```

**确认配置**:
```typescript
const orchestrator = new TaskOrchestrator({
    fastEngine,
    visionEngine,
    smartEngine,
    adapterRegistry,
    confirmationManager,
    enableConfirmation: true,
    enableReAct: false,
    skillRegistry,
    projectMemoryManager,
    enableSkills: true,
    enableOrchestratorWorker: false,
    maxWorkers: 5,
    hookManager,
    // 确认这两个配置存在
    enablePlanConfirmation: true,  // ← 确认启用
    planConfirmationTimeout: 5 * 60 * 1000,  // 5 分钟
});
```

**如果不存在，添加配置**:
```typescript
enablePlanConfirmation: true,
planConfirmationTimeout: 5 * 60 * 1000,
```

**预计时间**: 10 分钟

## 三、测试计划

### 3.1 单元测试

#### 测试 PlanConfirmationManager

```bash
cd aios/packages/daemon
npm test -- PlanConfirmationManager.test.ts
```

#### 测试 TaskPlanner

```bash
npm test -- TaskPlanner.test.ts
```

### 3.2 集成测试

#### 测试场景 1: 简单任务（不触发审批）

**输入**: "调节音量到 50%"

**预期**:
- 不显示 PlanPreview
- 直接执行

#### 测试场景 2: 复杂任务（触发审批）

**输入**: "创建一个包含 5 个文件的项目结构，每个文件写入不同内容"

**预期**:
1. 显示 PlanPreview 弹窗
2. 显示 5 个步骤
3. 显示风险评估（文件操作）
4. 显示所需权限（filesystem）
5. 点击"确认执行"后开始执行
6. TaskBoard 显示进度

#### 测试场景 3: 拒绝计划

**输入**: 同上

**操作**:
1. 点击"取消"按钮
2. 输入拒绝原因："我不需要这么多文件"
3. 点击"确认拒绝"

**预期**:
- PlanPreview 关闭
- 任务不执行
- 显示拒绝消息

#### 测试场景 4: 超时场景

**输入**: 同上

**操作**:
1. 显示 PlanPreview
2. 等待 5 分钟不操作

**预期**:
- 自动超时
- 显示超时错误消息

### 3.3 性能测试

#### 测试计划生成速度

**目标**: 计划生成应在 3 秒内完成

**测试**:
```typescript
const start = Date.now();
const plan = await taskPlanner.planTaskDetailed(taskId, input, tools);
const duration = Date.now() - start;
console.log(`Plan generation took ${duration}ms`);
// 应该 < 3000ms
```

## 四、部署清单

### 4.1 代码修改清单

- [ ] `aios/packages/client/src/renderer/src/views/ChatView.tsx` - 集成 PlanPreview
- [ ] `aios/packages/client/src/renderer/src/views/ChatView.css` - 添加样式
- [ ] `aios/packages/daemon/src/core/TaskOrchestrator.ts` - 添加步骤事件
- [ ] `aios/packages/daemon/src/core/TaskPlanner.ts` - 优化提示词（可选）
- [ ] `aios/packages/daemon/src/index.ts` - 确认配置启用

### 4.2 测试清单

- [ ] 单元测试通过
- [ ] 简单任务测试通过
- [ ] 复杂任务审批测试通过
- [ ] 拒绝计划测试通过
- [ ] 超时场景测试通过
- [ ] 性能测试通过

### 4.3 文档更新

- [ ] 更新用户手册（如何使用计划审批功能）
- [ ] 更新开发文档（如何配置 enablePlanConfirmation）
- [ ] 添加示例截图

## 五、风险和注意事项

### 5.1 潜在风险

1. **用户体验**: 频繁的审批可能打断用户工作流
   - **缓解**: 调整 `isPlanSignificant()` 阈值，只对真正复杂的任务触发审批

2. **性能影响**: 详细计划生成可能增加延迟
   - **缓解**: 优化 AI 提示词，使用更快的模型

3. **超时处理**: 用户长时间不响应
   - **缓解**: 已实现 5 分钟超时机制

### 5.2 回滚计划

如果出现问题，可以快速回滚：

```typescript
// 在 daemon/src/index.ts 中
const orchestrator = new TaskOrchestrator({
    // ...
    enablePlanConfirmation: false,  // 禁用计划确认
});
```

## 六、总结

### 6.1 实际工作量

| 阶段 | 预计时间 | 实际复杂度 |
|------|---------|-----------|
| ChatView 集成 | 1-2 小时 | 低 |
| 步骤级事件 | 2-3 小时 | 中 |
| 提示词优化 | 1 小时 | 低 |
| 配置确认 | 10 分钟 | 极低 |
| 测试 | 1 小时 | 中 |
| **总计** | **5-7 小时** | **中等** |

### 6.2 关键发现

1. **AIOS 架构设计优秀**: 所有核心组件都已实现，只需要最后的集成
2. **前端组件完整**: PlanPreview 组件功能丰富，UI 美观
3. **IPC 通信完善**: 事件转发机制健全
4. **唯一缺失**: ChatView 没有使用已有的组件

### 6.3 建议

1. **优先级 P0**: ChatView 集成（必须）
2. **优先级 P1**: 步骤级事件（重要，提升用户体验）
3. **优先级 P2**: 提示词优化（可选，逐步改进）

### 6.4 后续优化方向

1. **评论系统**: 允许用户在计划上添加注释（类似 Google Docs）
2. **计划模板**: 保存常用计划模板，快速复用
3. **历史记录**: 查看过去的计划和执行结果
4. **计划对比**: 对比不同版本的计划差异
5. **智能建议**: AI 根据历史数据优化计划生成

---

**文档版本**: 2.0  
**最后更新**: 2026-01-21  
**作者**: Kiro AI Assistant  
**状态**: 已审核（基于实际代码）
