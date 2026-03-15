use thiserror::Error;

#[derive(Debug, Error)]
pub enum AgentdError {
    #[error("intent cannot be empty")]
    EmptyIntent,
}
