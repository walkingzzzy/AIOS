// 旧版 MCP 实现 (保留兼容)
export { MCPClient } from './MCPClient.js';
export type { MCPTool, MCPClientConfig } from './MCPClient.js';
export { MCPServer } from './MCPServer.js';
export type { MCPServerConfig } from './MCPServer.js';

// 新版 MCP 实现 (官方 SDK)
export { MCPClientV2 } from './MCPClientV2.js';
export type { MCPToolV2, MCPClientV2Config } from './MCPClientV2.js';
export { MCPServerV2 } from './MCPServerV2.js';
export type { MCPServerV2Config } from './MCPServerV2.js';

// A2A 协议
export { A2AProtocol } from './A2AProtocol.js';
export type { AgentCard, A2AMessage } from './A2AProtocol.js';
export { A2ATokenManager } from './A2ATokenManager.js';
export type { TokenPayload, TokenValidationResult, A2ATokenConfig } from './A2ATokenManager.js';
export { A2AServer } from './A2AServer.js';
export type { A2AServerConfig } from './A2AServer.js';
export { A2AClient } from './A2AClient.js';
export type { A2AClientConfig } from './A2AClient.js';
