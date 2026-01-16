/**
 * 网络管理适配器
 * 管理 WiFi、蓝牙等网络连接
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { execSync } from 'child_process';

export class NetworkAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.network';
    readonly name = '网络管理';
    readonly description = '管理 WiFi、蓝牙等网络连接';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'wifi_status',
            name: 'WiFi状态',
            description: '获取WiFi开关状态',
            permissionLevel: 'low',
        },
        {
            id: 'wifi_toggle',
            name: 'WiFi开关',
            description: '开启或关闭WiFi',
            permissionLevel: 'medium',
            parameters: [
                { name: 'enabled', type: 'boolean', required: true, description: '是否开启' },
            ],
        },
        {
            id: 'bluetooth_status',
            name: '蓝牙状态',
            description: '获取蓝牙开关状态',
            permissionLevel: 'low',
        },
        {
            id: 'bluetooth_toggle',
            name: '蓝牙开关',
            description: '开启或关闭蓝牙',
            permissionLevel: 'medium',
            parameters: [
                { name: 'enabled', type: 'boolean', required: true, description: '是否开启' },
            ],
        },
    ];

    async checkAvailability(): Promise<boolean> {
        return process.platform === 'darwin' || process.platform === 'linux';
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'wifi_status':
                    return this.getWifiStatus();
                case 'wifi_toggle':
                    return this.toggleWifi(args.enabled as boolean);
                case 'bluetooth_status':
                    return this.getBluetoothStatus();
                case 'bluetooth_toggle':
                    return this.toggleBluetooth(args.enabled as boolean);
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async getWifiStatus(): Promise<AdapterResult> {
        if (process.platform === 'darwin') {
            const output = execSync('networksetup -getairportpower en0').toString();
            return this.success({ enabled: output.includes('On') });
        } else if (process.platform === 'linux') {
            const output = execSync('nmcli radio wifi').toString().trim();
            return this.success({ enabled: output === 'enabled' });
        }
        return this.failure('UNSUPPORTED_PLATFORM', '不支持的平台');
    }

    private async toggleWifi(enabled: boolean): Promise<AdapterResult> {
        if (process.platform === 'darwin') {
            execSync(`networksetup -setairportpower en0 ${enabled ? 'on' : 'off'}`);
        } else if (process.platform === 'linux') {
            execSync(`nmcli radio wifi ${enabled ? 'on' : 'off'}`);
        } else {
            return this.failure('UNSUPPORTED_PLATFORM', '不支持的平台');
        }
        return this.success({ enabled });
    }

    private async getBluetoothStatus(): Promise<AdapterResult> {
        if (process.platform === 'darwin') {
            const output = execSync('defaults read /Library/Preferences/com.apple.Bluetooth ControllerPowerState').toString().trim();
            return this.success({ enabled: output === '1' });
        } else if (process.platform === 'linux') {
            const output = execSync('bluetoothctl show | grep Powered').toString();
            return this.success({ enabled: output.includes('yes') });
        }
        return this.failure('UNSUPPORTED_PLATFORM', '不支持的平台');
    }

    private async toggleBluetooth(enabled: boolean): Promise<AdapterResult> {
        if (process.platform === 'darwin') {
            execSync(`blueutil --power ${enabled ? '1' : '0'}`);
        } else if (process.platform === 'linux') {
            execSync(`bluetoothctl power ${enabled ? 'on' : 'off'}`);
        } else {
            return this.failure('UNSUPPORTED_PLATFORM', '不支持的平台');
        }
        return this.success({ enabled });
    }
}

export const networkAdapter = new NetworkAdapter();