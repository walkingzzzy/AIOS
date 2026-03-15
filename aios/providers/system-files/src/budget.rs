use std::sync::{
    atomic::{AtomicU32, Ordering},
    Arc,
};

#[derive(Debug, Clone)]
pub struct ConcurrencyBudget {
    max_concurrency: u32,
    in_flight: Arc<AtomicU32>,
}

impl ConcurrencyBudget {
    pub fn new(max_concurrency: u32) -> Self {
        Self {
            max_concurrency,
            in_flight: Arc::new(AtomicU32::new(0)),
        }
    }

    pub fn in_flight(&self) -> u32 {
        self.in_flight.load(Ordering::SeqCst)
    }

    pub fn try_acquire(&self, operation: &str) -> anyhow::Result<ConcurrencyPermit> {
        loop {
            let current = self.in_flight.load(Ordering::SeqCst);
            if current >= self.max_concurrency {
                anyhow::bail!(
                    "provider concurrency budget exhausted for {}: in_flight={}/max={}",
                    operation,
                    current,
                    self.max_concurrency
                );
            }

            if self
                .in_flight
                .compare_exchange(current, current + 1, Ordering::SeqCst, Ordering::SeqCst)
                .is_ok()
            {
                return Ok(ConcurrencyPermit {
                    in_flight: Arc::clone(&self.in_flight),
                });
            }
        }
    }
}

#[derive(Debug)]
pub struct ConcurrencyPermit {
    in_flight: Arc<AtomicU32>,
}

impl Drop for ConcurrencyPermit {
    fn drop(&mut self) {
        self.in_flight.fetch_sub(1, Ordering::SeqCst);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_when_budget_is_exhausted() {
        let budget = ConcurrencyBudget::new(1);
        let _permit = budget
            .try_acquire("provider.fs.open")
            .expect("first permit");
        let error = budget
            .try_acquire("provider.fs.open")
            .expect_err("second permit should fail");
        assert!(error
            .to_string()
            .contains("provider concurrency budget exhausted"));
    }

    #[test]
    fn releases_capacity_when_permit_drops() {
        let budget = ConcurrencyBudget::new(1);
        {
            let _permit = budget
                .try_acquire("provider.fs.open")
                .expect("first permit");
            assert_eq!(budget.in_flight(), 1);
        }
        assert_eq!(budget.in_flight(), 0);
        budget
            .try_acquire("provider.fs.open")
            .expect("permit after drop should succeed");
    }
}
