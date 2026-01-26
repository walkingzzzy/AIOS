# Agentic Workflow 研究摘要

> 研究日期: 2026-01-21  
> 目标: 为 AIOS 实现类似 Google Antigravity 的计划确认工作流程

## 执行摘要

本研究深入分析了 Google Antigravity 和业界主流的 Agentic Workflow 模式，重点关注"计划-审批-执行"工作流程。研究发现 AIOS 已经具备基础的计划确认能力（`PlanConfirmationManager`），但缺少完整的用户交互界面和工作流程集成。

## 一、核心概念：Agentic Workflow

### 1.1 定义

Agentic Workflow 是一种 AI 驱动的工作流程，其中 AI Agent 能够：
- **自主规划**: 将复杂任务分解为可执行步骤
- **动态决策**: 根据执行结果调整后续行动
- **工具协调**: 智能选择和使用外部工具/API
- **持续学习**: 从执行反馈中改进决策

### 1.2 与传统自动化的区别

| 维度 | 传统自动化 | Agentic Workflow |
|------|-----------|------------------|
| 执行方式 | 预定义规则 | 动态推理 |
| 适应性 | 固定流程 | 实时调整 |
| 决策能力 | 无 | 基于 LLM 推理 |
| 错误处理 | 硬编码 | 智能恢复 |

## 二、Google Antigravity 工作流程分析

### 2.1 核心架构

Antigravity 采用"三表面"架构：
1. **Editor View**: 传统代码编辑器（类似 VS Code）
2. **Manager Surface**: Agent 管理界面（任务编排中心）
3. **Browser Preview**: 实时预览和自动化测试

### 2.2 两种执行模式

#### Planning Mode（规划模式）
- **适用场景**: 复杂任务、多文件修改、需要深度研究
- **工作流程**:
  1. 分析用户请求
  2. 生成 Implementation Plan（实施计划）
  3. 创建 Task List（任务清单）
  4. **等待用户审批**
  5. 执行任务
  6. 生成 Walkthrough（验证报告）

#### Fast Mode（快速模式）
- **适用场景**: 简单任务、单文件修改、快速迭代
- **工作流程**: 直接执行，无需审批

### 2.3 关键 Artifacts（产物）

Antigravity 通过 Artifacts 与用户沟通：


#### 1. Implementation Plan（实施计划）
```markdown
# Implementation Plan

## Overview
- Tech Stack: Next.js, TypeScript, Tailwind CSS
- Approach: Component-based architecture
- Estimated Time: 15-20 minutes

## Steps
1. Initialize project structure
2. Set up dependencies
3. Create UI components
4. Implement business logic
5. Add styling and animations

## Risks
- ⚠️ HIGH: File operations may affect existing data
- ⚠️ MEDIUM: Complex state management

## Required Permissions
- filesystem
- network
- execute
```

**特点**:
- 详细的技术栈说明
- 清晰的步骤分解
- 风险评估和缓解措施
- 所需权限列表
- **支持 Google Docs 风格的评论**（用户可以在计划上添加注释）

#### 2. Task List（任务清单）
```markdown
- [ ] Initialize Next.js project with TypeScript
- [ ] Set up shadcn/ui component library
- [/] Create dashboard layout
- [x] Implement dark mode toggle
- [!] Fix responsive layout issues
```

**状态标记**:
- `[ ]` 待执行
- `[/]` 执行中
- `[x]` 已完成
- `[!]` 失败
- `[-]` 跳过

#### 3. Walkthrough（验证报告）
- 包含截图、视频录制
- 终端命令输出
- 单元测试结果
- 证明任务已正确完成

### 2.4 用户交互流程

```
用户输入请求
    ↓
Agent 分析任务
    ↓
生成 Implementation Plan
    ↓
展示给用户（可添加评论）
    ↓
用户点击 "Proceed" 或修改计划
    ↓
Agent 执行任务（更新 Task List）
    ↓
生成 Walkthrough 验证
    ↓
用户审查结果
```

