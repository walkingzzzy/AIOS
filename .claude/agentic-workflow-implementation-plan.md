# AIOS Agentic Workflow 实现计划

> 基于研究摘要的详细实施方案  
> 目标: 实现类似 Google Antigravity 的计划确认工作流程

## 一、项目概述

### 1.1 目标

为 AIOS 添加完整的"计划-审批-执行"工作流程，使用户能够：
1. 在执行复杂任务前查看详细计划
2. 审批或修改执行方案
3. 实时追踪任务执行进度
4. 查看风险评估和所需权限

### 1.2 成功标准

- [ ] 用户能看到清晰的执行计划（包含步骤、风险、时间估算）
- [ ] 用户能批准或拒绝计划
- [ ] 任务执行时有实时进度反馈
- [ ] 支持计划修改（可选）
- [ ] 审批超时有优雅降级

### 1.3 非目标

- 不实现评论系统（类似 Google Docs）
- 不实现计划版本对比 UI
- 不实现多用户协作审批

## 二、技术方案

### 2.1 架构设计

```
┌─────────────────────────────────────────┐
│         Renderer Process (React)         │
│  ┌────────────────────────────────────┐ │
│  │  ChatView                          │ │
│  │  ├─ PlanPreview (增强)             │ │
│  │  ├─ TaskBoard (增强)               │ │
│  │  └─ usePlanApproval (新增 Hook)    │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
              ↕ IPC (Electron)
┌─────────────────────────────────────────┐
│         Main Process (Electron)          │
│  ┌────────────────────────────────────┐ │
│  │  IPC Handlers (新增)               │ │
│  │  ├─ plan:approval-required         │ │
│  │  ├─ plan:approve                   │ │
│  │  ├─ plan:reject                    │ │
│  │  └─ plan:progress                  │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
              ↕ JSON-RPC (stdio)
┌─────────────────────────────────────────┐
│         Daemon Process (Node.js)         │
│  ┌────────────────────────────────────┐ │
│  │  TaskOrchestrator (已有)           │ │
│  │  ├─ executeComplex (已有)          │ │
│  │  └─ emitPlanApprovalRequired (已有)│ │
│  ├────────────────────────────────────┤ │
│  │  PlanConfirmationManager (已有)    │ │
│  │  ├─ createDraft (已有)             │ │
│  │  ├─ submitForApproval (已有)       │ │
│  │  └─ handleApprovalResponse (已有)  │ │
│  ├────────────────────────────────────┤ │
│  │  TaskPlanner (需增强)              │ │
│  │  └─ planTaskDetailed (需优化)      │ │
│  ├────────────────────────────────────┤ │
│  │  JSONRPCHandler (需新增方法)       │ │
│  │  ├─ plan:approve (新增)            │ │
│  │  └─ plan:reject (新增)             │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```


### 2.2 数据流

```
用户输入复杂任务
    ↓
TaskOrchestrator.executeComplex()
    ↓
TaskPlanner.planTaskDetailed()
    ↓
PlanConfirmationManager.createDraft()
    ↓
判断是否需要审批 (isPlanSignificant)
    ↓ (需要)
PlanConfirmationManager.submitForApproval()
    ↓
发送 JSON-RPC notification: plan:approval-required
    ↓
Main Process 接收并转发给 Renderer
    ↓
Renderer 显示 PlanPreview 组件
    ↓
用户点击 Approve/Reject
    ↓
Renderer 发送 IPC: plan:approve/reject
    ↓
Main Process 转发给 Daemon (JSON-RPC)
    ↓
JSONRPCHandler 调用 PlanConfirmationManager.handleApprovalResponse()
    ↓
Promise resolve，继续执行任务
    ↓
逐步执行，发送进度事件
    ↓
完成，返回结果
```

## 三、详细实施步骤

### 阶段 1: 后端增强（1-1.5 天）

#### 任务 1.1: 优化 TaskPlanner.planTaskDetailed()

**文件**: `aios/packages/daemon/src/core/TaskPlanner.ts`

**目标**: 生成更详细的 rationale 和更准确的风险评估

**修改内容**:

```typescript
// 1. 改进 AI 提示词
private buildDetailedPlanningPrompt(availableTools: InternalToolDefinition[]): string {
    return `你是一个高级任务规划器。请仔细分析用户的请求，制定一个详尽的执行方案。

## 可用工具
${this.formatTools(availableTools)}

