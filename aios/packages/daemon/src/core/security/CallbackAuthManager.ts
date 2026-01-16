/**
 * CallbackAuthManager - 回调通道鉴权管理器
 * 提供 HMAC-SHA256 签名生成与验证
 */

import { createHmac, randomBytes } from 'crypto';
import type {
    CallbackAuth,
    CallbackPayload,
    SignedCallback,
    SignatureVerifyResult,
    CallbackAuthManagerConfig,
} from './types.js';

/**
 * 回调鉴权管理器
 */
export class CallbackAuthManager {
    /** 默认密钥 */
    private secret: string;

    /** 时间窗口（毫秒） */
    private timeWindow: number;

    /** 是否严格模式 */
    private strictMode: boolean;

    /** 签名算法 */
    private readonly algorithm = 'sha256';

    constructor(config: CallbackAuthManagerConfig = {}) {
        this.secret = config.secret ?? this.generateSecret();
        this.timeWindow = config.timeWindow ?? 5 * 60 * 1000; // 5 分钟
        this.strictMode = config.strictMode ?? false;
    }

    /**
     * 生成随机密钥
     */
    private generateSecret(): string {
        return randomBytes(32).toString('hex');
    }

    /**
     * 获取当前密钥
     */
    getSecret(): string {
        return this.secret;
    }

    /**
     * 设置新密钥
     */
    setSecret(secret: string): void {
        if (!secret || secret.length < 16) {
            throw new Error('密钥长度必须至少 16 个字符');
        }
        this.secret = secret;
    }

    /**
     * 重新生成密钥
     */
    rotateSecret(): string {
        this.secret = this.generateSecret();
        return this.secret;
    }

    /**
     * 对回调进行签名
     */
    sign(payload: CallbackPayload, secret?: string): SignedCallback {
        const timestamp = Date.now();
        const secretToUse = secret ?? this.secret;

        // 构建签名数据
        const signData = this.buildSignData(payload, timestamp);

        // 生成签名
        const signature = this.computeSignature(signData, secretToUse);

        return {
            payload,
            signature,
            timestamp,
            algorithm: 'hmac-sha256',
        };
    }

    /**
     * 验证签名
     */
    verify(signedCallback: SignedCallback, secret?: string): SignatureVerifyResult {
        const { payload, signature, timestamp, algorithm } = signedCallback;
        const secretToUse = secret ?? this.secret;

        // 检查必要字段
        if (!payload || !signature || !timestamp) {
            return {
                valid: false,
                reason: 'missing_data',
            };
        }

        // 检查算法
        if (algorithm !== 'hmac-sha256') {
            return {
                valid: false,
                reason: 'algorithm_mismatch',
            };
        }

        // 检查时间窗口
        const now = Date.now();
        const timeOffset = now - timestamp;
        if (Math.abs(timeOffset) > this.timeWindow) {
            return {
                valid: false,
                reason: 'expired',
                timeOffset,
            };
        }

        // 重新计算签名
        const signData = this.buildSignData(payload, timestamp);
        const expectedSignature = this.computeSignature(signData, secretToUse);

        // 使用时间安全比较
        const isValid = this.secureCompare(signature, expectedSignature);

        return {
            valid: isValid,
            reason: isValid ? undefined : 'invalid_signature',
            timeOffset,
        };
    }

    /**
     * 快速验证（返回布尔值）
     */
    isValid(signedCallback: SignedCallback, secret?: string): boolean {
        return this.verify(signedCallback, secret).valid;
    }

    /**
     * 构建签名数据
     */
    private buildSignData(payload: CallbackPayload, timestamp: number): string {
        // 按固定顺序序列化，确保一致性
        const normalized = {
            type: payload.type,
            taskId: payload.taskId,
            timestamp: payload.timestamp,
            data: payload.data,
        };
        return JSON.stringify(normalized) + '.' + timestamp.toString();
    }

    /**
     * 计算 HMAC-SHA256 签名
     */
    private computeSignature(data: string, secret: string): string {
        return createHmac(this.algorithm, secret)
            .update(data, 'utf8')
            .digest('hex');
    }

    /**
     * 时间安全的字符串比较
     * 防止时序攻击
     */
    private secureCompare(a: string, b: string): boolean {
        if (a.length !== b.length) {
            return false;
        }

        let result = 0;
        for (let i = 0; i < a.length; i++) {
            result |= a.charCodeAt(i) ^ b.charCodeAt(i);
        }
        return result === 0;
    }

    /**
     * 创建 Token 认证
     */
    createToken(expiresIn: number = 3600000): CallbackAuth {
        const token = randomBytes(32).toString('hex');
        return {
            method: 'token',
            token,
            expiresAt: Date.now() + expiresIn,
        };
    }

    /**
     * 验证 Token
     */
    verifyToken(auth: CallbackAuth): boolean {
        if (auth.method !== 'token') {
            return false;
        }
        if (!auth.token || !auth.expiresAt) {
            return false;
        }
        return Date.now() < auth.expiresAt;
    }

    /**
     * 是否为严格模式
     */
    isStrictMode(): boolean {
        return this.strictMode;
    }

    /**
     * 设置严格模式
     */
    setStrictMode(strict: boolean): void {
        this.strictMode = strict;
    }

    /**
     * 获取配置信息（不含密钥）
     */
    getConfig(): {
        timeWindow: number;
        strictMode: boolean;
        algorithm: string;
    } {
        return {
            timeWindow: this.timeWindow,
            strictMode: this.strictMode,
            algorithm: 'hmac-sha256',
        };
    }
}

/**
 * 默认实例
 */
export const callbackAuthManager = new CallbackAuthManager();