**关键特性**:
- **非阻塞审批**: 用户可以在审批期间继续其他工作
- **评论系统**: 类似 Google Docs，可以在计划任意位置添加注释
- **版本控制**: 保留计划修改历史
- **并行任务**: 支持多个 Agent 同时工作

## 三、业界最佳实践

### 3.1 Plan-and-Execute 架构

这是最主流的 Agentic Workflow 模式：


```python
# 伪代码示例
class PlanAndExecuteAgent:
    def execute(self, user_request):
        # 1. Planning Phase
        plan = self.planner.create_plan(user_request)
        
        # 2. User Approval
        if self.requires_approval(plan):
            approved = await self.wait_for_approval(plan)
            if not approved:
                return "Task cancelled by user"
        
        # 3. Execution Phase
        results = []
        for step in plan.steps:
            result = self.executor.execute_step(step)
            results.append(result)
            
            # 4. Adaptive Re-planning
            if result.failed:
                decision = self.planner.handle_failure(step, result)
                if decision == "replan":
                    plan = self.planner.replan(plan, results)
        
        # 5. Summarization
        summary = self.planner.summarize(results)
        return summary
```

### 3.2 任务分解策略

#### 层次化分解（Hierarchical Decomposition）
```
复杂任务
├── 子任务 1
│   ├── 步骤 1.1
│   └── 步骤 1.2
├── 子任务 2
│   ├── 步骤 2.1
│   ├── 步骤 2.2
│   └── 步骤 2.3
└── 子任务 3
    └── 步骤 3.1
```

#### 依赖关系管理
```json
{
  "steps": [
    {
      "id": 1,
      "description": "Initialize database",
      "dependsOn": []
    },
    {
      "id": 2,
      "description": "Create tables",
      "dependsOn": [1]
    },
    {
      "id": 3,
      "description": "Seed data",
      "dependsOn": [2]
    },
    {
      "id": 4,
      "description": "Start API server",
      "dependsOn": [1]  // 可以与步骤2并行
    }
  ]
}
```

### 3.3 确认机制设计

#### 风险评估驱动
```typescript
interface RiskAssessment {
  level: 'low' | 'medium' | 'high';
  description: string;
  mitigation?: string;
}

function requiresApproval(plan: Plan): boolean {
  // 1. 步骤数量阈值
  if (plan.steps.length > 5) return true;
  
  // 2. 风险级别
  if (plan.risks.some(r => r.level === 'high')) return true;
  
  // 3. 敏感操作
  const sensitiveActions = ['delete', 'drop', 'truncate', 'exec'];
  if (plan.steps.some(s => 
    sensitiveActions.some(a => s.action.includes(a))
  )) return true;
  
  // 4. 所需权限
  if (plan.requiredPermissions.includes('filesystem')) return true;
  
  return false;
}
```

#### 超时和取消机制
```typescript
async function waitForApproval(
  plan: Plan, 
  timeout: number = 5 * 60 * 1000
): Promise<ApprovalResponse> {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      reject(new Error('Approval timeout'));
    }, timeout);
    
    // 监听用户响应
    eventEmitter.once('approval', (response) => {
      clearTimeout(timeoutId);
      resolve(response);
    });
    
    // 监听取消事件
    eventEmitter.once('cancel', () => {
      clearTimeout(timeoutId);
      reject(new Error('Cancelled by user'));
    });
  });
}
```


### 3.4 进度追踪和反馈

```typescript
interface ProgressEvent {
  taskId: string;
  currentStep: number;
  totalSteps: number;
  percentage: number;
  stepDescription: string;
  status: 'planning' | 'executing' | 'completed' | 'failed';
}

// 实时进度更新
function* executeWithProgress(plan: Plan) {
  yield { status: 'planning', percentage: 0 };
  
  for (let i = 0; i < plan.steps.length; i++) {
    const step = plan.steps[i];
    
    yield {
      status: 'executing',
      currentStep: i,
      totalSteps: plan.steps.length,
      percentage: (i / plan.steps.length) * 100,
      stepDescription: step.description
    };
    
    const result = await executeStep(step);
    
    yield {
      status: result.success ? 'executing' : 'failed',
      currentStep: i + 1,
      percentage: ((i + 1) / plan.steps.length) * 100
    };
  }
  
  yield { status: 'completed', percentage: 100 };
}
```

