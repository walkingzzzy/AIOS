pub fn summarize(modality: &str, user_visible: bool, continuous: bool) -> String {
    let sensitivity = match modality {
        "screen" => {
            if user_visible {
                "screen-visible"
            } else {
                "screen-background"
            }
        }
        "audio" => "audio-sensitive",
        "input" => "input-events",
        "camera" => "camera-frame",
        _ => "unknown-device-object",
    };

    if continuous {
        format!("{sensitivity}:continuous")
    } else {
        format!("{sensitivity}:sampled")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn taint_marks_continuous_audio_as_sensitive() {
        assert_eq!(summarize("audio", true, true), "audio-sensitive:continuous");
    }
}
