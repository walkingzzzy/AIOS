import jwt from 'jsonwebtoken';

export interface TokenPayload {
    clientId: string;
    skills: string[];
    iat: number;
}

export interface TokenValidationResult {
    valid: boolean;
    payload?: TokenPayload;
    error?: string;
}

export interface A2ATokenConfig {
    secret: string;
    expirySeconds?: number;
}

/**
 * A2A Token Manager
 * 管理 Agent-to-Agent 协议的 JWT Token 生成和验证
 */
export class A2ATokenManager {
    private secret: string;
    private expiry: number;
    private revokedTokens = new Set<string>();

    constructor(config: A2ATokenConfig) {
        if (!config.secret || config.secret.length < 32) {
            throw new Error('JWT secret must be at least 32 characters');
        }
        this.secret = config.secret;
        this.expiry = config.expirySeconds || 3600; // 默认 1 小时
    }

    /**
     * 生成 JWT Token
     * @param clientId - 客户端 ID
     * @param skills - 允许访问的技能列表
     * @returns JWT Token 字符串
     */
    generateToken(clientId: string, skills: string[]): string {
        const payload: TokenPayload = {
            clientId,
            skills,
            iat: Math.floor(Date.now() / 1000),
        };

        return jwt.sign(payload, this.secret, {
            expiresIn: this.expiry,
        });
    }

    /**
     * 验证 JWT Token
     * @param token - JWT Token 字符串
     * @returns 验证结果
     */
    validateToken(token: string): TokenValidationResult {
        // 检查是否已被撤销
        if (this.revokedTokens.has(token)) {
            return {
                valid: false,
                error: 'Token has been revoked',
            };
        }

        try {
            const payload = jwt.verify(token, this.secret) as TokenPayload;
            return {
                valid: true,
                payload,
            };
        } catch (error) {
            return {
                valid: false,
                error: error instanceof Error ? error.message : 'Unknown error',
            };
        }
    }

    /**
     * 撤销 Token
     * @param token - 要撤销的 Token
     */
    revokeToken(token: string): void {
        this.revokedTokens.add(token);
    }

    /**
     * 清理过期的撤销 Token（可定期调用以释放内存）
     */
    cleanupRevokedTokens(): void {
        const now = Math.floor(Date.now() / 1000);
        const tokensToRemove: string[] = [];

        for (const token of this.revokedTokens) {
            try {
                const decoded = jwt.decode(token) as TokenPayload;
                if (decoded && decoded.iat + this.expiry < now) {
                    tokensToRemove.push(token);
                }
            } catch {
                // 解码失败，保留在集合中
            }
        }

        tokensToRemove.forEach((token) => this.revokedTokens.delete(token));
    }

    /**
     * 检查 Token 是否包含特定技能权限
     * @param token - JWT Token
     * @param requiredSkill - 需要的技能
     * @returns 是否有权限
     */
    hasSkillPermission(token: string, requiredSkill: string): boolean {
        const result = this.validateToken(token);
        if (!result.valid || !result.payload) {
            return false;
        }
        return result.payload.skills.includes(requiredSkill) || result.payload.skills.includes('*');
    }
}