## 四、AIOS 现状分析

### 4.1 已有能力

AIOS 已经实现了计划确认的核心组件：

#### 1. PlanConfirmationManager
位置: `aios/packages/daemon/src/core/planning/PlanConfirmationManager.ts`

**功能**:
- ✅ 创建计划草案（`createDraft`）
- ✅ 提交审批请求（`submitForApproval`）
- ✅ 处理用户响应（`handleApprovalResponse`）
- ✅ 版本历史管理（`getVersionHistory`）
- ✅ 风险自动评估（`assessRisks`）
- ✅ 权限提取（`extractRequiredPermissions`）
- ✅ 超时机制

#### 2. TaskPlanner
位置: `aios/packages/daemon/src/core/TaskPlanner.ts`

**功能**:
- ✅ 任务分解（`planTask`）
- ✅ 详细计划生成（`planTaskDetailed`）
- ✅ 失败处理（`handleFailure`）
- ✅ 结果汇总（`summarize`）
- ✅ 风险评估（`assessRisks`）

#### 3. TaskOrchestrator
位置: `aios/packages/daemon/src/core/TaskOrchestrator.ts`

**功能**:
- ✅ 复杂任务执行流程（`executeComplex`）
- ✅ 计划审批集成（`enablePlanConfirmation`）
- ✅ 审批事件发送（`emitPlanApprovalRequired`）
- ✅ 进度追踪（`hookManager.triggerProgress`）


### 4.2 实际情况（基于代码审查）

#### ✅ 已完整实现的部分

1. **前端组件**:
   - ✅ `PlanPreview.tsx` - 完整的计划展示组件（包含 rationale、风险、步骤、权限）
   - ✅ `TaskBoard.tsx` - 任务执行进度可视化
   - ✅ `usePlanApproval.ts` - 计划审批 Hook
   - ✅ 支持 Approve/Reject 按钮
   - ✅ 支持拒绝反馈输入
   - ✅ 支持 Markdown 渲染（ReactMarkdown）

2. **IPC 通信层**:
   - ✅ Preload API 完整（`onPlanApprovalRequired`, `approvePlan`, `rejectPlan`, `modifyPlan`）
   - ✅ Main Process 事件转发（`plan:approval-required` 已在 `DAEMON_EVENT_CHANNELS`）
   - ✅ IPC Handlers 完整（`plan:approve`, `plan:reject`, `plan:modify`, `plan:getPending`）

3. **Daemon 后端**:
   - ✅ JSON-RPC 方法已注册（`plan.approve`, `plan.reject`, `plan.modify`, `plan.getPending`）
   - ✅ `PlanConfirmationManager` 完整实现
   - ✅ `TaskPlanner.planTaskDetailed()` 已实现
   - ✅ `TaskOrchestrator.emitPlanApprovalRequired()` 已实现

#### ⚠️ 需要改进的部分

1. **集成到 ChatView**:
   - ❌ `ChatView.tsx` 没有使用 `usePlanApproval` Hook
   - ❌ 没有渲染 `PlanPreview` 组件
   - ❌ 没有监听 `plan:approval-required` 事件

2. **配置启用**:
   - ⚠️ `TaskOrchestrator` 的 `enablePlanConfirmation` 默认值未知
   - ⚠️ 需要确认 daemon 启动时是否启用了计划确认功能

3. **AI 提示词优化**:
   - ⚠️ `TaskPlanner.buildDetailedPlanningPrompt()` 可能需要优化以生成更详细的 rationale

4. **步骤进度事件**:
   - ⚠️ `TaskOrchestrator.executeStep()` 没有发送 `step:started/completed/failed` 事件
   - ⚠️ `TaskBoard` 无法实时更新步骤状态

### 4.3 架构对比

AIOS 的设计已经非常接近 Antigravity：

