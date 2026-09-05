# Figure 5 校准规模、调参敏感性与泛化能力：文献审读与论文建议

结论先说：这种实验在 ML 论文里是成立的，也有先例；但你这张图不应叫 “data scaling”，也不适合以当前形式放进 ICASSP 主文。它真正测的是 development-set composition 对超参数选择结果的敏感性，不是训练数据 scaling，也不能单独证明泛化能力。

更直接一点：CASM-only 的 Fig. 5 建议放 supplementary。若主文一定要保留，应改成 CASM–DBN 的 matched selection-stability 对照，并压缩到最核心指标。

## 这类图是不是学术惯例？

是，但有三种不同问题，不能混称：

1. Learning curve
   改变训练样本量、重新学习模型权重，观察独立测试性能。这才通常叫 data scaling / learning curve。[Perlich et al.](https://jmlr.org/papers/volume4/perlich03a/perlich03a.pdf) 明确定义为训练集大小与泛化性能的关系。

2. Hyperparameter sensitivity
   改变某个超参数，观察性能曲线、热图或局部稳定区。

3. Model-selection stability
   改变 validation/development set 的大小或组成，重新选超参数，再在固定测试集上看结果分布。你的图属于这一类。

而且有很接近的文献：

- [Cawley & Talbot, JMLR 2010](https://www.jmlr.org/papers/volume11/cawley10a/cawley10a.pdf) 的 Fig. 5 展示六个不同 validation-set realizations 下超参数最优点如何移动；核心结论正是有限验证集会让 model selection 本身过拟合。
- [Wainer & Cawley, JMLR 2017](https://jmlr.org/papers/v18/16-174.html) 系统比较不同 folds、holdout 与重复采样方式对超参数选择及最终泛化的影响。
- [Bouthillier et al., 2021](https://arxiv.org/abs/2103.03098) 直接量化 data sampling、初始化和 HPO 对 benchmark variance 的贡献。
- 在 domain shift 场景，[Ericsson et al., 2023](https://proceedings.mlr.press/v224/ericsson23a.html) 特别警告用 target-test labels 做 HPO 会造成过度乐观的结论。

所以不会因为做这个分析显得“异类”。会显得不专业的是：把它叫 data scaling，或者用它证明“4F 最优”“more data improves learning”“generalizes well”。

## 手调参数到底算不算 data-driven？

“手调”和“data-driven”不是二选一。

| 层次 | CASM 中是什么 | 正确称呼 |
|---|---|---|
| 结构、公式、候选图、安全机制 | 人设计 | hand-designed inductive bias |
| 用 SMC 标注比较配置并挑 scalars | 结果由数据决定，即使人查看结果后选择 | validation-driven hyperparameter selection |
| 每首曲子的 \(\tau,c,\sigma,w\) | 从未标注 activation 自动计算 | input-conditioned inference |
| 测试时重新看标签改参数 | 不应发生 | target/test-set tuning |

因此最诚实、也最有力量的表述不是 parameter-free，而是：

> CASM is not parameter-free. Its global hyperparameters are selected on development data and then frozen; the effective period target and duration precision are inferred from each activation sequence without target labels or test-time parameter updates.

“data-driven”可以用于第二、第三层，但不要写成“所有参数由数据学得”。CASM 不是 end-to-end learned decoder。

这也是 beat-tracking 文献的正常做法：例如 EUSIPCO 的 TCN 工作直接复用 published DBN defaults，并以严格 train/validation/test folds 和额外 GTZAN 测试评估 transfer；[论文原文](https://www.eurasip.org/Proceedings/Eusipco/eusipco2019/Proceedings/papers/1570533824.pdf)。[Beat This](https://arxiv.org/abs/2407.21658) 则把组件选择/消融放在 validation split、用多 seeds 报告，再把 GTZAN 当外部测试。重点始终是参数何时、在哪些标签上被选择，而不是参数是否由 gradient 学出来。

## 你这张图实际能说什么？

你现有数据最强的发现不是“4 folds 足够”，而是：

> 在相同 SMC development-fold subsets 和固定评价 panels 下，CASM 所选 decoder 的最终性能明显比 DBN 对 development-set composition 更不敏感。

你自己的匹配实验很强：

- SMC fold 0，4F 选择的标准差：
  - CASM：F1/CMLt/AMLt = 0.19/0.45/0.30 个百分点
  - DBN：1.62/6.47/5.85 个百分点
- GTZAN final0，4F：
  - CASM：0.01/0.06/0.05
  - DBN：0.39/0.82/1.15

这些结果和 protocol 在 [mechanism_evidence_report.md](../../self-run-figures/figures-20260904-1443/mechanism_evidence_report.md#figure-5-calibration-fold-scale) 中已经总结，完整性检查也通过了 [qa_report.md](../../self-run-figures/figures-20260904-1443/qa/qa_report.md)。

但必须加限定：

- 只能说 “under the stated search spaces”；CASM 与 DBN 暴露的参数和搜索范围不同。
- 这些 subset 高度重叠，不是独立随机样本；boxplot 是 exhaustive descriptive sensitivity，不是置信区间。
- 7F 只有一个配置，完全不能表示 spread，也不能证明 7F 最稳定或最优。
- 单个 SMC fold 0 只有 27 tracks，可能本身是一个特殊 fold。
- GTZAN final0 是一个 backbone seed、一个外部数据集；它是 cross-dataset evidence，不是广义 domain generalization 证明。

## 为什么我不建议当前 Fig. 5 进主文

首先，它单独只显示 CASM。没有 DBN twin 时，读者看到的只是“多一点 development data，结果稍微更稳定”，这个结论既不新，也没有直接支撑 CASM 相对 DBN 的贡献。

其次，ICASSP 主文更应该优先放：

- 机制图；
- 固定 precision / strength-only / width-only 等关键消融；
- CASM 与 DBN/Direct 的 F1–continuity operating point；
- safeguard 对 severe regression risk 的作用。

这些证据更直接回答“CASM 为什么有效”。你自己的内部分析其实也已经得出同样排序：[推荐把 Fig. 5 放 supplement](../../self-run-figures/figures-20260904-1443/mechanism_evidence_report.md#recommended-paper-use)。

还有几个必须马上修正的 manuscript/data 不一致：

- 文章写的是 GTZAN `final1`，当前图和数据是 `final0`：[casm_v2.tex](../0904_1335_overleaf/casm_v2.tex#L317)。
- 正文说 “all nine panels”，当前图只有六个 panels，也没有 downbeat：[casm_v2.tex](../0904_1335_overleaf/casm_v2.tex#L318)。
- 正文的“哪些指标在 2F/7F 达峰”与当前 final0 CSV 不一致。现在 beat F1/CMLt/AMLt 基本到 7F 继续上升，downbeat AMLt 在 4F 略高于 7F：[calibration_summary_final0.csv](../../self-run-figures/figures-20260904-1443/data/final0_experiment_provenance/calibration_summary_final0.csv#L20)。
- 当前 LaTeX caption 仍是 placeholder。
- 版面有大量右侧空白；六 panels 缩成单栏后文字会太小。
- 窄 y-axis 会放大 GTZAN 上极小差异。更适合画相对 Direct 的 percentage-point delta，并明确 focused scales。

比图更危险的是：正文明确写了 4F 是看完 sensitivity/GTZAN 后才 foreground 的。那它就不能再作为无偏、clean external-test operating point。图可以是 exploratory diagnosis，但不能替 4F 洗成预先选择的最优模型。

## 如果保留，应该怎样改

标题建议：

> Sensitivity of decoder selection to development-set size and composition

不要用 data scaling；“calibration”在 ML 中还容易被误解为 probability calibration。

主文版本最好只留下两个 CMLt panels：

- held-out SMC fold；
- external GTZAN；
- CASM 与 DBN 放在同一图中；
- y 轴改成相对 Direct 的百分点变化；
- 1F/2F/4F 显示 distributions；
- 7F 用单独星号，并注明 singleton；
- 完整 F1/CMLt/AMLt 六面板放 supplementary。

可用的 caption：

> **Sensitivity of decoder selection to development-set size and composition.** For every 1-, 2-, and 4-fold subset of SMC development folds 1–7, global decoder hyperparameters are selected using SMC only, frozen, and evaluated on SMC fold 0 and GTZAN-final0. Points denote subset-specific selections and boxes summarize 7, 21, and 35 overlapping subsets. The 7-fold marker is a single all-development-set selection and does not estimate variability. Dashed lines indicate Direct. Results are descriptive and do not identify an optimal development-set size.

正文只应声称：

> Under the prespecified search spaces and matched subset protocol, CASM selection is less sensitive than DBN selection to which labelled development folds are available.

不要声称 4F 最优、CASM 不需要调参，或这张图证明了普遍泛化。

## 更好的下一轮实验

优先级最高的是：

1. 做真正的 nested outer-fold experiment
   轮流把 SMC 的每个 fold 当 outer test fold；只用剩余 folds 选择配置。这样不会把全部结论压在 fold 0 的 27 首歌上。

2. 把 generalization 与 tuning sensitivity 分开
   Generalization：在 source datasets 上选参数，target dataset 完全不参与；然后 leave-one-dataset-out 轮换。
   Sensitivity：只在 development data 上画参数或 subset 扰动，不用 test performance 挑最终配置。

3. 报告 deployment contract，而不只是最好分数
   比较：
   - published DBN default；
   - source-development-tuned global DBN；
   - frozen global CASM；
   - target-tuned/per-track DBN oracle，仅作 diagnostic upper bound。

4. 主文优先使用更直接的 robustness 指标
   例如“有多少 tracks 回退超过 5 个百分点”、10th-percentile gain、paired bootstrap。你的 Fig. 6 比 Fig. 5 更直接地说明 safeguards 和部署风险。

最终建议就是：保留这项实验，因为它是有学术价值的 model-selection stability study；把完整 Fig. 5/5b 放 supplementary。主文若要用，只用压缩的 CASM-vs-DBN matched comparison。更重要的是，不要用 post-hoc 4F 承担 clean generalization claim；改用预先锁定的配置、nested protocol，或一个完全未参与选择的新外部测试集。
