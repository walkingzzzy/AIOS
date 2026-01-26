/**
 * NetworkAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const execSyncMock = vi.hoisted(() => vi.fn((command: string) => {
    if (command.includes('networksetup -getairportpower')) {
        return Buffer.from('Wi-Fi Power (en0): On');
    }
    if (command.includes('nmcli radio wifi')) {
        return Buffer.from('enabled');
    }
    if (command.includes('Bluetooth ControllerPowerState')) {
        return Buffer.from('1');
    }
    if (command.includes('bluetoothctl show')) {
        return Buffer.from('Powered: yes');
    }
    return Buffer.from('');
}));

vi.mock('child_process', async (importOriginal) => {
    const actual = await importOriginal<typeof import('child_process')>();
    return {
        ...actual,
        execSync: execSyncMock,
    };
});

import { NetworkAdapter } from '../../adapters/system/NetworkAdapter';

describe('NetworkAdapter', () => {
    let adapter: NetworkAdapter;

    beforeEach(() => {
        adapter = new NetworkAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.network');
            expect(adapter.name).toBe('网络管理');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('wifi_status');
            expect(capabilityIds).toContain('wifi_toggle');
            expect(capabilityIds).toContain('bluetooth_status');
            expect(capabilityIds).toContain('bluetooth_toggle');
        });
    });

    describe('网络状态', () => {
        it('应该能获取 WiFi 状态', async () => {
            const result = await adapter.invoke('wifi_status', {});

            if (process.platform === 'darwin' || process.platform === 'linux') {
                expect(result.success).toBe(true);
            } else {
                expect(result.success).toBe(false);
            }
        });

        it('应该能切换 WiFi', async () => {
            const result = await adapter.invoke('wifi_toggle', { enabled: true });

            if (process.platform === 'darwin' || process.platform === 'linux') {
                expect(result.success).toBe(true);
                expect((result.data as { enabled?: boolean }).enabled).toBe(true);
            } else {
                expect(result.success).toBe(false);
            }
        });

        it('应该能获取蓝牙状态', async () => {
            const result = await adapter.invoke('bluetooth_status', {});

            if (process.platform === 'darwin' || process.platform === 'linux') {
                expect(result.success).toBe(true);
            } else {
                expect(result.success).toBe(false);
            }
        });

        it('应该能切换蓝牙', async () => {
            const result = await adapter.invoke('bluetooth_toggle', { enabled: false });

            if (process.platform === 'darwin' || process.platform === 'linux') {
                expect(result.success).toBe(true);
                expect((result.data as { enabled?: boolean }).enabled).toBe(false);
            } else {
                expect(result.success).toBe(false);
            }
        });
    });
});