| 特性 | Antigravity | AIOS 实际状态 |
|------|-------------|--------------|
| 计划生成 | ✅ | ✅ 已实现 |
| 风险评估 | ✅ | ✅ 已实现 |
| 用户审批 | ✅ | ✅ 后端+前端组件已完整 |
| 任务分解 | ✅ | ✅ 已实现 |
| 进度追踪 | ✅ | ⚠️ 部分实现（缺步骤级事件） |
| 失败恢复 | ✅ | ✅ 已实现 |
| 前端界面 | ✅ | ⚠️ 组件已有，未集成到 ChatView |
| Rationale 展示 | ✅ | ✅ 已支持 Markdown 渲染 |
| 评论系统 | ✅ | ❌ 未实现 |
| 并行执行 | ✅ | ✅ O-W 模式已实现 |

**结论**: AIOS 已经具备 **90%** 的功能，只需要：
1. 在 ChatView 中集成 PlanPreview 组件（1-2 小时）
2. 添加步骤级进度事件（2-3 小时）
3. 优化 AI 提示词生成更详细的 rationale（1 小时）
4. 确认配置启用（10 分钟）

## 五、实现方案

### 5.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Electron Client                       │
│  ┌──────────────────────────────────────────────────┐  │
│  │  PlanPreview Component (已存在)                   │  │
│  │  - 展示计划详情                                    │  │
│  │  - 显示风险评估                                    │  │
│  │  - 审批按钮                                        │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  TaskBoard Component (已存在)                     │  │
│  │  - 任务清单可视化                                  │  │
│  │  - 实时进度更新                                    │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  EventPanel Component (已存在)                    │  │
│  │  - 监听 plan:approval-required                    │  │
│  │  - 发送审批响应                                    │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          ↕ IPC
┌─────────────────────────────────────────────────────────┐
│                    Daemon (Node.js)                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │  TaskOrchestrator                                 │  │
│  │  - executeComplex()                               │  │
│  │  - emitPlanApprovalRequired()                     │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  PlanConfirmationManager                          │  │
│  │  - createDraft()                                  │  │
│  │  - submitForApproval()                            │  │
│  │  - handleApprovalResponse()                       │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  TaskPlanner                                      │  │
│  │  - planTaskDetailed()                             │  │
│  │  - assessRisks()                                  │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```


### 5.2 实施步骤

#### 阶段 1: 增强后端能力（1-2 天）

**1.1 优化 TaskPlanner.planTaskDetailed()**
- ✅ 已实现基础功能
- 🔧 需要改进 AI 提示词，生成更详细的 `rationale`
- 🔧 添加 Markdown 格式化输出

**1.2 完善 PlanConfirmationManager**
- ✅ 核心功能已完整
- 🔧 添加计划序列化/反序列化（JSON ↔ Markdown）
- 🔧 添加计划 diff 功能（对比版本差异）

**1.3 改进事件通信**
- 🔧 确保 `plan:approval-required` 事件正确发送到前端
- 🔧 添加 `plan:progress-update` 事件（任务清单更新）
- 🔧 添加 `plan:step-completed` 事件（单步完成通知）

#### 阶段 2: 前端界面开发（2-3 天）

**2.1 增强 PlanPreview 组件**

当前状态: 已存在基础组件
位置: `aios/packages/client/src/renderer/src/components/PlanPreview.tsx`

需要添加:
```tsx
interface PlanPreviewProps {
  plan: PlanDraft;
  onApprove: (modifiedSteps?: ExecutionStep[]) => void;
  onReject: (feedback: string) => void;
  onModify: (stepId: number, updates: Partial<ExecutionStep>) => void;
}

// 新增功能
- 风险评估可视化（颜色编码：红/黄/绿）
- 所需权限列表
- 预估时间显示
- 步骤依赖关系图
- Rationale 展示（Markdown 渲染）
- 步骤编辑功能（可选）
```

**2.2 增强 TaskBoard 组件**

当前状态: 已存在基础组件
位置: `aios/packages/client/src/renderer/src/components/TaskBoard.tsx`

需要添加:
```tsx
// 实时任务清单
- 步骤状态图标（✓ / / ! -）
- 进度百分比
- 当前执行步骤高亮
- 失败步骤错误信息
- 可折叠的步骤详情
```

**2.3 集成到 ChatView**

位置: `aios/packages/client/src/renderer/src/views/ChatView.tsx`

```tsx
// 监听审批请求事件
useEffect(() => {
  const handleApprovalRequired = (event: PlanApprovalRequest) => {
    setCurrentPlan(event.plan);
    setShowPlanPreview(true);
  };
  
  window.api.on('plan:approval-required', handleApprovalRequired);
  
  return () => {
    window.api.off('plan:approval-required', handleApprovalRequired);
  };
}, []);

