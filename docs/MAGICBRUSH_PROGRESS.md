# MagicBrush 进度记录

时间均为 UTC；协议见 [MAGICBRUSH_EVALUATION.md](MAGICBRUSH_EVALUATION.md)。

## 2026-11-05

- 16:24 开始只读核对。系统时间早于 GPU 许可时段；GPU 4–7 约占用 46–50 GB，未启动任何 GPU 进程。
- 已 fetch `v2branch`、`eval-refedit`、`eval-mira`，主 worktree checkout 未改；从 `origin/v2branch` 读取配置／用法。
- 已阅读 RefEdit/MIRA 的 AGENTS、评测与进度文档、公开数据与八方法 adapter、worker、ARNOLD 模板；核对 SITEdit aa5a414 原始主行配置。
- 官方调研确认：test 已公开，535 会话／1,053 轮；HF gated=false；固定 GitHub d2d7f84 与 HF 6c25456；CC BY 4.0。未使用第三方镜像或付费接口。
- 创建独立 worktree `/opt/tiger/tanyue/if-bench-magicbrush` 和 `eval-magicbrush`，基于 `origin/eval-refedit` c9f9447；解除继承的远程分支追踪，防止误推 RefEdit。
- 在实现前写定方案：八方法，两种 mask 输入轨道，独立全轮／连续最终轮；mask-provided 论文区域指标与现行 scorer 整图指标的差异显式披露。
- 17:22 数据下载与解码完成：535 会话／1,053 轮；一／二／三轮会话数 216／120／199。六个 parquet 均通过官方 SHA256；指令与官方 metadata 一致，连续轮次的 GT/source RGB 像素一致。`SOURCE.json` SHA256：`7290246236a8b5cbae16093f65c7ce6f5e618e5db25174144f09109529ee4dd9`。
- 所有 1,053 个 mask 均为 RGBA、含透明和不透明区域；统一 alpha<128 为编辑区。首轮 533 张 500px、2 张 1024px；固定公开 1024px 网格与 IF-Bench canvas，避免连续编辑被恢复到 500px。三条官方空 local description 原样保留并披露。
- 官方 CLIP ViT-B/32 与 DINO ViT-S/16 权重已下载校验；CPU 相同图像自检得到 L1=L2=0、CLIP-I=DINO=1。使用安全权重加载和已安装 Transformers FP32 实现，与旧 CUDA/FP16 的精度差异列入方案。
- 新模块已具备公开输入、两轨道八方法适配、多轮依赖、独立生成／评分记录、分会话 bootstrap、报告、拼图、单机 ARNOLD staging。18 项 CPU 契约测试通过；包含禁止 GPU 0–3、19:00 时间门禁、占用门禁、无 GT 回退、mask 信息边界、完整请求数和冻结模块不变。
- 正在构造共享输入并执行训练指纹审计。尚未开始 GPU 冒烟或正式实验。
- 重合审计已比较 1,588 个去重后的源／GT 图像，对照 646,908 个训练图像指纹与 8,337 条 gRES 指纹。COCO id 命中 31 会话，其中 17 会话可追溯到实际 S2／Pass1 微调。逐一查看 31 对图像，确认同一 COCO 照片的裁剪关系；保守排除 31 会话，所有方法共用 504 会话／981 独立轮次子集。
- 额外感知近邻覆盖 20 会话，已查看全部候选缩略图，未确认新增重合；两条旧路径不可访问，改从既有 gRES parquet 读取 SHA 完全相同的图像字节核查。保存 `overlap/VISUAL_REVIEW.json` 与对比图。上述目检为 Codex 辅助核查，不冒充独立人工审计；任意裁剪、基础预训练和未记录数据来源不在穷尽性保证内。

- 18:14 共享包构造完成：2,106 份公开请求，bundle digest `545b6b9af9c7ccbe0980d62cc1fd8daaa7d4297e46a9652d0a11ecb947530faa`。固定冒烟为 `323789-1` 无 mask、`508582-1` 有 mask、`323789-2` 连续无 mask。
- 18:31 评分器补齐原始 DINO 的 LayerNorm epsilon=1e-6；198 个参数张量与原始官方 checkpoint 完全相同，两张真实图的独立 CPU 前向特征逐位一致，证据 `METRIC_PARITY.json`。未执行远程模型代码。
- CPU 集成测试覆盖三个请求的实际 worker 调度、连续输入依赖及完成结果复用；模型替身仅在测试中使用，不进入数据、冒烟或正式输出。

- 18:33 全量包 10,531 个公开／评分资产通过 NAS 路径与 SHA 核验，见 `PREPARE_VERIFICATION.json`。
- 为连续轮次在新机器上重绘标记，固定 DejaVuSans 字体字节并附许可，放入共享包 assets；三个实际标记图重新绘制后与已有输入逐字节一致。

## 当前待办

1. 19:00 后确认 GPU 4–7 空闲状态，执行每方法 3 个固定请求的端到端 smoke。
2. 用本次实测耗时核算 GPU 小时；遵守本机 8 h 上限，必要时交付入口，正式状态如实记录。
3. 检查实际输入／输出图，完成中文报告、提交与单机 ARNOLD READY 发布。
