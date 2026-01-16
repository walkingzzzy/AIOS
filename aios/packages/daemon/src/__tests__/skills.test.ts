/**
 * Skills 系统单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SkillRegistry } from '../core/skills/SkillRegistry.js';
import { ProjectMemoryManager } from '../core/skills/ProjectMemoryManager.js';
import type { Skill } from '../core/skills/types.js';

describe('SkillRegistry', () => {
    let registry: SkillRegistry;

    beforeEach(() => {
        registry = new SkillRegistry({ autoDiscover: false });
    });

    describe('register', () => {
        it('should register a skill', () => {
            const skill: Skill = {
                id: 'test-skill',
                meta: {
                    name: 'Test Skill',
                    version: '1.0.0',
                    description: 'A test skill',
                    category: 'development',
                    keywords: ['test', 'debug'],
                    enabled: true,
                },
                instructions: {
                    usage: 'Use this skill for testing',
                },
            };

            registry.register(skill);
            expect(registry.count).toBe(1);
            expect(registry.get('test-skill')).toBeDefined();
        });
    });

    describe('getAll', () => {
        it('should return all skills', () => {
            const skill1: Skill = {
                id: 'skill1',
                meta: { name: 'Skill 1', version: '1.0.0', description: '', category: 'custom', keywords: [], enabled: true },
                instructions: { usage: '' },
            };
            const skill2: Skill = {
                id: 'skill2',
                meta: { name: 'Skill 2', version: '1.0.0', description: '', category: 'custom', keywords: [], enabled: true },
                instructions: { usage: '' },
            };

            registry.register(skill1);
            registry.register(skill2);

            expect(registry.getAll().length).toBe(2);
        });
    });

    describe('getEnabled', () => {
        it('should return only enabled skills', () => {
            const skill1: Skill = {
                id: 'skill1',
                meta: { name: 'Skill 1', version: '1.0.0', description: '', category: 'custom', keywords: [], enabled: true },
                instructions: { usage: '' },
            };
            const skill2: Skill = {
                id: 'skill2',
                meta: { name: 'Skill 2', version: '1.0.0', description: '', category: 'custom', keywords: [], enabled: false },
                instructions: { usage: '' },
            };

            registry.register(skill1);
            registry.register(skill2);

            expect(registry.getEnabled().length).toBe(1);
        });
    });

    describe('match', () => {
        it('should match skills by keywords', () => {
            const skill: Skill = {
                id: 'git-skill',
                meta: {
                    name: 'Git Skill',
                    version: '1.0.0',
                    description: 'Git operations',
                    category: 'development',
                    keywords: ['git', 'version control', 'commit'],
                    enabled: true,
                },
                instructions: { usage: '' },
            };

            registry.register(skill);

            const matches = registry.match('how to commit changes');
            expect(matches.length).toBe(1);
            expect(matches[0].skill.id).toBe('git-skill');
            expect(matches[0].matchedKeywords).toContain('commit');
        });

        it('should return empty for no matches', () => {
            const skill: Skill = {
                id: 'git-skill',
                meta: {
                    name: 'Git Skill',
                    version: '1.0.0',
                    description: 'Git operations',
                    category: 'development',
                    keywords: ['git'],
                    enabled: true,
                },
                instructions: { usage: '' },
            };

            registry.register(skill);

            const matches = registry.match('cooking recipes');
            expect(matches.length).toBe(0);
        });

        it('should match by name', () => {
            const skill: Skill = {
                id: 'docker-skill',
                meta: {
                    name: 'Docker',
                    version: '1.0.0',
                    description: 'Container management',
                    category: 'development',
                    keywords: ['container'],
                    enabled: true,
                },
                instructions: { usage: '' },
            };

            registry.register(skill);

            const matches = registry.match('how to use Docker');
            expect(matches.length).toBe(1);
        });
    });

    describe('getSummaries', () => {
        it('should return skill summaries', () => {
            const skill: Skill = {
                id: 'test-skill',
                meta: {
                    name: 'Test Skill',
                    version: '1.0.0',
                    description: 'A test skill',
                    category: 'development',
                    keywords: ['test'],
                    enabled: true,
                },
                instructions: { usage: '' },
            };

            registry.register(skill);

            const summaries = registry.getSummaries();
            expect(summaries.length).toBe(1);
            expect(summaries[0].name).toBe('Test Skill');
            expect(summaries[0].description).toBe('A test skill');
        });
    });

    describe('getByCategory', () => {
        it('should filter skills by category', () => {
            const devSkill: Skill = {
                id: 'dev-skill',
                meta: { name: 'Dev', version: '1.0.0', description: '', category: 'development', keywords: [], enabled: true },
                instructions: { usage: '' },
            };
            const prodSkill: Skill = {
                id: 'prod-skill',
                meta: { name: 'Prod', version: '1.0.0', description: '', category: 'productivity', keywords: [], enabled: true },
                instructions: { usage: '' },
            };

            registry.register(devSkill);
            registry.register(prodSkill);

            const devSkills = registry.getByCategory('development');
            expect(devSkills.length).toBe(1);
            expect(devSkills[0].id).toBe('dev-skill');
        });
    });
});

describe('ProjectMemoryManager', () => {
    let manager: ProjectMemoryManager;

    beforeEach(() => {
        manager = new ProjectMemoryManager({ projectDir: '/nonexistent' });
    });

    describe('load', () => {
        it('should return null for non-existent file', () => {
            const memory = manager.load();
            expect(memory).toBeNull();
        });
    });

    describe('isLoaded', () => {
        it('should return false when not loaded', () => {
            expect(manager.isLoaded()).toBe(false);
        });
    });

    describe('toSystemPromptContext', () => {
        it('should return empty string when no memory', () => {
            expect(manager.toSystemPromptContext()).toBe('');
        });
    });
});
