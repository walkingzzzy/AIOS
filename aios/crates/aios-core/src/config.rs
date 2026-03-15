use std::{env, path::PathBuf};

pub fn env_path_or(name: &str, default: impl FnOnce() -> PathBuf) -> PathBuf {
    env::var_os(name).map(PathBuf::from).unwrap_or_else(default)
}

pub fn env_optional_string(name: &str) -> Option<String> {
    env::var(name).ok()
}

pub fn env_optional_path(name: &str) -> Option<PathBuf> {
    env::var_os(name).map(PathBuf::from)
}

pub fn env_u64_or(name: &str, default: u64) -> u64 {
    env::var(name)
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(default)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn env_helpers_return_defaults_and_parse_values() {
        let path = env_path_or("AIOS_TEST_MISSING_PATH", || PathBuf::from("/tmp/default"));
        assert_eq!(path, PathBuf::from("/tmp/default"));

        std::env::set_var("AIOS_TEST_U64", "42");
        assert_eq!(env_u64_or("AIOS_TEST_U64", 7), 42);
        std::env::remove_var("AIOS_TEST_U64");

        std::env::set_var("AIOS_TEST_STR", "hello");
        assert_eq!(
            env_optional_string("AIOS_TEST_STR").as_deref(),
            Some("hello")
        );
        std::env::remove_var("AIOS_TEST_STR");
    }
}
