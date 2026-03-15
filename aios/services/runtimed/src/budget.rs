use std::{
    collections::BTreeMap,
    sync::{Arc, Mutex},
};

use aios_contracts::RuntimeBudgetResponse;

use crate::scheduler::Scheduler;

#[derive(Debug, Clone, Default)]
struct BudgetUsage {
    total_requests: u64,
    gpu_fallbacks: u64,
    backend_request_counts: BTreeMap<String, u64>,
    last_backend: Option<String>,
    last_route_state: Option<String>,
    active_requests: u32,
    active_models: BTreeMap<String, u32>,
    active_estimated_memory_mb: u64,
    active_estimated_kv_cache_mb: u64,
}

#[derive(Debug)]
pub struct BudgetPermit {
    usage: Arc<Mutex<BudgetUsage>>,
    model: Option<String>,
    estimated_memory_mb: u64,
    estimated_kv_cache_mb: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BudgetAdmissionError {
    MaxParallelModels {
        requested_model: String,
        active_models: usize,
        limit: u32,
    },
    MemoryBudget {
        requested_mb: u64,
        active_mb: u64,
        limit_mb: u64,
    },
    KvCacheBudget {
        requested_mb: u64,
        active_mb: u64,
        limit_mb: u64,
    },
}

#[derive(Debug, Clone, Copy)]
struct BudgetEstimate {
    estimated_memory_mb: u64,
    estimated_kv_cache_mb: u64,
}

const BASE_REQUEST_MEMORY_MB: u64 = 128;
const NEW_MODEL_MEMORY_MB: u64 = 512;
const PROMPT_CHARS_PER_MEMORY_MB: usize = 4096;
const PROMPT_CHARS_PER_KV_MB: usize = 256;
const MIN_REQUEST_KV_CACHE_MB: u64 = 16;

#[derive(Debug, Clone)]
pub struct BudgetState {
    pub memory_budget_mb: u64,
    pub kv_cache_budget_mb: u64,
    pub max_concurrency: u32,
    pub max_parallel_models: u32,
    pub timeout_ms: u64,
    usage: Arc<Mutex<BudgetUsage>>,
}

impl BudgetState {
    pub fn from_scheduler(scheduler: &Scheduler) -> Self {
        Self {
            memory_budget_mb: scheduler.runtime_profile.memory_budget_mb,
            kv_cache_budget_mb: scheduler.runtime_profile.kv_cache_budget_mb,
            max_concurrency: scheduler.runtime_profile.max_concurrency,
            max_parallel_models: scheduler.runtime_profile.max_parallel_models,
            timeout_ms: scheduler.runtime_profile.timeout_ms,
            usage: Arc::new(Mutex::new(BudgetUsage::default())),
        }
    }

    pub fn record_response(&self, backend_id: &str, route_state: &str) {
        let mut usage = self.usage.lock().expect("budget usage mutex poisoned");
        usage.total_requests += 1;
        *usage
            .backend_request_counts
            .entry(backend_id.to_string())
            .or_insert(0) += 1;
        if backend_id == "local-cpu" && route_state.contains("fallback") {
            usage.gpu_fallbacks += 1;
        }
        usage.last_backend = Some(backend_id.to_string());
        usage.last_route_state = Some(route_state.to_string());
    }

