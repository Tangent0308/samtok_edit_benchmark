# v1：机器回收后的恢复与完整性检查

恢复入口只依赖 NAS 和版本化代码。当前机器的 `/opt/tiger/tanyue/`、旧 `/tmp` 实验目录、HF 登录态或 Lark CLI 配置不是获取 v1 数据和已有结果的前提。

## 1. 三个持久化入口

| 内容 | NAS 位置 |
|---|---|
| 正式 450、后续 433、完整 883 审核器与 ZIP、历史区域 | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v1/` |
| 两模型全量结果、扩充结果、所有评分迭代、原生图与生成记录 | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/benchmark_v1/` |
| 代码 bundle/源码快照、环境清单、模型配置及 NAS 权重链接、构建历史 | 上述实验根的 `recovery/` |

远程仓库使用 `Tangent0308/samtok_edit_benchmark` 的 `v1branch`。NAS 的 `recovery/code/benchmark.bundle` 提供无需 GitHub 网络的相同分支恢复入口；`editor.bundle` 与 `editor_source/` 保存实际编辑管线所需的 SAMTokEdit/DiffSynth 代码。完整目录定义见 [STORAGE.md](STORAGE.md)。

## 2. 在新机器恢复

先挂载 NAS。以下工作目录可按需选择，不需要原机器的目录：

```bash
NAS_ROOT=/mnt/bn/strategy-mllm-train/user/tanyue
RECOVERY_ROOT="$NAS_ROOT/experiments/SAMTokEdit/benchmark_v1/recovery"
git clone --branch v1branch "$RECOVERY_ROOT/code/benchmark.bundle" ./samtok_edit_benchmark
cd samtok_edit_benchmark

# 只使用标准库：检查 NAS 文件、哈希、任务身份及历史引用的实际落点
python -I scripts/verify_v1_recovery.py --nas-root "$NAS_ROOT" \
  --output ./recovery_check.json
```

默认校验所有数据、结果、代码和配置的 SHA256，并检查模型分片存在及链接落在 NAS。`--metadata-only` 只检查大小、路径闭合和任务/结果身份，用于快速恢复演练；`--with-model-weights` 还会重新流式核验全部模型分片。结果必须为 `status=passed`，任何缺文件、越出 NAS 的依赖、输入/输出身份不符或哈希变化均报错。

NAS 若以其他路径挂载，用 `--nas-root` 指定**相同用户目录结构的新根**。工具会将历史 NAS 绝对路径和旧本机路径映射到新根；模型的权重链接使用相对路径。

查看现有结果不需要 GPU、编辑模型环境、HF token 或原临时目录：

```bash
python -m http.server 8765 --bind 127.0.0.1 \
  --directory "$NAS_ROOT/datasets/samtok_edit_benchmark_v1/reviews/qwen21_883_20261009"
```

打开 `http://127.0.0.1:8765/`，或将 NAS 上 `reviews/packages/` 的完整 ZIP 下载解压后打开 HTML。

安装正式 CLI 后可继续校验/使用冻结任务：

```bash
python -m pip install -e .
samtok-benchmark validate \
  --dataset-root "$NAS_ROOT/datasets/samtok_edit_benchmark_v1"
```

NAS 上的 `recovery/index.json` 指向完整文件清单 `manifest.jsonl` 及其 SHA256；恢复审计报告放在 `recovery/verification/`。原 450 正式 manifest 的身份仍为 `16e3c8418d8ef179d0501f349a175409a43435af469829ae3689e36c1ba22937`。

## 3. 已保存的补充材料

此前的大规模归档之外，以下内容也保存在 NAS：

- 两模型 450 条完整查看器，以及旧正式数据准入工具的完整快照。
- 双语翻译结果、翻译审计、人工可读修订依据及所有审核包构建脚本。
- 三轮指令修订、原混合任务区域选择、300 条源图复核拼图及相关开发验证。
- 仓库整理脚本、可视化图生成脚本、v1 飞书同步内容快照和上传交付记录。
- 原数据源盘点 Markdown、项目 proposal，以及修改前的分支/审阅包备份。正文在私有 NAS，不额外提交到 Git。

这些位于 `recovery/provenance/`；每个复制目录保留原文件字节、逐文件 SHA256 和来源。开发阶段的合成输出、模拟浏览器决定和测试报告属于验证证据，不作为编辑模型成绩或真实用户审核。

## 4. 模型与环境

`recovery/models/{qwen21,qwen2511,judge}/` 保存本轮实际配置、tokenizer/processor 文件和权重链接。35 个权重分片已与原实验记录的 SHA256 一一核对，实际字节位于同一 NAS 用户目录下的 `models/pretrained_models/`；链接目标不在 `/opt` 或 `/tmp`。核验记录为 `recovery/models/verification.json`。

重新推理时可将上述 checkpoint 目录作为模型路径。编辑与评分代码的 Git bundle、源码快照及 Python 依赖版本清单在 `recovery/code/`、`recovery/environments/`。历史冻结记录的路径字符串保持原样；实际访问用 `path_map.json`、`resolved_outputs.jsonl` 和 NAS checkpoint 目录。新推理必须重新准备输入，不能改路径后复用原 digest。

重建环境使用相应版本依赖与新环境；原机器的虚拟环境、Python 解释器软链接、下载缓存及编译缓存无需恢复。已生成的 1,717 条输出和所有评分响应仍可直接查看，不依赖模型重新出图。

## 5. 人工审核记录的边界

当前服务器未收到用户最终人工审核导出，正式 450 和建议困难 504 的状态未被自动修改。原服务器已有的审核文件、初始 AI 结论和所有指令版本已保存；查看器浏览器里未导出的修改不会出现在服务器文件中。

后续审核请导出完整 JSON 备份，并保存到 NAS 的 `reviews/user_exports/`。移动浏览器/页面后导入该备份，保留指令修改与最终决定。不得用测试 backup 或默认保留建议冒充人工审核完成。