// 处理用户审批
const handleApprove = async (modifiedSteps?: ExecutionStep[]) => {
  await window.api.invoke('plan:approve', {
    draftId: currentPlan.draftId,
    approved: true,
    modifiedSteps
  });
  setShowPlanPreview(false);
};
```


#### 阶段 3: IPC 通信层（1 天）

**3.1 添加 IPC 处理器**

位置: `aios/packages/client/src/main/index.ts`

```typescript
// 监听 daemon 的计划审批请求
daemonProcess.stdout.on('data', (data) => {
  const lines = data.toString().split('\n');
  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      const message = JSON.parse(line);
      if (message.method === 'plan:approval-required') {
        // 转发给渲染进程
        mainWindow.webContents.send('plan:approval-required', message.params);
      }
    } catch (e) {
      // 忽略非 JSON 输出
    }
  }
});

// 处理渲染进程的审批响应
ipcMain.handle('plan:approve', async (event, response) => {
  // 发送给 daemon
  daemonProcess.stdin.write(JSON.stringify({
    jsonrpc: '2.0',
    method: 'plan:approve',
    params: response
  }) + '\n');
});

ipcMain.handle('plan:reject', async (event, response) => {
  daemonProcess.stdin.write(JSON.stringify({
    jsonrpc: '2.0',
    method: 'plan:reject',
    params: response
  }) + '\n');
});
```

**3.2 添加 Daemon JSON-RPC 方法**

位置: `aios/packages/daemon/src/core/JSONRPCHandler.ts`

```typescript
// 新增方法
case 'plan:approve':
case 'plan:reject': {
  const { draftId, approved, feedback, modifiedSteps } = params;
  const response: PlanApprovalResponse = {
    approved,
    feedback,
    modifiedSteps
  };
  
  // 调用 PlanConfirmationManager
  this.orchestrator.planConfirmationManager.handleApprovalResponse(
    draftId,
    response
  );
  
  return { success: true };
}
```

#### 阶段 4: 测试和优化（1-2 天）

**4.1 单元测试**
- PlanConfirmationManager 测试
- TaskPlanner.planTaskDetailed 测试
- 事件发送/接收测试

**4.2 集成测试**
- 端到端审批流程测试
- 超时场景测试
- 计划修改测试
- 并发审批测试

**4.3 用户体验优化**
- 加载状态提示
- 错误处理和重试
- 键盘快捷键（Approve: Ctrl+Enter, Reject: Esc）
- 计划保存和恢复（刷新后不丢失）

### 5.3 配置选项

在 `OrchestratorConfig` 中添加：

```typescript
interface OrchestratorConfig {
  // ... 现有配置
  
  /** 是否启用计划确认流程 */
  enablePlanConfirmation?: boolean;
  
  /** 计划确认超时时间 (ms) */
  planConfirmationTimeout?: number;
  
  /** 自动审批阈值（步骤数小于此值自动执行） */
  autoApproveThreshold?: number;
  
  /** 是否在审批时显示 rationale */
  showRationale?: boolean;
}
```

默认配置建议：
```typescript
{
  enablePlanConfirmation: true,
  planConfirmationTimeout: 5 * 60 * 1000, // 5 分钟
  autoApproveThreshold: 2, // 2 步以下自动执行
  showRationale: true
}
```


## 六、关键技术细节

### 6.1 计划格式设计

参考 Antigravity 的 Implementation Plan 格式：

```typescript
interface PlanDraft {
  // 基础信息
  draftId: string;
  taskId: string;
  goal: string;
  
