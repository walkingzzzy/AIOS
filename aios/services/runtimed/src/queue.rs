use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Arc,
};

#[derive(Debug, Clone, Default)]
pub struct QueueStats {
    pending: Arc<AtomicUsize>,
}

#[derive(Debug)]
pub struct QueuePermit {
    pending: Arc<AtomicUsize>,
}

impl QueueStats {
    pub fn admit(&self, max_concurrency: u32) -> Result<QueuePermit, usize> {
        loop {
            let current = self.pending.load(Ordering::SeqCst);
            if current as u32 >= max_concurrency {
                return Err(current);
            }

            if self
                .pending
                .compare_exchange(current, current + 1, Ordering::SeqCst, Ordering::SeqCst)
                .is_ok()
            {
                return Ok(QueuePermit {
                    pending: Arc::clone(&self.pending),
                });
            }
        }
    }

    pub fn snapshot(&self) -> usize {
        self.pending.load(Ordering::SeqCst)
    }

    pub fn available_slots(&self, max_concurrency: u32) -> u32 {
        let pending = self.snapshot().min(max_concurrency as usize) as u32;
        max_concurrency.saturating_sub(pending)
    }

    pub fn is_saturated(&self, max_concurrency: u32) -> bool {
        self.snapshot() as u32 >= max_concurrency
    }
}

impl Drop for QueuePermit {
    fn drop(&mut self) {
        self.pending.fetch_sub(1, Ordering::SeqCst);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn admit_rejects_when_queue_reaches_max_concurrency() {
        let queue = QueueStats::default();
        let first = queue.admit(1).expect("first request should enter queue");

        let pending = queue
            .admit(1)
            .expect_err("second request should be rejected");
        assert_eq!(pending, 1);
        assert_eq!(queue.available_slots(1), 0);
        assert!(queue.is_saturated(1));

        drop(first);
        assert_eq!(queue.available_slots(1), 1);
        assert!(!queue.is_saturated(1));
    }
}
