/**
 * AIOS Client - Electron 主进程
 */

import { app, BrowserWindow, Tray, Menu, globalShortcut, nativeImage, ipcMain } from 'electron';
import { spawn, type ChildProcess } from 'child_process';
import { join } from 'path';

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let daemonProcess: ChildProcess | null = null;
let requestId = 0;
const pendingRequests = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
let buffer = '';

const DAEMON_EVENT_CHANNELS = new Set([
    'task:progress',
    'task:complete',
    'task:error',
    'confirmation:request',
]);

/** 处理 daemon 响应 */
function processDaemonOutput(data: Buffer): void {
    buffer += data.toString();
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
        if (!line.trim()) continue;
        try {
            const message = JSON.parse(line) as {
                id?: number;
                result?: unknown;
                error?: { message?: string };
                method?: string;
                params?: unknown;
            };

            // JSON-RPC response
            if (typeof message.id === 'number') {
                const pending = pendingRequests.get(message.id);
                if (pending) {
                    pendingRequests.delete(message.id);
                    if (message.error) {
                        pending.reject(new Error(message.error.message || 'Daemon error'));
                    } else {
                        pending.resolve(message.result);
                    }
                }
                continue;
            }

            // JSON-RPC notification (events)
            if (typeof message.method === 'string' && DAEMON_EVENT_CHANNELS.has(message.method)) {
                mainWindow?.webContents.send(message.method, message.params);
            }
        } catch {
            // Ignore parse errors
        }
    }
}

/** 发送 JSON-RPC 请求到 daemon */
async function callDaemon(method: string, params?: Record<string, unknown>): Promise<unknown> {
    if (!daemonProcess?.stdin) {
        throw new Error('Daemon not running');
    }

    const id = ++requestId;
    const request = {
        jsonrpc: '2.0',
        id,
        method,
        params,
    };

    return new Promise((resolve, reject) => {
        pendingRequests.set(id, { resolve, reject });
        daemonProcess?.stdin?.write(JSON.stringify(request) + '\n');

        // 超时
        setTimeout(() => {
            if (pendingRequests.has(id)) {
                pendingRequests.delete(id);
                reject(new Error('Request timeout'));
            }
        }, 30000);
    });
}

/** 创建主窗口 */
function createMainWindow(): void {
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        minWidth: 800,
        minHeight: 600,
        title: 'AIOS',
        show: false,
        webPreferences: {
            preload: join(__dirname, '../preload/index.js'),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });

    // 加载渲染进程
    if (process.env.NODE_ENV === 'development') {
        mainWindow.loadURL('http://localhost:5173');
        mainWindow.webContents.openDevTools();
    } else {
        mainWindow.loadFile(join(__dirname, '../renderer/index.html'));
    }

    mainWindow.on('ready-to-show', () => {
        mainWindow?.show();
    });

    mainWindow.on('close', (event) => {
        // 开发模式下直接退出，生产模式下隐藏到托盘
        if (process.env.NODE_ENV === 'development') {
            app.quit();
        } else {
            event.preventDefault();
            mainWindow?.hide();
        }
    });
}

/** 创建系统托盘 */
function createTray(): void {
    // 创建托盘图标
    const iconPath = join(__dirname, '../../resources/trayTemplate.png');
    let icon: Electron.NativeImage;

    try {
        icon = nativeImage.createFromPath(iconPath);
        // macOS 需要设置为 template image 以支持深色模式
        if (process.platform === 'darwin') {
            icon.setTemplateImage(true);
        }
    } catch {
        // 如果图标加载失败，使用空图标
        icon = nativeImage.createEmpty();
    }

    tray = new Tray(icon);

    const contextMenu = Menu.buildFromTemplate([
        {
            label: '显示 AIOS',
            click: () => mainWindow?.show(),
        },
        { type: 'separator' },
        {
            label: '快速命令',
            accelerator: 'CmdOrCtrl+Shift+Space',
            click: () => showQuickLauncher(),
        },
        { type: 'separator' },
        {
            label: '设置',
            click: () => {
                mainWindow?.show();
                mainWindow?.webContents.send('navigate', '/settings');
            },
        },
        { type: 'separator' },
        {
            label: '退出',
            click: () => {
                app.quit();
            },
        },
    ]);

    tray.setToolTip('AIOS - AI 系统控制');
    tray.setContextMenu(contextMenu);

    tray.on('click', () => {
        mainWindow?.show();
    });
}