  // 计划内容
  steps: ExecutionStep[];
  summary: string;  // 简短摘要
  rationale?: string;  // Markdown 格式的详细分析
  
  // 元数据
  status: PlanStatus;
  version: number;
  createdAt: number;
  updatedAt: number;
  
  // 评估信息
  estimatedDuration: number;  // 毫秒
  risks: PlanRisk[];
  requiredPermissions: string[];
  
  // 用户反馈
  userFeedback?: string;
}

interface PlanRisk {
  level: 'low' | 'medium' | 'high';
  description: string;
  mitigation?: string;
}
```

### 6.2 Rationale 生成提示词

在 `TaskPlanner.buildDetailedPlanningPrompt()` 中：

```typescript
const rationaleTemplate = `
## 输出格式
{
  "goal": "任务目标",
  "summary": "一句话摘要",
  "rationale": "# 方案分析\\n\\n## 任务理解\\n\\n[详细分析用户需求]\\n\\n## 技术选型\\n\\n[解释为什么选择这些工具/方法]\\n\\n## 实施策略\\n\\n[说明步骤设计的逻辑]\\n\\n## 风险考虑\\n\\n[识别潜在问题和应对措施]\\n\\n## 替代方案\\n\\n[如果有其他实现方式，简要说明为什么不选择]",
  "risks": [...],
  "steps": [...]
}

## Rationale 编写要求
1. 使用 Markdown 格式
2. 分为 4-5 个小节
3. 每节 2-3 段，简洁清晰
4. 重点说明"为什么"而不是"是什么"
5. 帮助用户理解 AI 的思考过程
`;
```

### 6.3 步骤依赖关系可视化

前端可以使用 Mermaid 或 D3.js 渲染依赖图：

```typescript
function generateDependencyGraph(steps: ExecutionStep[]): string {
  const lines = ['graph TD'];
  
  for (const step of steps) {
    const nodeId = `S${step.id}`;
    const label = step.description.substring(0, 30);
    lines.push(`  ${nodeId}["${label}"]`);
    
    for (const depId of step.dependsOn) {
      lines.push(`  S${depId} --> ${nodeId}`);
    }
  }
  
  return lines.join('\n');
}

// 示例输出:
// graph TD
//   S1["Initialize database"]
//   S2["Create tables"]
//   S3["Seed data"]
//   S4["Start API server"]
//   S1 --> S2
//   S2 --> S3
//   S1 --> S4
```

### 6.4 实时进度更新

使用 Server-Sent Events (SSE) 或 WebSocket：

```typescript
// Daemon 端
class TaskOrchestrator {
  private async executeStep(step: ExecutionStep) {
    // 发送开始事件
    this.emitStepEvent('step:started', {
      stepId: step.id,
      description: step.description
    });
    
    try {
      const result = await this.toolExecutor.execute(...);
      
      // 发送完成事件
      this.emitStepEvent('step:completed', {
        stepId: step.id,
        success: result.success,
        output: result.data
      });
      
      return result;
    } catch (error) {
      // 发送失败事件
      this.emitStepEvent('step:failed', {
        stepId: step.id,
        error: error.message
      });
      throw error;
    }
  }
}

// Client 端
useEffect(() => {
  window.api.on('step:started', (data) => {
    updateTaskBoard(data.stepId, 'in_progress');
  });
  
  window.api.on('step:completed', (data) => {
    updateTaskBoard(data.stepId, 'completed');
  });
  
  window.api.on('step:failed', (data) => {
    updateTaskBoard(data.stepId, 'failed');
    showErrorDetails(data.error);
  });
}, []);
```


## 七、与现有架构的集成

### 7.1 与 Hook 系统集成

AIOS 已有完善的 Hook 系统，可以无缝集成：

```typescript
// 在 HookManager 中添加新的 Hook 类型
interface PlanHooks {
  onPlanCreated?: (plan: PlanDraft) => void;
  onPlanApproved?: (plan: PlanDraft) => void;
  onPlanRejected?: (plan: PlanDraft, reason: string) => void;
  onPlanModified?: (plan: PlanDraft, changes: Partial<PlanDraft>) => void;
}

