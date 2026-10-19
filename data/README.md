# Data layout

当前唯一正式版本是 [`v2_2.6.0/`](v2_2.6.0/)；[`current.json`](current.json) 指向它。

- `v2_2.6.0/cases.jsonl`: 1,084 case、3,872 unit 的正式 manifest；
- `v2_2.6.0/statistics.json`: 机器统计；
- `v2_2.6.0/validation.json`: 构建/资产/几何/协议校验回执；
- `v2_2.6.0/release.json`: release 元数据和语义验收边界；
- `v2_2.6.0/asset_manifest.jsonl`: 运行时资产清单；
- `v2_2.6.0/mask_patch/`: 708 张可恢复的 `U#_v2.png` 补丁。

`v2_1084/`、`v2/` 和 `v2_1k/` 仅作为历史基线或构造草稿保留，不是当前评测入口；不要覆盖它们，也不要把它们的结果混入 2.6.0。

正式图像资产在数据根 `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2/assets/`，仓库只发布新版 mask 补丁和清单，不复制全部源图。
