/**
 * usePlanApproval - 计划审批 Hook
 * 管理计划审批状态和操作
 */

import { useState, useEffect, useCallback } from 'react';
import type { PlanDraft } from '../components/PlanPreview';

interface UsePlanApprovalReturn {
    /** 当前待审批的计划 */
    pendingPlan: PlanDraft | null;
    /** 是否正在加载 */
    isLoading: boolean;
    /** 错误信息 */
    error: string | null;
    /** 确认计划 */
    approvePlan: (modifications?: unknown[]) => Promise<void>;
    /** 拒绝计划 */
    rejectPlan: (feedback?: string) => Promise<void>;
    /** 修改计划 */
    modifyPlan: (modifications: unknown) => Promise<void>;
    /** 清除当前计划 */
    clearPlan: () => void;
}

export function usePlanApproval(): UsePlanApprovalReturn {
    const [pendingPlan, setPendingPlan] = useState<PlanDraft | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // 监听计划审批请求
    useEffect(() => {
        if (!window.aios?.onPlanApprovalRequired) {
            console.warn('[usePlanApproval] onPlanApprovalRequired not available');
            return;
        }

        const unsubscribe = window.aios.onPlanApprovalRequired((plan) => {
            console.log('[usePlanApproval] Received plan approval request:', plan.draftId);
            setPendingPlan(plan as PlanDraft);
            setError(null);
        });

        return () => {
            if (typeof unsubscribe === 'function') {
                unsubscribe();
            }
        };
    }, []);

    // 确认计划
    const approvePlan = useCallback(async (modifications?: unknown[]) => {
        if (!pendingPlan) {
            console.warn('[usePlanApproval] No pending plan to approve');
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            const result = await window.aios.approvePlan(pendingPlan.draftId, modifications);
            if (result.success) {
                console.log('[usePlanApproval] Plan approved:', pendingPlan.draftId);
                setPendingPlan(null);
            } else {
                setError('确认计划失败');
            }
        } catch (err) {
            console.error('[usePlanApproval] Approve error:', err);
            setError(err instanceof Error ? err.message : '确认计划时发生错误');
        } finally {
            setIsLoading(false);
        }
    }, [pendingPlan]);

    // 拒绝计划
    const rejectPlan = useCallback(async (feedback?: string) => {
        if (!pendingPlan) {
            console.warn('[usePlanApproval] No pending plan to reject');
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            const result = await window.aios.rejectPlan(pendingPlan.draftId, feedback);
            if (result.success) {
                console.log('[usePlanApproval] Plan rejected:', pendingPlan.draftId);
                setPendingPlan(null);
            } else {
                setError('拒绝计划失败');
            }
        } catch (err) {
            console.error('[usePlanApproval] Reject error:', err);
            setError(err instanceof Error ? err.message : '拒绝计划时发生错误');
        } finally {
            setIsLoading(false);
        }
    }, [pendingPlan]);

    // 修改计划
    const modifyPlan = useCallback(async (modifications: unknown) => {
        if (!pendingPlan) {
            console.warn('[usePlanApproval] No pending plan to modify');
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            const result = await window.aios.modifyPlan(pendingPlan.draftId, modifications);
            if (result.success) {
                console.log('[usePlanApproval] Plan modified:', pendingPlan.draftId);
                // 修改后会收到新的 plan:modified 事件，更新 pendingPlan
            } else {
                setError('修改计划失败');
            }
        } catch (err) {
            console.error('[usePlanApproval] Modify error:', err);
            setError(err instanceof Error ? err.message : '修改计划时发生错误');
        } finally {
            setIsLoading(false);
        }
    }, [pendingPlan]);

    // 清除当前计划
    const clearPlan = useCallback(() => {
        setPendingPlan(null);
        setError(null);
    }, []);

    return {
        pendingPlan,
        isLoading,
        error,
        approvePlan,
        rejectPlan,
        modifyPlan,
        clearPlan,
    };
}

export default usePlanApproval;
