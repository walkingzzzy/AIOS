/**
 * 平台检测工具
 */

export type Platform = 'darwin' | 'win32' | 'linux';

/** 获取当前平台 */
export function getPlatform(): Platform {
    return process.platform as Platform;
}

/** 是否为 macOS */
export function isMacOS(): boolean {
    return process.platform === 'darwin';
}

/** 是否为 Windows */
export function isWindows(): boolean {
    return process.platform === 'win32';
}

/** 是否为 Linux */
export function isLinux(): boolean {
    return process.platform === 'linux';
}

/** 根据平台选择值 */
export function platformSelect<T>(options: {
    darwin?: T;
    win32?: T;
    linux?: T;
    default: T;
}): T {
    const platform = getPlatform();
    return options[platform] ?? options.default;
}

/** 平台特定命令映射 */
export interface PlatformCommands {
    darwin?: string;
    win32?: string;
    linux?: string;
}

/** 获取平台命令 */
export function getPlatformCommand(commands: PlatformCommands): string | undefined {
    return commands[getPlatform()];
}
