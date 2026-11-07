# GIDE-Bench 小子集评测方案

用户于 2026-11-07 确认；先记录协议，再实现评测。

- 范围：8 条固定请求，SITEdit 与 Qwen-Image-2.1。不是全量 benchmark 结论。
- 官方评分仓库：https://github.com/Zivenzhu/GIDE.git，当前核验 commit `afd593c9b7ae938610344efcdc302b3a785c5376`。
- 抽样 seed 20261107，按已确认计划分层，生成前保存固定清单。
- 源码基础：新分支 `eval-gide` 从已验证的两模型 pilot 通用代码 f0b954e 创建；不改变其他 worktree、IF-Bench 冻结包或现有结果。
- 方法固定：SITEdit aa5a414、Pass1 step2000、S2 adapter16000、raw TE、40步、γ2、seed42；Qwen-Image-2.1 原生40步、CFG1、seed42。
- 输入边界：两模型获得同一公开信息。评分 mask/GT/问题答案不能进入生成。只允许确定性几何转换，模型自己的原生定位流程保持不变。
- 评分：冻结官方函数、预处理、模型权重及聚合；涉及 API 时换为用户指定 GPT-5.4，原提示与评分定义保留，明确披露，不与其他 Judge 的论文数字直接混排。
- 异常：原始记录保留、失败不隐去，不自行把缺失分数补成零。
- 临时产物：`/tmp/ifbench/external_pilots_20261107/`。
- 已确认的小子集结果：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gide/pilot_20261107/`。
- 可视化：`/opt/tiger/tanyue/visualization_tmp/GIDE-Bench_20261107/`。

以下固定版本、公开字段映射和原生评分口径已在生成前完成核查；样例与生成配置不再按评分结果调整。

## 已冻结的公开区域映射

八条在 805 条发布请求中分层固定：polygon 2、xywh box 2、text 4，覆盖六种编辑组合。只读取 `edit_instructions` 为生成指令；`evaluation` 中显式目标名称与 `input_all.json` 中对象/描述均不进入编辑器。pixel 坐标按共享 1MP 几何进行连续仿射转换，框保持 xywh，四点多边形保留全部点，指令明确画布像素坐标系。

Qwen2.1 得到干净画布和转换后的原指令。SITEdit 只按原文已有的 `, and add/replace/remove` 分隔为两个子指令：公开 polygon 确定性栅格化后由原生 SAMTok codec 编码；box 转为原生 normalized_0_1000 locator；纯文字子指令为 none locator。一次联合 Pass1 处理所有需定位的单元，已知 mask token 保留；按训练格式一次联合 S2 编辑。没有 SAM、外部定位器、额外改写器，也不串行编辑。

Judge 原样使用官方 metrics.py 的两编辑 rubric，以及私有 evaluation 指令、原图和输出图；公开输入形式不进入 Judge。官方 calculate_score.py 分别平均两项 Prompt Compliance、Visual Naturalness，范围 1–5；API 从 GPT-5.1 改为用户指定 GPT-5.4，原提示不变。不加入自定义总分。

SOURCE.json 保存官方 Git commit 和源图/元数据 SHA256；官方发布未找到单独的数据许可，本分支不重分发图片。

## 本机复现

从官方 GitHub 获取上述固定 commit 的只读 checkout；只复制选中的 8 张源图与官方 JSON，不执行数据目录中的代码。

```bash
git clone https://github.com/Zivenzhu/GIDE.git /path/to/gide-upstream
git -C /path/to/gide-upstream checkout --detach afd593c9b7ae938610344efcdc302b3a785c5376
python -I scripts/gide_prepare.py --upstream /path/to/gide-upstream --dataset /mnt/bn/strategy-mllm-train/user/tanyue/datasets/GIDE-Bench --output /path/to/pilot/bundle
python scripts/run_external_pilot.py --config configs/external/gide.json --bundle /path/to/pilot/bundle --output /path/to/pilot/run --gpus 6 7 --case-ids 94 337 495 --attempt smoke01
python scripts/run_external_pilot.py --config configs/external/gide.json --bundle /path/to/pilot/bundle --output /path/to/pilot/run --gpus 6 7 --attempt remaining01
```

上述三条冒烟覆盖 polygon / box / text 三种输入；完整固定子集不会重采样已完成项。评分使用 `PYTHONPATH=src python -m samtok_benchmark.external_gide.score --help` 所列入口，密钥仅从 `--key-file /protected/path` 读取。评分和汇总都可在 CPU 上执行。

## 原生透明输出的记录口径

原始 `raw.png` 保留模型返回的 RGBA；冻结画布回源函数和这些官方 RGB 指标使用 `convert("RGB")`，不会把透明区域贴回源图，也不补背景。冒烟中 Qwen2.1 部分输出预测了大面积透明 alpha，RGB 图中显为紫色；这是原始输出的透明区域在 RGB 口径下的表现，不能误写成文件损坏或预处理生成了紫色背景。后续报告保留该限制，不按得分修改输出转换或重新生成。
