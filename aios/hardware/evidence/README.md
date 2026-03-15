# evidence/

该目录提供实机跨重启证据采集的最小资产：

- `aios-boot-evidence.service`：每次开机后导出一次 boot evidence
- `aios-boot-evidence.sh`：采集 `boot_id`、kernel cmdline、`updated` deployment/boot state、`bootctl` / `firmwarectl` / `systemd-sysupdate` 输出摘要
- `scripts/build-aios-platform-media.py` 会把这些资产复制到 `out/platform-media/<platform>/bringup/assets/`，并生成 host-side pull/evaluate helper

边界：

- 它提供的是实机证据采集链，不是仓库内伪造的“实机成功”证明
- 需要在真实平台上至少采两次不同 `boot_id`，再结合 `scripts/evaluate-aios-hardware-boot-evidence.py` 做跨重启判定