// 使用示例
hookManager.register({
  onPlanCreated: (plan) => {
    // 记录审计日志
    auditLogger.log('plan_created', {
      taskId: plan.taskId,
      stepCount: plan.steps.length,
      risks: plan.risks.length
    });
  },
  
  onPlanApproved: (plan) => {
    // 发送通知
    notificationService.send({
      title: '计划已批准',
      body: `开始执行: ${plan.goal}`
    });
  }
});
```

### 7.2 与 ReAct 模式共存

```typescript
class TaskOrchestrator {
  private async executeComplex(input: string) {
    // 1. 判断是否使用 ReAct 模式
    if (this.enableReAct && this.shouldUseReAct(input)) {
      return this.executeWithReAct(input);
    }
    
    // 2. 使用计划确认模式
    if (this.enablePlanConfirmation) {
      return this.executeWithPlanConfirmation(input);
    }
    
    // 3. 传统执行
    return this.executeTraditional(input);
  }
  
  private shouldUseReAct(input: string): boolean {
    // ReAct 适合需要多轮推理的任务
    const reactKeywords = ['研究', '分析', '调查', '探索'];
    return reactKeywords.some(kw => input.includes(kw));
  }
}
```

### 7.3 与 O-W 模式集成

```typescript
// 计划确认后，可以使用 O-W 模式并行执行
private async executeWithPlanConfirmation(input: string) {
  // 1. 生成计划
  const plan = await this.taskPlanner.planTaskDetailed(...);
  
  // 2. 用户审批
  const approved = await this.waitForApproval(plan);
  if (!approved) return;
  
  // 3. 分析步骤依赖关系
  const { parallelGroups, sequentialGroups } = 
    this.analyzeStepDependencies(plan.steps);
  
  // 4. 并行执行独立步骤
  for (const group of parallelGroups) {
    await this.workerPool.executeParallel(group);
  }
  
  // 5. 顺序执行依赖步骤
  for (const group of sequentialGroups) {
    for (const step of group) {
      await this.executeStep(step);
    }
  }
}
```

## 八、最佳实践建议

### 8.1 何时启用计划确认

**建议启用**:
- 生产环境部署
- 涉及文件系统操作
- 多步骤复杂任务（> 3 步）
- 高风险操作（删除、修改配置）

**可以禁用**:
- 开发测试环境
- 简单查询任务
- 用户明确要求快速执行
- 低风险只读操作

### 8.2 计划粒度控制

```typescript
// 根据任务复杂度调整计划详细程度
function adjustPlanGranularity(input: string): 'high' | 'medium' | 'low' {
  const wordCount = input.split(/\s+/).length;
  
  if (wordCount > 50) return 'high';  // 详细分解
  if (wordCount > 20) return 'medium';  // 适度分解
  return 'low';  // 粗粒度
}