## 输出格式
请以 JSON 格式输出执行计划：
{
  "goal": "任务目标描述",
  "summary": "给用户看的简洁计划摘要（一句话）",
  "rationale": "# 方案分析\\n\\n## 任务理解\\n\\n[详细分析用户的核心需求和期望结果]\\n\\n## 技术选型\\n\\n[解释为什么选择这些工具和方法]\\n\\n## 实施策略\\n\\n[说明步骤设计的逻辑和顺序]\\n\\n## 风险考虑\\n\\n[识别潜在问题和应对措施]",
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
6. 识别并评估潜在风险（特别关注文件操作、系统命令）
7. 为每个步骤估算执行时间（毫秒）

## Rationale 编写要求
- 使用 Markdown 格式，分为 3-4 个小节
- 每节 2-3 段，简洁清晰
- 重点说明"为什么"而不是"是什么"
- 帮助用户理解 AI 的思考过程和决策依据
`;
}

// 2. 添加 Markdown 格式化方法
toPlanMarkdown(draft: PlanDraft): string {
    const lines: string[] = [
        `# ${draft.goal}`,
        '',
        `> 任务 ID: ${draft.taskId}`,
        `> 草案 ID: ${draft.draftId}`,
        `> 创建时间: ${new Date(draft.createdAt).toLocaleString('zh-CN')}`,
        `> 预估时间: ${Math.ceil(draft.estimatedDuration / 1000)} 秒`,
        '',
    ];

    // Rationale
    if (draft.rationale) {
        lines.push('## 方案分析', '', draft.rationale, '');
    }

    // Steps
    lines.push('## 执行步骤', '');
    for (const step of draft.steps) {
        lines.push(`### ${step.id}. ${step.description}`);
        lines.push(`- **操作**: \`${step.action}\``);
        if (step.requiresVision) {
            lines.push(`- **需要视觉分析**: 是`);
        }
        if (step.dependsOn.length > 0) {
            lines.push(`- **依赖步骤**: ${step.dependsOn.join(', ')}`);
        }
        lines.push('');
    }

    // Risks
    if (draft.risks.length > 0) {
        lines.push('## 风险评估', '');
        for (const risk of draft.risks) {
            const emoji = risk.level === 'high' ? '🔴' : risk.level === 'medium' ? '🟡' : '🟢';
            lines.push(`${emoji} **${risk.level.toUpperCase()}**: ${risk.description}`);
            if (risk.mitigation) {
                lines.push(`  - 缓解措施: ${risk.mitigation}`);
            }
            lines.push('');
        }
    }

    // Permissions
    if (draft.requiredPermissions.length > 0) {
        lines.push('## 所需权限', '');
        for (const perm of draft.requiredPermissions) {
            lines.push(`- ${perm}`);
        }
        lines.push('');
    }

    return lines.join('\n');
}
```

**测试**:
```bash
# 单元测试
npm test -- TaskPlanner.test.ts
```


#### 任务 1.2: 添加 JSON-RPC 方法

**文件**: `aios/packages/daemon/src/core/JSONRPCHandler.ts`

**目标**: 处理前端发送的审批响应

**修改内容**:

```typescript
// 在 handleRequest 方法中添加新的 case
async handleRequest(request: JSONRPCRequest): Promise<JSONRPCResponse> {
    const { method, params } = request;
    
    try {
        switch (method) {
            // ... 现有方法
            
            case 'plan:approve':
            case 'plan:reject': {
                const { draftId, approved, feedback, modifiedSteps } = params as {
                    draftId: string;
                    approved: boolean;
                    feedback?: string;
                    modifiedSteps?: ExecutionStep[];
                };
                
                const response: PlanApprovalResponse = {
                    approved,
                    feedback,
                    modifiedSteps,
                };
                
                // 调用 PlanConfirmationManager
                this.orchestrator.getPlanConfirmationManager()
                    .handleApprovalResponse(draftId, response);
                
                return {
                    jsonrpc: '2.0',
                    id: request.id,
                    result: { success: true },
                };
            }
            
            default:
                throw new Error(`Unknown method: ${method}`);
        }
    } catch (error) {
        return {
            jsonrpc: '2.0',
            id: request.id,
            error: {
                code: -32603,
                message: error instanceof Error ? error.message : 'Internal error',
            },
        };
    }
}
```

**注意**: 需要在 TaskOrchestrator 中添加 getter:

```typescript
// 在 TaskOrchestrator 类中添加
getPlanConfirmationManager(): PlanConfirmationManager {
    return this.planConfirmationManager;
}
```

#### 任务 1.3: 改进事件发送

**文件**: `aios/packages/daemon/src/core/TaskOrchestrator.ts`

**目标**: 确保事件正确发送到前端

**修改内容**:

```typescript
// 1. 改进 emitPlanApprovalRequired 方法
private emitPlanApprovalRequired(taskId: string, draft: PlanDraft): void {
    const notification = {
        jsonrpc: '2.0',
        method: 'plan:approval-required',
        params: {
            taskId,
            draftId: draft.draftId,
            plan: draft,
            // 添加格式化的 Markdown（可选）
            markdown: this.taskPlanner.toPlanMarkdown(draft),
        },
    };

    try {
        // 通过 stdout 发送给 Main Process
        process.stdout.write(JSON.stringify(notification) + '\n');
        console.log(`[TaskOrchestrator] Emitted plan:approval-required for draft ${draft.draftId}`);
    } catch (error) {
        console.error('[TaskOrchestrator] Failed to emit plan approval notification:', error);
    }
}

