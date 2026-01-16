/**
 * 计划模块单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { PlanManager } from '../core/planning/PlanManager.js';
import { ReActOrchestrator } from '../core/planning/ReActOrchestrator.js';
import type { PlanStep } from '../core/planning/types.js';

describe('PlanManager', () => {
    let manager: PlanManager;

    beforeEach(() => {
        manager = new PlanManager({ enableFilePersistence: false });
    });

    describe('getOrCreatePlan', () => {
        it('should create a new plan', () => {
            const plan = manager.getOrCreatePlan('task1', 'Build a feature');

            expect(plan.taskId).toBe('task1');
            expect(plan.goal).toBe('Build a feature');
            expect(plan.steps).toEqual([]);
            expect(plan.currentStepIndex).toBe(0);
        });

        it('should return existing plan', () => {
            const plan1 = manager.getOrCreatePlan('task1', 'Goal 1');
            const plan2 = manager.getOrCreatePlan('task1', 'Different Goal');

            expect(plan2.goal).toBe('Goal 1'); // Should keep original
        });

        it('should create plan with steps', () => {
            const steps: PlanStep[] = [
                { id: 1, description: 'Step 1', status: 'pending' },
                { id: 2, description: 'Step 2', status: 'pending' },
            ];
            const plan = manager.getOrCreatePlan('task1', 'Goal', steps);

            expect(plan.steps.length).toBe(2);
        });
    });

    describe('completeStep', () => {
        it('should complete a step', () => {
            const steps: PlanStep[] = [
                { id: 1, description: 'Step 1', status: 'pending' },
                { id: 2, description: 'Step 2', status: 'pending' },
            ];
            manager.getOrCreatePlan('task1', 'Goal', steps);

            const result = manager.completeStep('task1', 1, 'Done!');
            expect(result).toBe(true);

            const plan = manager.getPlan('task1');
            expect(plan?.steps[0].status).toBe('completed');
            expect(plan?.steps[0].result).toBe('Done!');
        });

        it('should advance to next step', () => {
            const steps: PlanStep[] = [
                { id: 1, description: 'Step 1', status: 'pending' },
                { id: 2, description: 'Step 2', status: 'pending' },
            ];
            manager.getOrCreatePlan('task1', 'Goal', steps);

            manager.completeStep('task1', 1, 'Done!');

            const plan = manager.getPlan('task1');
            expect(plan?.currentStepIndex).toBe(1);
        });
    });

    describe('failStep', () => {
        it('should mark step as failed', () => {
            const steps: PlanStep[] = [
                { id: 1, description: 'Step 1', status: 'pending' },
            ];
            manager.getOrCreatePlan('task1', 'Goal', steps);

            manager.failStep('task1', 1, 'Something went wrong');

            const plan = manager.getPlan('task1');
            expect(plan?.steps[0].status).toBe('failed');
            expect(plan?.steps[0].error).toBe('Something went wrong');
        });
    });

    describe('addIssue', () => {
        it('should add an issue', () => {
            manager.getOrCreatePlan('task1', 'Goal');

            manager.addIssue('task1', 'Found a bug', 'high');

            const plan = manager.getPlan('task1');
            expect(plan?.knownIssues.length).toBe(1);
            expect(plan?.knownIssues[0].description).toBe('Found a bug');
            expect(plan?.knownIssues[0].severity).toBe('high');
        });
    });

    describe('resolveIssue', () => {
        it('should resolve an issue', () => {
            manager.getOrCreatePlan('task1', 'Goal');
            manager.addIssue('task1', 'Found a bug', 'high');

            manager.resolveIssue('task1', 1, 'Fixed it!');

            const plan = manager.getPlan('task1');
            expect(plan?.knownIssues[0].resolved).toBe(true);
            expect(plan?.knownIssues[0].resolution).toBe('Fixed it!');
        });
    });

    describe('getPlanSummary', () => {
        it('should return plan summary', () => {
            const steps: PlanStep[] = [
                { id: 1, description: 'Step 1', status: 'completed' },
                { id: 2, description: 'Step 2', status: 'pending' },
            ];
            manager.getOrCreatePlan('task1', 'Build feature', steps);

            const summary = manager.getPlanSummary('task1');
            expect(summary).toContain('Build feature');
            expect(summary).toContain('1/2');
        });
    });

    describe('toPlanMarkdown', () => {
        it('should generate markdown', () => {
            const steps: PlanStep[] = [
                { id: 1, description: 'Step 1', status: 'completed', result: 'Done' },
                { id: 2, description: 'Step 2', status: 'pending' },
            ];
            manager.getOrCreatePlan('task1', 'Build feature', steps);

            const markdown = manager.toPlanMarkdown('task1');
            expect(markdown).toContain('# Task Plan: Build feature');
            expect(markdown).toContain('- [x] 1. Step 1');
            expect(markdown).toContain('- [ ] 2. Step 2');
        });
    });
});

describe('ReActOrchestrator', () => {
    let planManager: PlanManager;

    beforeEach(() => {
        planManager = new PlanManager({ enableFilePersistence: false });
    });

    it('should complete simple task', async () => {
        const mockEngine = {
            chat: vi.fn().mockResolvedValue('OK'),
        } as any;

        const orchestrator = new ReActOrchestrator(mockEngine, planManager, {
            maxIterations: 5,
            verbose: false,
        });

        const executor = vi.fn().mockResolvedValue('Step completed successfully');

        const result = await orchestrator.execute('task1', 'Simple task', executor);

        expect(result.success).toBe(true);
        expect(result.iterations).toBeGreaterThan(0);
    });

    it('should handle failures and replan', async () => {
        const mockEngine = {
            chat: vi.fn().mockResolvedValue('OK'),
        } as any;

        const orchestrator = new ReActOrchestrator(mockEngine, planManager, {
            maxIterations: 10,
            replanThreshold: 2,
            verbose: false,
        });

        let callCount = 0;
        const executor = vi.fn().mockImplementation(async () => {
            callCount++;
            if (callCount < 3) {
                return 'Error: failed to execute';
            }
            return 'Success';
        });

        const result = await orchestrator.execute('task2', 'Retry task', executor);

        expect(executor).toHaveBeenCalled();
    });

    it('should respect max iterations', async () => {
        const mockEngine = {
            chat: vi.fn().mockResolvedValue('OK'),
        } as any;

        const steps: PlanStep[] = [];
        for (let i = 1; i <= 20; i++) {
            steps.push({ id: i, description: `Step ${i}`, status: 'pending' });
        }
        planManager.getOrCreatePlan('task3', 'Long task', steps);

        const orchestrator = new ReActOrchestrator(mockEngine, planManager, {
            maxIterations: 3,
            verbose: false,
        });

        const executor = vi.fn().mockResolvedValue('Done');

        const result = await orchestrator.execute('task3', 'Long task', executor);

        expect(result.iterations).toBe(3);
    });
});