/** 显示快速启动器 */
function showQuickLauncher(): void {
    // 发送消息到渲染进程显示快速启动器
    mainWindow?.webContents.send('show-quick-launcher');
    mainWindow?.show();
}

/** 注册全局快捷键 */
function registerShortcuts(): void {
    // Cmd/Ctrl + Shift + Space 唤起快速启动器
    globalShortcut.register('CommandOrControl+Shift+Space', () => {
        showQuickLauncher();
    });
}

/** 注册 IPC 处理器 */
function registerIPCHandlers(): void {
    // 兼容旧 API：发送消息到 daemon（等同 smartChat）
    ipcMain.handle('daemon:send', async (_event, message: string) => {
        try {
            return await callDaemon('smartChat', { message, hasScreenshot: false });
        } catch (error) {
            console.error('[AIOS Client] daemon:send error:', error);
            throw error;
        }
    });

    // 获取适配器列表
    ipcMain.handle('daemon:getAdapters', async () => {
        try {
            return await callDaemon('getAdapters');
        } catch (error) {
            console.error('[AIOS Client] getAdapters error:', error);
            throw error;
        }
    });

    // 获取适配器列表（含可用状态）
    ipcMain.handle('daemon:getAdaptersWithStatus', async () => {
        try {
            return await callDaemon('getAdaptersWithStatus');
        } catch (error) {
            console.error('[AIOS Client] getAdaptersWithStatus error:', error);
            throw error;
        }
    });

    // 调用适配器能力
    ipcMain.handle('daemon:invoke', async (_event, params: { adapterId: string; capability: string; args: Record<string, unknown> }) => {
        try {
            console.log('[AIOS Client] Invoking:', params.adapterId, params.capability, params.args);
            const result = await callDaemon('invoke', params);
            console.log('[AIOS Client] Result:', result);
            return result;
        } catch (error) {
            console.error('[AIOS Client] invoke error:', error);
            throw error;
        }
    });

    // AI 对话
    ipcMain.handle('daemon:chat', async (_event, params: { messages: Array<{ role: string; content: string }> }) => {
        try {
            return await callDaemon('chat', params);
        } catch (error) {
            console.error('[AIOS Client] chat error:', error);
            throw error;
        }
    });

    // 智能对话 (三层 AI 协调)
    ipcMain.handle('daemon:smartChat', async (_event, params: { message: string; hasScreenshot?: boolean }) => {
        try {
            return await callDaemon('smartChat', params);
        } catch (error) {
            console.error('[AIOS Client] smartChat error:', error);
            throw error;
        }
    });

    // 获取 AI 配置
    ipcMain.handle('daemon:getAIConfig', async () => {
        try {
            return await callDaemon('getAIConfig');
        } catch (error) {
            console.error('[AIOS Client] getAIConfig error:', error);
            throw error;
        }
    });

    // 设置 AI 配置
    ipcMain.handle('daemon:setAIConfig', async (_event, config) => {
        try {
            return await callDaemon('setAIConfig', config);
        } catch (error) {
            console.error('[AIOS Client] setAIConfig error:', error);
            throw error;
        }
    });

    // 获取模型列表
    ipcMain.handle('daemon:fetchModels', async (_event, params) => {
        try {
            return await callDaemon('fetchModels', params);
        } catch (error) {
            console.error('[AIOS Client] fetchModels error:', error);
            throw error;
        }
    });

    // 测试 AI 连接
    ipcMain.handle('daemon:testAIConnection', async (_event, params) => {
        try {
            return await callDaemon('testAIConnection', params);
        } catch (error) {
            console.error('[AIOS Client] testAIConnection error:', error);
            throw error;
        }
    });

    // 检查权限
    ipcMain.handle('daemon:checkPermission', async (_event, params) => {
        try {
            return await callDaemon('checkPermission', params);
        } catch (error) {
            console.error('[AIOS Client] checkPermission error:', error);
            throw error;
        }
    });

    // 请求权限
    ipcMain.handle('daemon:requestPermission', async (_event, params) => {
        try {
            return await callDaemon('requestPermission', params);
        } catch (error) {
            console.error('[AIOS Client] requestPermission error:', error);
            throw error;
        }
    });

    // ============ Task API ============

    // 提交任务
    ipcMain.handle('task:submit', async (_event, params: { prompt: string; priority?: string; type?: string; metadata?: Record<string, unknown> }) => {
        try {
            return await callDaemon('task.submit', params);
        } catch (error) {
            console.error('[AIOS Client] task:submit error:', error);
            throw error;
        }
    });

    // 取消任务
    ipcMain.handle('task:cancel', async (_event, params: { taskId: string }) => {
        try {
            return await callDaemon('task.cancel', params);
        } catch (error) {
            console.error('[AIOS Client] task:cancel error:', error);
            throw error;
        }
    });

    // 获取任务状态
    ipcMain.handle('task:getStatus', async (_event, params: { taskId: string }) => {
        try {
            return await callDaemon('task.getStatus', params);
        } catch (error) {
            console.error('[AIOS Client] task:getStatus error:', error);
            throw error;
        }
    });

    // 获取队列状态
    ipcMain.handle('task:getQueue', async () => {
        try {
            return await callDaemon('task.getQueue');
        } catch (error) {
            console.error('[AIOS Client] task:getQueue error:', error);
            throw error;
        }
    });

    // 获取任务历史
    ipcMain.handle('task:getHistory', async (_event, params?: { sessionId?: string; status?: string; page?: number; pageSize?: number }) => {
        try {
            return await callDaemon('task.getHistory', params);
        } catch (error) {
            console.error('[AIOS Client] task:getHistory error:', error);
            throw error;
        }
    });

    // ============ Confirmation API ============

    // 确认响应处理器
    ipcMain.handle('confirmation:respond', async (_event, params: { requestId: string; confirmed: boolean; reason?: string }) => {
        try {
            return await callDaemon('confirmation.respond', params);
        } catch (error) {
            console.error('[AIOS Client] confirmation:respond error:', error);
            throw error;
        }
    });

    // ============ Progress Events ============

    // 窗口控制
    ipcMain.on('window:close', () => {
        mainWindow?.close();
    });

    ipcMain.on('window:minimize', () => {
        mainWindow?.minimize();
    });

    // 系统信息
    ipcMain.handle('system:info', () => {
        return {
            platform: process.platform,
            version: app.getVersion(),
        };
    });
}