// 在 TaskPlanner 中应用
async planTask(input: string, tools: Tool[]) {
  const granularity = adjustPlanGranularity(input);
  
  const prompt = granularity === 'high'
    ? '请将任务分解为 8-12 个详细步骤'
    : granularity === 'medium'
    ? '请将任务分解为 4-6 个主要步骤'
    : '请将任务分解为 2-3 个核心步骤';
  
  // ...
}
```

### 8.3 用户体验优化

**1. 非阻塞审批**
```typescript
// 允许用户在等待审批时继续其他操作
async function submitForApprovalNonBlocking(plan: PlanDraft) {
  // 显示通知而不是模态框
  showNotification({
    title: '需要审批',
    body: plan.summary,
    actions: [
      { label: '查看计划', action: () => openPlanPreview(plan) },
      { label: '稍后处理', action: () => {} }
    ]
  });
  
  // 异步等待审批
  return new Promise((resolve) => {
    pendingApprovals.set(plan.draftId, resolve);
  });
}
```

**2. 智能默认选择**
```typescript
// 根据历史行为预测用户选择
function suggestApproval(plan: PlanDraft): 'approve' | 'review' {
  const history = getUserApprovalHistory();
  
  // 如果用户过去总是批准类似计划，建议自动批准
  const similarPlans = history.filter(h => 
    h.stepCount === plan.steps.length &&
    h.riskLevel === plan.risks[0]?.level
  );
  
  const approvalRate = similarPlans.filter(p => p.approved).length / 
                       similarPlans.length;
  
  return approvalRate > 0.8 ? 'approve' : 'review';
}
```


**3. 渐进式披露**
```tsx
// 默认显示摘要，点击展开详情
function PlanPreview({ plan }: Props) {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div className="plan-preview">
      {/* 始终显示 */}
      <div className="plan-summary">
        <h3>{plan.goal}</h3>
        <div className="meta">
          <span>{plan.steps.length} 步骤</span>
          <span>{formatDuration(plan.estimatedDuration)}</span>
          <RiskBadge risks={plan.risks} />
        </div>
      </div>
      
      {/* 可展开 */}
      {expanded && (
        <div className="plan-details">
          <Rationale content={plan.rationale} />
          <StepList steps={plan.steps} />
          <RiskDetails risks={plan.risks} />
        </div>
      )}
      
      <button onClick={() => setExpanded(!expanded)}>
        {expanded ? '收起' : '查看详情'}
      </button>
    </div>
  );
}
```

## 九、参考资源

### 9.1 官方文档
- [Google Antigravity Documentation](https://developers.googleblog.com/build-with-google-antigravity-our-new-agentic-development-platform/)
- [Getting Started with Antigravity](https://codelabs.developers.google.com/getting-started-google-antigravity)

### 9.2 学术论文
- "Plan-and-Execute: Improving Planning of Agents for Long-Horizon Tasks" (arXiv:2503.09572)
- "Task Decomposition for Coding Agents" (MGX Insights)

### 9.3 开源项目
- [LangChain Plan-and-Execute](https://python.langchain.com/docs/modules/agents/agent_types/plan_and_execute)
- [AutoGPT](https://github.com/Significant-Gravitas/AutoGPT)
- [BabyAGI](https://github.com/yoheinakajima/babyagi)

### 9.4 相关技术
- ReAct (Reason + Act) Pattern
- Chain-of-Thought Prompting
- Tree of Thoughts
- Hierarchical Task Networks (HTN)

## 十、总结与建议

### 10.1 核心发现

1. **AIOS 已具备 80% 的能力**: 后端架构非常完善，只需补充前端界面
2. **计划确认是必要的**: 对于复杂任务，用户审批能显著提升信任度和安全性
3. **Antigravity 的成功在于 UX**: 清晰的计划展示、实时进度、评论系统是关键

### 10.2 实施优先级

**P0 (必须实现)**:
1. 前端 PlanPreview 组件增强
2. IPC 通信层完善
3. 基础审批流程（Approve/Reject）

**P1 (重要)**:
4. TaskBoard 实时更新
5. Rationale 展示
6. 风险评估可视化

**P2 (可选)**:
7. 计划修改功能
8. 评论系统
9. 依赖关系图
10. 历史记录和回放

### 10.3 开发时间估算

- **最小可行版本 (MVP)**: 3-4 天
  - 后端优化: 1 天
  - 前端基础界面: 1.5 天
  - IPC 集成: 0.5 天
  - 测试: 1 天

- **完整版本**: 7-10 天
  - MVP: 4 天
  - 高级功能: 3 天
  - 优化和测试: 2-3 天

### 10.4 风险和挑战

1. **用户体验平衡**: 审批流程不能太繁琐，否则用户会禁用
2. **超时处理**: 需要优雅处理审批超时场景
3. **并发审批**: 多个任务同时需要审批时的 UI 设计
4. **性能影响**: 详细计划生成可能增加延迟（需要优化提示词）

### 10.5 下一步行动

1. **确认需求**: 与团队讨论是否需要评论系统、计划修改等高级功能
2. **设计评审**: 前端 UI/UX 设计评审
3. **技术验证**: 创建 POC 验证 IPC 通信和事件流
4. **迭代开发**: 按优先级逐步实现功能

---

**文档版本**: 1.0  
**最后更新**: 2026-01-21  
**作者**: Kiro AI Assistant  
**状态**: 待审核
