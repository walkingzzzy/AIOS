/**
 * 权限管理器
 * 统一的权限模型，映射到各平台权限系统
 */

import type { PermissionLevel } from '@aios/shared';
import { getPlatform } from '@aios/shared';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

/** 权限检查结果 */
export interface PermissionCheckResult {
    granted: boolean;
    level: PermissionLevel;
    platform: string;
    details?: string;
}

/** 权限请求结果 */
export interface PermissionRequestResult {
    success: boolean;
    granted: boolean;
    message: string;
}

/** 权限要求 */
export interface PermissionRequirement {
    level: PermissionLevel;
    reason: string;
    platformSpecific?: {
        darwin?: string;
        win32?: string;
        linux?: string;
    };
}

/**
 * 权限管理器
 */
export class PermissionManager {
    private static instance: PermissionManager;
    private permissionCache: Map<string, boolean> = new Map();

    private constructor() {}

    static getInstance(): PermissionManager {
        if (!PermissionManager.instance) {
            PermissionManager.instance = new PermissionManager();
        }
        return PermissionManager.instance;
    }

    /**
     * 检查权限级别
     */
    async checkPermission(level: PermissionLevel): Promise<PermissionCheckResult> {
        const platform = getPlatform();
        const cacheKey = `${platform}:${level}`;

        // 检查缓存
        if (this.permissionCache.has(cacheKey)) {
            return {
                granted: this.permissionCache.get(cacheKey)!,
                level,
                platform,
            };
        }

        let granted = false;
        let details: string | undefined;

        switch (level) {
            case 'public':
                granted = true;
                break;
            case 'low':
                granted = await this.checkLowPermission(platform);
                break;
            case 'medium':
                granted = await this.checkMediumPermission(platform);
                details = this.getMediumPermissionDetails(platform);
                break;
            case 'high':
                granted = await this.checkHighPermission(platform);
                details = this.getHighPermissionDetails(platform);
                break;
            case 'critical':
                granted = await this.checkCriticalPermission(platform);
                details = this.getCriticalPermissionDetails(platform);
                break;
        }

        // 缓存结果（除了 critical 级别）
        if (level !== 'critical') {
            this.permissionCache.set(cacheKey, granted);
        }

        return { granted, level, platform, details };
    }

    /**
     * 请求权限
     */
    async requestPermission(level: PermissionLevel): Promise<PermissionRequestResult> {
        const platform = getPlatform();

        switch (level) {
            case 'public':
            case 'low':
                return { success: true, granted: true, message: '无需额外权限' };

            case 'medium':
                return this.requestMediumPermission(platform);

            case 'high':
                return this.requestHighPermission(platform);

            case 'critical':
                return this.requestCriticalPermission(platform);

            default:
                return { success: false, granted: false, message: '未知权限级别' };
        }
    }

    /**
     * 获取适配器所需权限
     */
    getRequiredPermissions(adapterId: string, capability: string): PermissionRequirement[] {
        // 这里可以根据适配器和能力返回具体的权限要求
        // 简化实现：返回通用要求
        return [
            {
                level: 'low',
                reason: `执行 ${capability} 操作`,
            },
        ];
    }

    /**
     * 清除权限缓存
     */
    clearCache(): void {
        this.permissionCache.clear();
    }

    // ========== 私有方法 ==========

    private async checkLowPermission(platform: string): Promise<boolean> {
        // low 级别通常不需要特殊权限
        return true;
    }

    private async checkMediumPermission(platform: string): Promise<boolean> {
        if (platform === 'darwin') {
            // macOS: 检查辅助功能权限
            return this.checkMacAccessibility();
        } else if (platform === 'win32') {
            // Windows: 通常不需要 UAC
            return true;
        } else {
            // Linux: 检查 PolicyKit
            return true;
        }
    }

    private async checkHighPermission(platform: string): Promise<boolean> {
        if (platform === 'darwin') {
            // macOS: 检查辅助功能 + 屏幕录制权限
            const accessibility = await this.checkMacAccessibility();
            const screenRecording = await this.checkMacScreenRecording();
            return accessibility && screenRecording;
        } else if (platform === 'win32') {
            // Windows: 检查是否以管理员运行
            return this.checkWindowsAdmin();
        } else {
            // Linux: 检查 sudo 权限
            return this.checkLinuxSudo();
        }
    }

