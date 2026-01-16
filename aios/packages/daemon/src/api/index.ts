/**
 * API 模块导出
 */

export { TaskAPI } from './TaskAPI.js';
export type {
    TaskSubmitParams,
    TaskCancelParams,
    TaskStatusParams,
    TaskHistoryParams,
    TaskSubmitResult,
    TaskStatusResult,
    QueueStatusResult,
} from './TaskAPI.js';

export { ProgressAPI } from './ProgressAPI.js';
export type {
    ProgressSubscriber,
    ProgressEvent,
} from './ProgressAPI.js';

export { JSONRPCHandler } from '../core/JSONRPCHandler.js';
export type { JSONRPCRequest, JSONRPCResponse, JSONRPCError } from '@aios/shared';
export type { MethodHandler as RPCMethodHandler } from '../core/JSONRPCHandler.js';

export {
    ConfirmationManager,
    type ConfirmationRequest,
    type ConfirmationResult,
    type ConfirmationCallback,
    type IPCEmitter,
} from './ConfirmationManager.js';