/** 启动 Daemon 进程 */
function startDaemon(): void {
    const daemonPath = join(__dirname, '../../../daemon/dist/index.js');

    try {
        daemonProcess = spawn('node', [daemonPath], {
            stdio: ['pipe', 'pipe', 'inherit'],
            env: {
                ...process.env,
            },
        });

        // 监听 daemon 输出
        daemonProcess.stdout?.on('data', processDaemonOutput);

        daemonProcess.on('error', (error) => {
            console.error('[AIOS Client] Daemon error:', error);
        });

        daemonProcess.on('exit', (code) => {
            console.log(`[AIOS Client] Daemon exited with code ${code}`);
        });

        console.log('[AIOS Client] Daemon started');
    } catch (error) {
        console.error('[AIOS Client] Failed to start daemon:', error);
    }
}

/** 应用初始化 */
app.whenReady().then(() => {
    registerIPCHandlers();
    createMainWindow();
    createTray();
    registerShortcuts();
    startDaemon();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createMainWindow();
        } else {
            mainWindow?.show();
        }
    });
});

app.on('window-all-closed', () => {
    // macOS 上不退出应用
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('will-quit', () => {
    // 注销所有快捷键
    globalShortcut.unregisterAll();

    // 停止 daemon
    if (daemonProcess) {
        daemonProcess.kill();
    }
});