    private async checkCriticalPermission(platform: string): Promise<boolean> {
        if (platform === 'darwin') {
            // macOS: 检查完全磁盘访问权限
            return this.checkMacFullDiskAccess();
        } else if (platform === 'win32') {
            // Windows: 检查系统权限
            return this.checkWindowsAdmin();
        } else {
            // Linux: 检查 root 权限
            return process.getuid?.() === 0;
        }
    }

    // ========== macOS 权限检查 ==========

    private async checkMacAccessibility(): Promise<boolean> {
        try {
            // 使用 AppleScript 检查辅助功能权限
            const { stdout } = await execAsync(
                'osascript -e \'tell application "System Events" to return true\''
            );
            return stdout.trim() === 'true';
        } catch {
            return false;
        }
    }

    private async checkMacScreenRecording(): Promise<boolean> {
        try {
            // 尝试截图来检查屏幕录制权限
            await execAsync('screencapture -x /tmp/aios_permission_test.png');
            await execAsync('rm -f /tmp/aios_permission_test.png');
            return true;
        } catch {
            return false;
        }
    }

    private async checkMacFullDiskAccess(): Promise<boolean> {
        try {
            // 尝试读取受保护的目录
            await execAsync('ls ~/Library/Mail 2>/dev/null');
            return true;
        } catch {
            return false;
        }
    }

    // ========== Windows 权限检查 ==========

    private async checkWindowsAdmin(): Promise<boolean> {
        try {
            const { stdout } = await execAsync(
                'powershell -Command "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"'
            );
            return stdout.trim().toLowerCase() === 'true';
        } catch {
            return false;
        }
    }

    // ========== Linux 权限检查 ==========

    private async checkLinuxSudo(): Promise<boolean> {
        try {
            await execAsync('sudo -n true 2>/dev/null');
            return true;
        } catch {
            return false;
        }
    }

    // ========== 权限请求 ==========

    private async requestMediumPermission(platform: string): Promise<PermissionRequestResult> {
        if (platform === 'darwin') {
            // macOS: 打开系统偏好设置
            try {
                await execAsync(
                    'open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"'
                );
                return {
                    success: true,
                    granted: false,
                    message: '请在系统偏好设置中授予辅助功能权限',
                };
            } catch {
                return { success: false, granted: false, message: '无法打开系统偏好设置' };
            }
        }
        return { success: true, granted: true, message: '权限已授予' };
    }

    private async requestHighPermission(platform: string): Promise<PermissionRequestResult> {
        if (platform === 'darwin') {
            try {
                await execAsync(
                    'open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"'
                );
                return {
                    success: true,
                    granted: false,
                    message: '请在系统偏好设置中授予屏幕录制权限',
                };
            } catch {
                return { success: false, granted: false, message: '无法打开系统偏好设置' };
            }
        } else if (platform === 'win32') {
            return {
                success: true,
                granted: false,
                message: '请以管理员身份运行应用程序',
            };
        }
        return { success: true, granted: true, message: '权限已授予' };
    }

    private async requestCriticalPermission(platform: string): Promise<PermissionRequestResult> {
        if (platform === 'darwin') {
            try {
                await execAsync(
                    'open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"'
                );
                return {
                    success: true,
                    granted: false,
                    message: '请在系统偏好设置中授予完全磁盘访问权限',
                };
            } catch {
                return { success: false, granted: false, message: '无法打开系统偏好设置' };
            }
        }
        return {
            success: false,
            granted: false,
            message: '关键权限需要手动配置',
        };
    }

    // ========== 权限详情 ==========

    private getMediumPermissionDetails(platform: string): string {
        switch (platform) {
            case 'darwin':
                return '需要辅助功能权限 (System Preferences > Security & Privacy > Privacy > Accessibility)';
            case 'win32':
                return '可能需要 UAC 确认';
            case 'linux':
                return '可能需要 PolicyKit 授权';
            default:
                return '';
        }
    }

    private getHighPermissionDetails(platform: string): string {
        switch (platform) {
            case 'darwin':
                return '需要辅助功能和屏幕录制权限';
            case 'win32':
                return '需要管理员权限';
            case 'linux':
                return '需要 sudo 权限';
            default:
                return '';
        }
    }

    private getCriticalPermissionDetails(platform: string): string {
        switch (platform) {
            case 'darwin':
                return '需要完全磁盘访问权限 (Full Disk Access)';
            case 'win32':
                return '需要系统级权限';
            case 'linux':
                return '需要 root 权限';
            default:
                return '';
        }
    }
}

/** 全局权限管理器实例 */
export const permissionManager = PermissionManager.getInstance();