// 2. 添加步骤进度事件
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
            output: result.data,
        });
        
        return {
            stepId: step.id,
            success: result.success,
            output: result.data,
        };
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


### 阶段 2: Main Process IPC 层（0.5 天）

#### 任务 2.1: 添加 IPC 处理器

**文件**: `aios/packages/client/src/main/index.ts`

**目标**: 在 Main Process 中转发 Daemon 事件到 Renderer

**修改内容**:

```typescript
// 1. 监听 Daemon 的 stdout
function setupDaemonEventListeners(daemonProcess: ChildProcess, mainWindow: BrowserWindow) {
    let buffer = '';
    
    daemonProcess.stdout?.on('data', (data: Buffer) => {
        buffer += data.toString();
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // 保留不完整的行
        
        for (const line of lines) {
            if (!line.trim()) continue;
            
            try {
                const message = JSON.parse(line);
                
                // 只处理 notification（没有 id 字段）
                if (message.jsonrpc === '2.0' && message.method && !message.id) {
                    handleDaemonNotification(message, mainWindow);
                }
            } catch (e) {
                // 忽略非 JSON 输出（如日志）
            }
        }
    });
}

function handleDaemonNotification(message: any, mainWindow: BrowserWindow) {
    const { method, params } = message;
    
    switch (method) {
        case 'plan:approval-required':
            console.log('[Main] Forwarding plan:approval-required to renderer');
            mainWindow.webContents.send('plan:approval-required', params);
            break;
            
        case 'step:started':
        case 'step:completed':
        case 'step:failed':
            mainWindow.webContents.send(method, params);
            break;
            
        default:
            // 其他事件也转发
            mainWindow.webContents.send(method, params);
    }
}

// 2. 注册 IPC 处理器
function registerPlanIPCHandlers(daemonProcess: ChildProcess) {
    ipcMain.handle('plan:approve', async (event, response) => {
        console.log('[Main] Received plan:approve from renderer');
        
        const request = {
            jsonrpc: '2.0',
            method: 'plan:approve',
            params: response,
            id: Date.now(),
        };
        
        return sendToDaemon(daemonProcess, request);
    });
    
    ipcMain.handle('plan:reject', async (event, response) => {
        console.log('[Main] Received plan:reject from renderer');
        
        const request = {
            jsonrpc: '2.0',
            method: 'plan:reject',
            params: response,
            id: Date.now(),
        };
        
        return sendToDaemon(daemonProcess, request);
    });
}

function sendToDaemon(daemonProcess: ChildProcess, request: any): Promise<any> {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
            reject(new Error('Daemon request timeout'));
        }, 5000);
        
        // 监听响应
        const responseHandler = (data: Buffer) => {
            try {
                const response = JSON.parse(data.toString());
                if (response.id === request.id) {
                    clearTimeout(timeout);
                    daemonProcess.stdout?.off('data', responseHandler);
                    
                    if (response.error) {
                        reject(new Error(response.error.message));
                    } else {
                        resolve(response.result);
                    }
                }
            } catch (e) {
                // 忽略
            }
        };
        
        daemonProcess.stdout?.on('data', responseHandler);
        
        // 发送请求
        daemonProcess.stdin?.write(JSON.stringify(request) + '\n');
    });
}

// 3. 在 app.whenReady() 中调用
app.whenReady().then(() => {
    const mainWindow = createWindow();
    const daemonProcess = startDaemon();
    
    setupDaemonEventListeners(daemonProcess, mainWindow);
    registerPlanIPCHandlers(daemonProcess);
});
```

#### 任务 2.2: 添加 Preload API

**文件**: `aios/packages/client/src/preload/index.ts`

**目标**: 暴露 IPC 方法给 Renderer

**修改内容**:

