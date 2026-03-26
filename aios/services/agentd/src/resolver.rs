pub fn candidate_capabilities(intent: &str) -> Vec<String> {
    aios_core::intent::candidate_capabilities(intent)
}

#[cfg(test)]
mod tests {
    use aios_contracts::methods;

    use super::*;

    #[test]
    fn wrapper_preserves_shared_delete_priority() {
        let capabilities = candidate_capabilities("删除 /tmp/danger.txt 并清空回收站");

        assert_eq!(
            capabilities.first(),
            Some(&methods::SYSTEM_FILE_BULK_DELETE.to_string())
        );
        assert!(capabilities
            .iter()
            .any(|item| item == methods::PROVIDER_FS_OPEN));
    }

    #[test]
    fn wrapper_preserves_shared_browser_extract_detection() {
        let capabilities = candidate_capabilities("用浏览器打开 https://example.com 并提取标题");

        assert_eq!(
            capabilities.first(),
            Some(&"compat.browser.navigate".to_string())
        );
        assert!(capabilities
            .iter()
            .any(|item| item == "compat.browser.extract"));
    }
}
