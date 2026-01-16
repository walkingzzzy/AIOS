import { createServer, IncomingMessage, ServerResponse, Server as HttpServer } from 'http';
import { EventEmitter } from 'events';
import { AgentCard, A2AMessage } from './A2AProtocol.js';
import { A2ATokenManager } from './A2ATokenManager.js';

export interface A2AServerConfig {
    port: number;
    agentCard: AgentCard;
    tokenSecret: string;
    tokenExpiry?: number;
}

interface TaskRecord {
    id: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    request: any;
    result?: any;
    error?: string;
    createdAt: number;
}

/**
 * A2A HTTP Server
 * 提供 Agent Card 和任务接收端点
 */
export class A2AServer extends EventEmitter {
    private server: HttpServer | null = null;
    private agentCard: AgentCard;
    private tokenManager: A2ATokenManager;
    private tasks = new Map<string, TaskRecord>();

    constructor(config: A2AServerConfig) {
        super();
        this.agentCard = config.agentCard;
        this.tokenManager = new A2ATokenManager({
            secret: config.tokenSecret,
            expirySeconds: config.tokenExpiry,
        });
    }

    /**
     * 启动 HTTP 服务器
     */
    async start(port: number, host: string = '127.0.0.1'): Promise<void> {
        return new Promise((resolve) => {
            this.server = createServer((req, res) => {
                this.handleRequest(req, res).catch((error) => {
                    console.error('[A2AServer] Request error:', error);
                    this.sendError(res, 500, 'INTERNAL_ERROR', 'Internal server error');
                });
            });

            this.server.listen(port, host, () => {
                console.log(`[A2AServer] Listening on ${host}:${port}`);
                resolve();
            });
        });
    }

    /**
     * 停止服务器
     */
    stop(): void {
        if (this.server) {
            this.server.close();
            this.server = null;
        }
    }

    /**
     * 处理 HTTP 请求
     */
    private async handleRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
        // 设置 CORS 头
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

        // 处理 OPTIONS 预检请求
        if (req.method === 'OPTIONS') {
            res.writeHead(204);
            res.end();
            return;
        }

        const url = new URL(req.url || '/', `http://${req.headers.host}`);

        // GET /.well-known/agent.json - 返回 Agent Card
        if (req.method === 'GET' && url.pathname === '/.well-known/agent.json') {
            this.sendJson(res, 200, this.agentCard);
            return;
        }

        // POST /tasks - 接收任务
        if (req.method === 'POST' && url.pathname === '/tasks') {
            await this.handleCreateTask(req, res);
            return;
        }

        // GET /tasks/:id - 查询任务状态
        if (req.method === 'GET' && url.pathname.startsWith('/tasks/')) {
            const taskId = url.pathname.split('/')[2];
            await this.handleGetTask(taskId, res);
            return;
        }

        // 404 Not Found
        this.sendError(res, 404, 'NOT_FOUND', 'Endpoint not found');
    }

    /**
     * 处理创建任务请求
     */
    private async handleCreateTask(req: IncomingMessage, res: ServerResponse): Promise<void> {
        // 验证 Authorization
        const authHeader = req.headers.authorization;
        if (!authHeader?.startsWith('Bearer ')) {
            this.sendError(res, 401, 'UNAUTHORIZED', 'Missing or invalid authorization');
            return;
        }

        const token = authHeader.replace('Bearer ', '');
        const validation = this.tokenManager.validateToken(token);
        if (!validation.valid) {
            this.sendError(res, 403, 'FORBIDDEN', validation.error || 'Invalid token');
            return;
        }

        // 读取请求体
        const body = await this.readBody(req);
        let message: A2AMessage;
        try {
            message = JSON.parse(body);
        } catch {
            this.sendError(res, 400, 'BAD_REQUEST', 'Invalid JSON');
            return;
        }

        // 验证技能权限
        if (message.payload?.skill && !this.tokenManager.hasSkillPermission(token, message.payload.skill)) {
            this.sendError(res, 403, 'SKILL_NOT_ALLOWED', `Access to skill '${message.payload.skill}' denied`);
            return;
        }

        // 创建任务记录
        const taskId = message.taskId || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const task: TaskRecord = {
            id: taskId,
            status: 'pending',
            request: message.payload,
            createdAt: Date.now(),
        };
        this.tasks.set(taskId, task);

        // 触发事件让外部处理任务
        this.emit('task', {
            taskId,
            message,
            clientId: validation.payload!.clientId,
        });

        // 返回任务 ID
        this.sendJson(res, 202, {
            taskId,
            status: 'pending',
        });
    }

    /**
     * 处理获取任务状态请求
     */
    private async handleGetTask(taskId: string, res: ServerResponse): Promise<void> {
        const task = this.tasks.get(taskId);
        if (!task) {
            this.sendError(res, 404, 'TASK_NOT_FOUND', 'Task not found');
            return;
        }

        this.sendJson(res, 200, {
            taskId: task.id,
            status: task.status,
            result: task.result,
            error: task.error,
        });
    }

    /**
     * 更新任务状态（由外部调用）
     */
    updateTaskStatus(taskId: string, status: 'processing' | 'completed' | 'failed', result?: any, error?: string): void {
        const task = this.tasks.get(taskId);
        if (task) {
            task.status = status;
            task.result = result;
            task.error = error;
        }
    }

    /**
     * 生成访问 Token
     */
    generateToken(clientId: string, skills: string[]): string {
        return this.tokenManager.generateToken(clientId, skills);
    }

    /**
     * 读取请求体
     */
    private readBody(req: IncomingMessage): Promise<string> {
        return new Promise((resolve, reject) => {
            let body = '';
            req.on('data', (chunk) => (body += chunk.toString()));
            req.on('end', () => resolve(body));
            req.on('error', reject);
        });
    }

    /**
     * 发送 JSON 响应
     */
    private sendJson(res: ServerResponse, status: number, data: any): void {
        res.writeHead(status, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(data));
    }

    /**
     * 发送错误响应
     */
    private sendError(res: ServerResponse, status: number, code: string, message: string): void {
        this.sendJson(res, status, {
            error: { code, message },
        });
    }
}