    pub fn admit(
        &self,
        model: Option<&str>,
        prompt: &str,
    ) -> Result<BudgetPermit, BudgetAdmissionError> {
        let mut usage = self.usage.lock().expect("budget usage mutex poisoned");
        let is_new_model = model
            .map(|model_name| !usage.active_models.contains_key(model_name))
            .unwrap_or(false);

        if let Some(model_name) = model {
            let model_key = model_name.to_string();
            if is_new_model && usage.active_models.len() as u32 >= self.max_parallel_models {
                return Err(BudgetAdmissionError::MaxParallelModels {
                    requested_model: model_key,
                    active_models: usage.active_models.len(),
                    limit: self.max_parallel_models,
                });
            }
        }

        let estimate = self.estimate_usage(prompt, is_new_model);

        if usage.active_estimated_memory_mb + estimate.estimated_memory_mb > self.memory_budget_mb {
            return Err(BudgetAdmissionError::MemoryBudget {
                requested_mb: estimate.estimated_memory_mb,
                active_mb: usage.active_estimated_memory_mb,
                limit_mb: self.memory_budget_mb,
            });
        }

        if usage.active_estimated_kv_cache_mb + estimate.estimated_kv_cache_mb
            > self.kv_cache_budget_mb
        {
            return Err(BudgetAdmissionError::KvCacheBudget {
                requested_mb: estimate.estimated_kv_cache_mb,
                active_mb: usage.active_estimated_kv_cache_mb,
                limit_mb: self.kv_cache_budget_mb,
            });
        }

        if let Some(model_name) = model {
            let model_key = model_name.to_string();
            *usage.active_models.entry(model_key.clone()).or_insert(0) += 1;
            usage.active_requests += 1;
            usage.active_estimated_memory_mb += estimate.estimated_memory_mb;
            usage.active_estimated_kv_cache_mb += estimate.estimated_kv_cache_mb;
            return Ok(BudgetPermit {
                usage: Arc::clone(&self.usage),
                model: Some(model_key),
                estimated_memory_mb: estimate.estimated_memory_mb,
                estimated_kv_cache_mb: estimate.estimated_kv_cache_mb,
            });
        }

        usage.active_requests += 1;
        usage.active_estimated_memory_mb += estimate.estimated_memory_mb;
        usage.active_estimated_kv_cache_mb += estimate.estimated_kv_cache_mb;
        Ok(BudgetPermit {
            usage: Arc::clone(&self.usage),
            model: None,
            estimated_memory_mb: estimate.estimated_memory_mb,
            estimated_kv_cache_mb: estimate.estimated_kv_cache_mb,
        })
    }

    fn estimate_usage(&self, prompt: &str, is_new_model: bool) -> BudgetEstimate {
        let prompt_chars = prompt.chars().count();
        let prompt_memory_mb = ceil_div(prompt_chars, PROMPT_CHARS_PER_MEMORY_MB);
        let prompt_kv_cache_mb = ceil_div(prompt_chars, PROMPT_CHARS_PER_KV_MB);

        BudgetEstimate {
            estimated_memory_mb: BASE_REQUEST_MEMORY_MB
                + prompt_memory_mb
                + if is_new_model { NEW_MODEL_MEMORY_MB } else { 0 },
            estimated_kv_cache_mb: MIN_REQUEST_KV_CACHE_MB.max(prompt_kv_cache_mb),
        }
    }

    pub fn notes(&self) -> Vec<String> {
        let usage = self.usage.lock().expect("budget usage mutex poisoned");
        vec![
            format!("memory_budget_mb={}", self.memory_budget_mb),
            format!("kv_cache_budget_mb={}", self.kv_cache_budget_mb),
            format!("max_concurrency={}", self.max_concurrency),
            format!("max_parallel_models={}", self.max_parallel_models),
            format!("timeout_ms={}", self.timeout_ms),
            format!("total_requests={}", usage.total_requests),
            format!("gpu_fallbacks={}", usage.gpu_fallbacks),
            format!("active_requests={}", usage.active_requests),
            format!("active_models={}", usage.active_models.len()),
            format!(
                "active_estimated_memory_mb={}",
                usage.active_estimated_memory_mb
            ),
            format!(
                "active_estimated_kv_cache_mb={}",
                usage.active_estimated_kv_cache_mb
            ),
        ]
    }

    pub fn snapshot(&self) -> RuntimeBudgetResponse {
        let usage = self.usage.lock().expect("budget usage mutex poisoned");
        RuntimeBudgetResponse {
            memory_budget_mb: self.memory_budget_mb,
            kv_cache_budget_mb: self.kv_cache_budget_mb,
            max_concurrency: self.max_concurrency,
            max_parallel_models: self.max_parallel_models,
            timeout_ms: self.timeout_ms,
            total_requests: usage.total_requests,
            gpu_fallbacks: usage.gpu_fallbacks,
            active_requests: usage.active_requests,
            active_models: usage.active_models.len() as u32,
            active_estimated_memory_mb: usage.active_estimated_memory_mb,
            active_estimated_kv_cache_mb: usage.active_estimated_kv_cache_mb,
            backend_request_counts: usage.backend_request_counts.clone(),
            last_backend: usage.last_backend.clone(),
            last_route_state: usage.last_route_state.clone(),
        }
    }
}

impl std::fmt::Display for BudgetAdmissionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MaxParallelModels {
                requested_model,
                active_models,
                limit,
            } => write!(
                f,
                "runtime model budget exceeded: requested model {}, active_models={}, max_parallel_models={}",
                requested_model, active_models, limit
            ),
            Self::MemoryBudget {
                requested_mb,
                active_mb,
                limit_mb,
            } => write!(
                f,
                "runtime memory budget exceeded: requested={}MB, active={}MB, memory_budget_mb={}MB",
                requested_mb, active_mb, limit_mb
            ),
            Self::KvCacheBudget {
                requested_mb,
                active_mb,
                limit_mb,
            } => write!(
                f,
                "runtime kv-cache budget exceeded: requested={}MB, active={}MB, kv_cache_budget_mb={}MB",
                requested_mb, active_mb, limit_mb
            ),
        }
    }
}

