/**
 * 命令执行工具
 */

import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import { getPlatform, type PlatformCommands } from './platform.js';

const execAsync = promisify(exec);

/** 命令执行结果 */
export interface CommandResult {
    stdout: string;
    stderr: string;
    exitCode: number;
}

/** 执行命令并返回结果 */
export async function runCommand(command: string): Promise<CommandResult> {
    try {
        const { stdout, stderr } = await execAsync(command);
        return { stdout: stdout.trim(), stderr: stderr.trim(), exitCode: 0 };
    } catch (error: unknown) {
        const err = error as { stdout?: string; stderr?: string; message?: string; code?: number };
        return {
            stdout: err.stdout?.trim() || '',
            stderr: err.stderr?.trim() || err.message || '',
            exitCode: err.code || 1,
        };
    }
}

/** 执行命令（静默模式） */
export async function runSilent(command: string): Promise<boolean> {
    const result = await runCommand(command);
    return result.exitCode === 0;
}

/** 根据平台执行不同命令 */
export async function runPlatformCommand(
    commands: PlatformCommands
): Promise<CommandResult> {
    const command = commands[getPlatform()];

    if (!command) {
        return {
            stdout: '',
            stderr: `Platform ${getPlatform()} not supported`,
            exitCode: 1,
        };
    }

    return runCommand(command);
}

/** 后台启动进程 */
export function spawnBackground(
    command: string,
    args: string[] = []
): ReturnType<typeof spawn> {
    return spawn(command, args, {
        detached: true,
        stdio: 'ignore',
    });
}