```typescript
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('api', {
    // ... 现有 API
    
    // Plan Approval API
    plan: {
        onApprovalRequired: (callback: (data: any) => void) => {
            ipcRenderer.on('plan:approval-required', (event, data) => callback(data));
        },
        
        offApprovalRequired: (callback: (data: any) => void) => {
            ipcRenderer.removeListener('plan:approval-required', callback);
        },
        
        approve: (response: {
            draftId: string;
            approved: true;
            modifiedSteps?: any[];
        }) => {
            return ipcRenderer.invoke('plan:approve', response);
        },
        
        reject: (response: {
            draftId: string;
            approved: false;
            feedback: string;
        }) => {
            return ipcRenderer.invoke('plan:reject', response);
        },
    },
    
    // Step Progress API
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
});
```

**类型定义**:

**文件**: `aios/packages/client/src/renderer/src/types/global.d.ts`

```typescript
interface Window {
    api: {
        // ... 现有 API
        
        plan: {
            onApprovalRequired: (callback: (data: PlanApprovalRequest) => void) => void;
            offApprovalRequired: (callback: (data: PlanApprovalRequest) => void) => void;
            approve: (response: PlanApprovalResponse) => Promise<{ success: boolean }>;
            reject: (response: PlanApprovalResponse) => Promise<{ success: boolean }>;
        };
        
        step: {
            onStarted: (callback: (data: StepEvent) => void) => void;
            onCompleted: (callback: (data: StepEvent) => void) => void;
            onFailed: (callback: (data: StepEvent) => void) => void;
        };
    };
}

interface PlanApprovalRequest {
    taskId: string;
    draftId: string;
    plan: PlanDraft;
    markdown?: string;
}

interface PlanApprovalResponse {
    draftId: string;
    approved: boolean;
    feedback?: string;
    modifiedSteps?: ExecutionStep[];
}

interface StepEvent {
    taskId: string;
    stepId: number;
    description?: string;
    success?: boolean;
    output?: any;
    error?: string;
}
```


### 阶段 3: 前端组件开发（2-2.5 天）

#### 任务 3.1: 创建 usePlanApproval Hook

**文件**: `aios/packages/client/src/renderer/src/hooks/usePlanApproval.ts` (新建)

**目标**: 封装计划审批逻辑

**代码**:

```typescript
import { useState, useEffect, useCallback } from 'react';

interface PlanDraft {
    draftId: string;
    taskId: string;
    goal: string;
    summary: string;
    rationale?: string;
    steps: ExecutionStep[];
    risks: PlanRisk[];
    requiredPermissions: string[];
    estimatedDuration: number;
}

interface ExecutionStep {
    id: number;
    description: string;
    action: string;
    params: Record<string, unknown>;
    requiresVision: boolean;
    dependsOn: number[];
}

interface PlanRisk {
    level: 'low' | 'medium' | 'high';
    description: string;
    mitigation?: string;
}

export function usePlanApproval() {
    const [currentPlan, setCurrentPlan] = useState<PlanDraft | null>(null);
    const [isApproving, setIsApproving] = useState(false);
    
    useEffect(() => {
        const handleApprovalRequired = (data: any) => {
            console.log('[usePlanApproval] Received approval request:', data);
            setCurrentPlan(data.plan);
        };
        
        window.api.plan.onApprovalRequired(handleApprovalRequired);
        
        return () => {
            window.api.plan.offApprovalRequired(handleApprovalRequired);
        };
    }, []);
    
    const approve = useCallback(async (modifiedSteps?: ExecutionStep[]) => {
        if (!currentPlan) return;
        
        setIsApproving(true);
        try {
            await window.api.plan.approve({
                draftId: currentPlan.draftId,
                approved: true,
                modifiedSteps,
            });
            
            console.log('[usePlanApproval] Plan approved');
            setCurrentPlan(null);
        } catch (error) {
            console.error('[usePlanApproval] Approve failed:', error);
            throw error;
        } finally {
            setIsApproving(false);
        }
    }, [currentPlan]);
    
    const reject = useCallback(async (feedback: string) => {
        if (!currentPlan) return;
        
        setIsApproving(true);
        try {
            await window.api.plan.reject({
                draftId: currentPlan.draftId,
                approved: false,
                feedback,
            });
            
            console.log('[usePlanApproval] Plan rejected');
            setCurrentPlan(null);
        } catch (error) {
            console.error('[usePlanApproval] Reject failed:', error);
            throw error;
        } finally {
            setIsApproving(false);
        }
    }, [currentPlan]);
    
    const dismiss = useCallback(() => {
        setCurrentPlan(null);
    }, []);
    
    return {
        currentPlan,
        isApproving,
        approve,
        reject,
        dismiss,
    };
}
```