impl Drop for BudgetPermit {
    fn drop(&mut self) {
        let mut usage = self.usage.lock().expect("budget usage mutex poisoned");
        usage.active_requests = usage.active_requests.saturating_sub(1);
        usage.active_estimated_memory_mb = usage
            .active_estimated_memory_mb
            .saturating_sub(self.estimated_memory_mb);
        usage.active_estimated_kv_cache_mb = usage
            .active_estimated_kv_cache_mb
            .saturating_sub(self.estimated_kv_cache_mb);
        if let Some(model) = &self.model {
            let mut remove_entry = false;
            if let Some(count) = usage.active_models.get_mut(model) {
                *count = count.saturating_sub(1);
                remove_entry = *count == 0;
            }
            if remove_entry {
                usage.active_models.remove(model);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn budget(max_parallel_models: u32) -> BudgetState {
        BudgetState {
            memory_budget_mb: 1024,
            kv_cache_budget_mb: 256,
            max_concurrency: 2,
            max_parallel_models,
            timeout_ms: 30_000,
            usage: Arc::new(Mutex::new(BudgetUsage::default())),
        }
    }

    #[test]
    fn admit_allows_multiple_requests_for_same_model() {
        let budget = budget(1);
        let first = budget
            .admit(Some("model-a"), "hello")
            .expect("first admit should pass");
        let second = budget
            .admit(Some("model-a"), "still same model")
            .expect("same model should reuse budget slot");

        let notes = budget.notes();
        assert!(notes.iter().any(|item| item == "active_requests=2"));
        assert!(notes.iter().any(|item| item == "active_models=1"));

        drop(second);
        drop(first);
    }

    #[test]
    fn admit_rejects_new_model_when_parallel_model_limit_is_reached() {
        let budget = budget(1);
        let permit = budget
            .admit(Some("model-a"), "hello")
            .expect("first admit should pass");

        let error = budget
            .admit(Some("model-b"), "world")
            .expect_err("second distinct model should be rejected");
        assert_eq!(
            error,
            BudgetAdmissionError::MaxParallelModels {
                requested_model: "model-b".to_string(),
                active_models: 1,
                limit: 1,
            }
        );

        drop(permit);
    }

    #[test]
    fn admit_rejects_when_memory_budget_is_exceeded() {
        let budget = BudgetState {
            memory_budget_mb: 600,
            kv_cache_budget_mb: 256,
            max_concurrency: 2,
            max_parallel_models: 2,
            timeout_ms: 30_000,
            usage: Arc::new(Mutex::new(BudgetUsage::default())),
        };

        let error = budget
            .admit(Some("model-a"), "short prompt")
            .expect_err("first distinct model should exceed tight memory budget");

        assert_eq!(
            error,
            BudgetAdmissionError::MemoryBudget {
                requested_mb: 641,
                active_mb: 0,
                limit_mb: 600,
            }
        );
    }

    #[test]
    fn admit_rejects_when_kv_budget_is_exceeded() {
        let budget = BudgetState {
            memory_budget_mb: 1024,
            kv_cache_budget_mb: 8,
            max_concurrency: 2,
            max_parallel_models: 2,
            timeout_ms: 30_000,
            usage: Arc::new(Mutex::new(BudgetUsage::default())),
        };

        let error = budget
            .admit(Some("model-a"), "short prompt")
            .expect_err("minimum kv-cache estimate should exceed tiny kv budget");

        assert_eq!(
            error,
            BudgetAdmissionError::KvCacheBudget {
                requested_mb: 16,
                active_mb: 0,
                limit_mb: 8,
            }
        );
    }

    #[test]
    fn snapshot_exposes_active_budget_usage() {
        let budget = budget(2);
        let permit = budget
            .admit(Some("model-a"), "hello active budget")
            .expect("admit should pass");

        let snapshot = budget.snapshot();
        assert_eq!(snapshot.active_requests, 1);
        assert_eq!(snapshot.active_models, 1);
        assert!(snapshot.active_estimated_memory_mb > 0);
        assert!(snapshot.active_estimated_kv_cache_mb > 0);

        drop(permit);
    }
}

fn ceil_div(value: usize, divisor: usize) -> u64 {
    if value == 0 {
        return 0;
    }
    value.div_ceil(divisor) as u64
}
