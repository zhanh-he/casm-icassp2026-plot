# CASM/DBN 校准规模实验的科学意义与论文使用决策

**日期：** 2026-09-05  
**性质：** 内部方法学审计与写作决策记录  
**适用对象：** Figure 5 CASM calibration-scale 图、对应 DBN 图，以及论文中关于 1F/2F/4F/7F、自动校准、参数稳定性和 4F operating point 的表述

## 结论先行

CASM 的 calibration-scale 图本身具有科学意义，但当前 CASM--DBN 对照还不能作为正文中的强比较证据。

这项实验可以准确回答：

> 当全局 decoder configuration 由不同数量和组成的 calibration folds 自动选出时，最终固定面板性能对 calibration set 有多敏感？

它不能直接回答：

- semi-Markov 是否天生比 DBN 稳定；
- CASM 是否随着数据增加而“学得更好”；
- DBN 是否比 CASM 更容易过拟合；
- 4F 是否是统计意义上的最优 calibration scale；
- CASM 是否完全不需要参数选择。

当前最重要的审计发现是：**CASM 与 DBN 的 calibration inventory、calibration sample size、selection objective 和 search procedure 并未真正匹配。**因此，两张图虽然都正确复现了各自协议下的结果，但目前观察到的方差差异不能归因于模型结构本身。

论文使用决策如下：

1. 当前两张完整的 \(2\times3\) 图保留在 GitHub 或 supplementary，标为 exploratory/descriptive calibration-sensitivity audit。
2. 在完成公平重跑以前，不把它们作为“CASM 比 DBN 更稳定”的正文核心证据。
3. 如果公平重跑后结论仍成立，并且“低校准负担”仍是论文的核心卖点，可在正文放一个压缩后的图或表；完整图继续放 supplementary。
4. 不使用 “data-scaling learning curve”“4F is optimal”“semi-Markov learns from more data” 等表述。

## 代码、数据与版本状态

Figure 5、DBN 对照图、数据和复现代码已经进入 GitHub `main`。绘图修正提交为 [`1a28a02`](https://github.com/zhanh-he/casm-icassp2026-plot/commit/1a28a02)，该提交已包含在当前主分支历史中。

主要文件：

- [Figure 5 绘图代码](../../self-run-figures/figures-20260904-1443/plot_mechanism_evidence.py)
- [DBN calibration-scale 实验代码](../../self-run-figures/figures-20260904-1443/run_dbn_calibration_scale.py)
- [完整复现说明](../../self-run-figures/figures-20260904-1443/README.md)
- [CASM fixed-panel 数据](../../self-run-figures/figures-20260904-1443/data/calibration_fixed_panel.csv)
- [DBN fixed-panel 数据](../../self-run-figures/figures-20260904-1443/data/dbn_calibration_fixed_panel.csv)
- [CASM Figure 5](../../gpt-figures/figures-20260904-1443/fig05_calibration_scale.png)
- [DBN Figure 5b](../../gpt-figures/figures-20260904-1443/fig05b_dbn_calibration_scale.png)

## 一、CASM 作为 semi-Markov 方法是否存在“拟合数据”的概念？

### 1. Semi-Markov 是结构，不是训练方式

“Semi-Markov”描述的是序列模型如何表示可变长度 segment 或显式 duration，并不自动规定模型参数是学习得到、人工设定还是通过验证集选择。

一般的 semi-Markov 模型当然可以学习。例如，semi-CRF 可以进行条件训练；HSMM 也可以通过 forward--backward 等算法估计或更新参数。参见：

- Sunita Sarawagi and William W. Cohen, [Semi-Markov Conditional Random Fields for Information Extraction](https://proceedings.nips.cc/paper_files/paper/2004/file/eb06b9db06012a7a4179b8f3cb5384d3-Paper.pdf), NeurIPS 2004.
- Shun-Zheng Yu, [Hidden Semi-Markov Models](https://www.sciencedirect.com/science/article/pii/S0004370209001416), Artificial Intelligence, 2010.

因此，“semi-Markov 方法不学习参数”作为一般陈述是错误的。准确的说法只能针对当前 CASM 实现。

### 2. 当前 CASM 没有训练 decoder weights，但存在数据依赖的 configuration selection

令 \(D_S\) 表示某个 calibration fold subset，\(\Theta\) 表示预先定义的 CASM configuration/search space，\(U\) 表示 selection utility。当前流程可以写为

\[
\hat{\theta}_{S}
=
\operatorname*{arg\,max}_{\theta\in\Theta}
U(D_S;\theta),
\]

随后在测试曲目 \(x\) 的 activation \(a_x\) 上进行结构化推断：

\[
\hat y_x
=
\operatorname*{arg\,max}_{y}
E(y;a_x,\hat{\theta}_{S}).
\]

这里必须区分两件事：

- 第一式是有标注 development data 驱动的 supervised calibration/model selection；
- 第二式是固定参数下的 semi-Markov dynamic-programming inference。

CASM 不通过梯度下降、最大似然或反向传播学习新的 decoder weights，也不会在测试曲目上更新 \(\hat\theta_S\)。但是，由于 configuration 是通过带标注 development metrics 选出的，因此不能说它“完全没有拟合数据”。

论文中最稳妥的术语是：

> validation-selected global decoder parameters

或

> one-off global calibration followed by parameter-frozen inference

不宜直接写成 `trained semi-Markov model`，也不宜写成 `parameter-free` 或 `tuning-free`。

### 3. CASM 真正的自适应发生在测试时的输入条件化推断

CASM 的重要性质不是“没有参数”，而是全局参数描述一套固定的响应规则。对每首新曲目，局部 period target \(\tau_x(t)\) 与 reliability/context quantity \(c_x(t)\) 从输入 activation 自动计算，继而调制 segment/duration potential 的中心、宽度或强度。

因此，CASM 的全局参数更接近：

> 决定 decoder 应当如何根据局部观测进行调整的 policy parameters

而不是：

> 为每首曲目人工指定的 BPM、IBI、tempo rigidity 或 meter setting

测试阶段不需要 ground-truth beat、IBI、BPM、meter annotation，也没有 per-track parameter update。这才是“自动挡”主张中可以守住的部分。

## 二、DBN 是否“拟合数据”？它与 CASM 的差异是什么？

当前 DBN calibration-scale 实验同样没有重新训练 neural frontend，也没有通过概率学习估计一套新的 DBN 参数。它从预先给定的网格中选择：

- `min_bpm`；
- `max_bpm`；
- `transition_lambda`。

测试时，DBN 使用固定的 tempo support、observation model 和 transition law，从 activation 中推断最优 tempo/phase/meter hidden-state path。Krebs、Böck 与 Widmer的 DBN 本身就是对 tempo 与 bar position 的联合隐状态推断：[An Efficient State-Space Model for Joint Tempo and Meter Tracking](https://archives.ismir.net/ismir2015/paper/000239.pdf)。`madmom` 文档也明确说明，较大的 `transition_lambda` 更偏好相邻拍之间保持恒定速度：[madmom beat-tracking documentation](https://madmom.readthedocs.io/en/v0.13.2/modules/features/beats.html)。

因此，不能写“DBN 完全不自适应”。DBN 的 hidden tempo/phase path 会随输入变化。

更准确的区别是：

| 层次 | CASM | 当前 DBN |
|---|---|---|
| Neural activations | 来自已经训练的 Beat This frontend | 使用相同 frontend |
| Decoder calibration | staged validation selection of global \(\theta\) | grid selection of global \(\phi\) |
| Test-time latent inference | dynamic programming over candidate events/segments | Viterbi-style inference over tempo/phase/meter states |
| Test-time adaptation | duration target/precision 等 potential 本身受局部 activation context 调制 | hidden state path 随输入变化，但 tempo support 与 transition law 全局固定 |
| Per-track labelled tuning | 无 | 无 |

因此不应写：

> CASM 会学习，DBN 不会学习。

更有力且准确的表述是：

> DBN adapts its latent metrical trajectory to the observations under a globally fixed state support and transition law. CASM additionally conditions its segment-duration potential on local activation-derived context, so its global parameters specify how the decoder should adapt rather than a single effective rigidity for every excerpt.

这一表述也与近期 beat-tracking 工作对固定 DBN tempo/meter constraint 的反思相衔接。例如 Beat This 将移除 DBN post-processing 的固定约束作为其设计动机之一：[Beat This! Accurate Beat Tracking without DBN Postprocessing](https://arxiv.org/abs/2407.21658)。

## 三、1F/2F/4F/7F 实验实际测量的对象

每一个点的含义是：

1. 选择一个 calibration fold subset \(S\)；
2. 按预先规定的 search/selection procedure 得到 \(\hat\theta_S\) 或 \(\hat\phi_S\)；
3. 冻结该 configuration；
4. 在同一个 SMC fold0 或 GTZAN final0 panel 上评分。

因此，图的科学对象是：

> configuration-selection sensitivity to calibration-set size and composition

它不是以下任何一种实验：

- neural-network training-data learning curve；
- semi-Markov parameter-estimation curve；
- training-seed variance；
- test-population confidence interval；
- “more data must monotonically improve performance”的验证。

即使 decoder 没有可训练 weights，超参数或 configuration selection 仍然会受到有限 validation sample 的影响。selection criterion 自身可能具有较大 variance，也可能发生 model-selection overfitting。参见 Gavin C. Cawley and Nicola L. C. Talbot, [On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation](https://jmlr.csail.mit.edu/papers/volume11/cawley10a/cawley10a.pdf), JMLR 2010。

所以，这项实验有科学意义，但应被称作 calibration sensitivity/stability analysis，而不是 data-scaling learning experiment。

## 四、固定且较小的 evaluation set 是否让实验失去意义？

不会完全失去意义，但结论必须是 conditional 的。

### 固定 evaluation panel 的优点

所有 configuration 都在相同曲目上评价，所以不同点之间的性能变化不是由“这一次抽到了更容易的测试集”造成的。在 decoder 和 metric 都是确定性的条件下，图中的变化来自 calibration subset 改变后选中了不同 configuration。

这对于诊断 selection-induced performance variation 是合理设计。

### SMC fold0 只有 27 首的限制

SMC fold0 的 \(N=27\) 意味着：

- 结果只能描述这些 configuration 在这个特定 fold0 上的表现；
- 无法据此估计整个 SMC population 的 calibration robustness；
- 换一个 outer test fold，configuration 的相对顺序和 spread 可能变化；
- 在 piece-wise macro mean 下，单首曲目的理论最大贡献约为 \(1/27\approx3.7\) percentage points，因此小于一个百分点的 CASM spread 很容易受到少量曲目的影响。

这不意味着同一 panel 上的 paired comparison 没有意义，而是意味着不能把 fold0-conditional result 提升成 population-level conclusion。

### GTZAN final0 的作用

GTZAN final0 有 993 首，而且没有进入 CASM/DBN configuration selection，因此它提供了更强的 external-transfer 观察。它仍然只是一个 corpus 和一个 frontend checkpoint，不能单独证明普遍的跨域稳定性。

## 五、组合重叠、boxplot 和“方差”的正确解释

对 folds 1--7，实验穷举：

- 7 个 1F subsets；
- 21 个 2F subsets；
- 35 个 4F subsets；
- 1 个 7F union。

这些不是 IID 随机重复。尤其是不同 4F subsets 共享大量 folds，因此点与点之间高度相关。

由于实验穷举了给定七个 folds 上的全部组合，可以把这些点当作一个**有限组合总体**，报告其 mean、range 和 population SD。这种描述不要求组合彼此独立。

但不能：

- 把 7/21/35 个点当作独立实验重复；
- 对其使用普通 IID standard error、t-test 或未经修正的 bootstrap CI；
- 把 across-combination spread 称作 unseen-test-data uncertainty；
- 对 7F 报告 variance，因为 7F 只有一个 configuration。

因此现有图脚注中 “distributions are descriptive” 是必要限定，正式 caption 还应进一步写明组合是 exhaustive and overlapping。

## 六、当前 CASM--DBN 对比存在的关键协议不匹配

这是本次审计最重要的发现。

### 1. Calibration data 规模与构成不匹配

CASM staged search 使用对应 Beat This OOF folds 中的**所有数据集**。根据 sealed selection results：

| Scale | CASM calibration pieces | 其中 SMC | 当前 DBN calibration pieces |
|---|---:|---:|---:|
| 1F | 562--575 | 27--28 | 27--28，SMC only |
| 2F | 1129--1148 | 54--55 | 54--55，SMC only |
| 4F | 2267--2287 | 108--109 | 108--109，SMC only |
| 7F | 3985 | 190 | 190，SMC only |

CASM 的来源可见：[CASM exhaustive-combination driver](../../self-run-figures/figure2-20260901-1200/data/full_raw_archive/code/run_casm_fixed_fold0_exhaustive_combinations.py#L471)。该代码在构造 selection inventory 时只按 fold 过滤，并没有按 `smc` 过滤；其结果中 7F development population 为 3985 首，其中 SMC 为 190 首。

DBN 脚本则明确在 calibration 时调用 SMC aggregate：[DBN calibration runner](../../self-run-figures/figures-20260904-1443/run_dbn_calibration_scale.py#L223)。

也就是说，当前 CASM 的 1F 已经使用大约 570 首、多 corpus 的 calibration data，而 DBN 的 1F 只有约 27 首 SMC。CASM 较小的 configuration variance 很可能部分来自更大的样本和更丰富的 corpus composition，而不一定来自 semi-Markov/context-aware structure。

### 2. Selection objective 不匹配

CASM 的 staged records 保存 overall beat/downbeat 六项指标、metric guards、`six_metric_wins` 和历史参数距离，并通过 sealed staged lexicographic procedure 前进。

当前 DBN selection 则为：

1. 最大化 SMC Beat F1；
2. 保留距离最佳 F1 不超过 0.0005 的 configuration；
3. 最大化 SMC CMLt；
4. 最大化 SMC AMLt；
5. 再偏好距离 default 更近的 configuration。

所以不能写“两者使用相同 selection rule”。它们只在 fold-subset labels、frontend 和 fixed evaluation panels 等部分相同。

### 3. Search procedure 与有效复杂度不匹配

CASM 使用 staged、带 guard 和历史 operating point 的结构化搜索；DBN 使用包含 52 个 configuration 的完整网格：

\[
\texttt{min\_bpm}\in\{30,55\},\quad
\texttt{max\_bpm}\in\{215,300\},
\]

以及 13 个 `transition_lambda` 值。

方法之间没有必要拥有相同名字或数量的参数，但 search budget、selection regularisation 和允许变化的高风险参数会直接影响 selection variance。因此，当前结果最多是两个**完整配置流程**之间的比较，而不是 semi-Markov 与 DBN 两个模型类别的定理式比较。

### 4. 当前报告中的“matched”表述必须纠正

[现有 mechanism report](../../self-run-figures/figures-20260904-1443/mechanism_evidence_report.md#L89) 将二者描述为使用相同 calibration subsets 和 selection metric。就数据内容与 objective 而言，这一表述不成立，投稿前必须重写。

## 七、DBN 大方差究竟来自哪里？

当前 DBN 图中的巨大 spread 不是随机噪声，而主要是由选中的 global tempo support 不同造成的。

在 64 个非 Direct selections 中，按 `min_bpm` 分组后：

| Selected `min_bpm` | 选择次数 | SMC fold0 F1 | SMC fold0 CMLt | SMC fold0 AMLt |
|---:|---:|---:|---:|---:|
| 30 | 20 | 62.04 | 60.08 | 72.00 |
| 55 | 44 | 58.32 | 44.30 | 70.29 |

4F 的 35 个 subsets 中，有 29 个选择了 `min_bpm=55`。这解释了 SMC CMLt 图中约 44% 与约 60% 的明显模式分离。

这个现象具有真实的科学意义：

> 当 global tempo support 在 calibration corpora 上被选出后，它可能在另一个困难 corpus 上形成硬支持失配，尤其会伤害 continuity metrics。

但是它不能证明：

> DBN 整体比 semi-Markov 更容易过拟合。

原因是当前 CASM configurations 始终将 `min_bpm` 固定在 30，而 DBN 被允许在 30 与 55 之间进行选择。当前实验允许 DBN 做出一个危险的全局支持选择，却没有让 CASM 的相应支持发生变化。

因此，当前 DBN 图更像一张 **tempo-support portability diagnostic**，而不是已经完成控制变量的 model-class stability comparison。

## 八、现有数值可以说明什么，不能说明什么？

在当前各自协议下，有限组合总体的 descriptive population SD 确实显示 CASM 更集中。例如：

- SMC fold0，1F，CASM 的 F1/CMLt/AMLt SD 约为 0.30/0.91/0.83 points；DBN 为 1.72/6.82/7.34。
- SMC fold0，4F，CASM 约为 0.19/0.45/0.30；DBN 为 1.62/6.47/5.85。
- GTZAN final0，4F，CASM 约为 0.01/0.06/0.05；DBN 为 0.39/0.82/1.15。

这些数字在复现与描述层面是真实的。正确结论是：

> Under their current, different calibration procedures and search spaces, the selected CASM configurations produce a much narrower distribution of fixed-panel scores than the selected DBN configurations.

当前不允许进一步写成：

> CASM is intrinsically less sensitive than DBN because it is semi-Markov.

要建立后一个结论，必须消除 calibration population、objective、tempo support 与 search policy 等混杂因素。

## 九、为什么“更多数据不一定更好”不是这张图的主要故事？

即使在标准机器学习中，有限样本下的 test score 也不需要随 calibration/training size 单调上升。这里尤其不能期待单调性，因为：

- 1F、2F、4F families 不是一组固定顺序的 nested samples；
- 增加 fold 同时改变了样本数量与音乐内容组成；
- selection 使用离散 configuration 和多指标规则，最优点可能跳变；
- calibration distribution 与固定 evaluation corpus 可能存在 domain shift；
- search space 可能具有多个接近的 validation optima；
- 7F 只有一个 union，不能与其他 family 比较方差。

因此，这张图不应宣传为“data 越多不一定越好”的普遍机器学习发现。这一结论过大，也并不新颖。

更合适的故事是：

> More calibration data can reduce dependence on which labelled folds are available, but it does not guarantee monotonic fixed-panel improvement under finite, heterogeneous and distribution-shifted calibration.

## 十、4F 是否最优？

当前数据不支持 4F 为 statistically optimal calibration scale。

CASM 的 7F configuration 在当前 SMC fold0 和 GTZAN final0 的三个 beat metrics 上均略高于 4F family mean。7F 的问题不是性能较差，而是它只有一个 configuration，因此不能估计 composition variance。

4F 还存在两个额外问题：

1. 4F 被 foreground 是在观察 calibration-sensitivity analysis 之后发生的，属于 post-hoc operating-point choice。
2. 具体选择 folds \(\{2,7,1,3\}\) 又增加了一层 researcher degree of freedom。

如果最终 operating point 仍有调整空间，7F 在方法学上更干净：

- 使用全部 development folds；
- 不需要事后挑一个 4F subset；
- 减少 configuration-selection 自由度；
- 当前记录中它也是更适合作为 pre-GTZAN reference 的 configuration。

如果继续保留 4F，只能写成：

> a post-hoc, computation-aware near-saturation operating point

或更保守的：

> an exploratory operating point selected to balance calibration cost and observed stability

不能写成：

> the optimal amount of calibration data

也不能因为 4F family 有 35 个点、boxplot 看起来稳定，就声称它优于 7F。

## 十一、使该实验足以进入正文的公平重跑方案

### 方案 A：General-purpose/global calibration

如果论文主张 CASM 是一个可跨 backbone、跨 corpus 使用的通用 post-processor，则 CASM 与 DBN 都应使用相同的 multi-corpus OOF folds 进行 calibration，并使用相同的 selection utility。

这回答：

> 在相同 heterogeneous development data 下，哪一种完整 decoder-selection policy 更容易形成可迁移的全局 default？

### 方案 B：Low-resource target-domain calibration

如果论文主张在 SMC 这类困难数据上减少 target-specific tuning burden，则 CASM 与 DBN 都应只使用相同的 SMC calibration tracks，并使用相同 beat-only selection utility。

这回答：

> 当 practitioner 只有少量目标域标注时，两种 decoder policy 对具体拿到哪些标注曲目有多敏感？

方案 A 与 B 不能混成同一项实验。论文应明确选择一个作为 primary question，另一个最多作为 supplementary analysis。

### 必须增加的 DBN controls

至少报告两种 DBN search space：

1. **Matched-support DBN：** 固定 30--300 BPM，只选择 `transition_lambda`。这用于隔离 transition rigidity 的敏感性。
2. **Operational DBN：** 允许 `min_bpm`、`max_bpm` 和 `transition_lambda` 一起选择。它用于展示实际部署中的 global-support calibration burden。

如果只有第二种，CASM--DBN 差异会被 `min_bpm` support mismatch 主导。

### 必须增加的 outer evaluation

不应永远固定 SMC fold0。推荐对八个 SMC folds 做 outer rotation：

1. 选择 outer test fold \(o\)；
2. 其余七 folds 构成 calibration universe；
3. 在其中枚举 1F/2F/4F/7F subsets；
4. 对每个 subset 执行完整 configuration-selection procedure；
5. 在 outer fold \(o\) 上评价；
6. 对八个 outer folds 重复。

这样才能判断当前 fold0 上的模式是否具有跨 outer-fold 稳定性。

### 推荐报告的 quantities

- 每个 outer fold、每个 calibration scale 的 fixed-panel score distribution；
- exhaustive-subset population SD 与 range；
- 相对于同一 outer split 之 7F configuration 的 selection-induced difference：

\[
\Delta_{S,o}
=
U_o(\hat\theta_S)-U_o(\hat\theta_{7F,o});
\]

- selected-configuration entropy 或 unique-configuration count；
- 落入 \(\epsilon\)-equivalent performance region 的 configuration proportion；
- 对 tracks/outer folds 进行 paired 或 hierarchical resampling，而不是对高度重叠的 calibration subsets 进行普通 IID bootstrap。

7F 只能作为 full-calibration reference，不应被称为 test oracle。真正的 oracle-in-search-space 如果使用 test labels，只能作为明确标记的分析上界。

### 预注册与 test hygiene

在重跑前冻结：

- calibration inventory；
- candidate/search spaces；
- selection utility 与 tie-breaks；
- evaluation panels；
- primary metric；
- planned figure/caption；
- main claim 与 claim limits。

已经看过的 GTZAN final1/final0 结果不能因为重新生成 lock 文件就重新变成完全 untouched test evidence。若最终 operating point 或故事曾受到这些结果影响，应明确称为 exploratory，或使用新的 external corpus 完成确认。

## 十二、建议的论文定位与措辞

### 推荐 figure title

> Sensitivity of validation-selected decoder configurations to calibration-set size and composition

不推荐：

> Data-scaling performance of CASM

### 当前探索性 caption 应包含的限定

> Each point corresponds to a decoder configuration selected from one exhaustive subset of the available calibration folds and evaluated on the same fixed panel. Subsets overlap; the distributions therefore describe the finite set of selection outcomes and are not confidence intervals over unseen music.

### 公平重跑后才可以使用的比较性主张

> Under a fixed and preregistered calibration protocol, CASM's observation-conditioned decoder policy was less sensitive to which labelled calibration folds were available than the matched-support DBN selection procedure.

这句话必须保留：

- `under a fixed and preregistered protocol`；
- `matched-support`；
- `selection procedure`；
- `which labelled calibration folds were available`。

不应简化为：

> Semi-Markov is more robust than DBN.

### CASM 自动化主张的推荐核心

CASM 最有力的主张不应是“没有参数”，而应是：

> CASM replaces per-track manual timing constraints with a single globally calibrated, parameter-frozen policy whose segment-duration preference is conditioned on local activation evidence at inference time.

对应中文含义是：CASM 不是消除全部参数，而是把需要人工针对每首曲目决定的 tempo/rigidity 选择，转换成一次性的全局校准和测试时由输入证据驱动的局部响应。

## 十三、Figure 5 在整篇论文证据链中的位置

这项 calibration-scale 实验最多应承担辅助证据，而不能替 CASM 的全部新颖性兜底。

更强的核心证据顺序应为：

1. **Mechanism ablation：** 将 input-conditioned local precision/target 替换成 fixed counterpart 后，CMLt/AMLt 明确下降。这直接证明“adaptive”不是文字包装。
2. **Frozen cross-backbone/cross-corpus transfer：** 同一套全局 configuration 不经 target-specific retuning 即可迁移。
3. **Matched-support DBN comparison：** 在相同 tempo support 下隔离 observation-conditioned duration potential 与 fixed transition law 的差异。
4. **Safeguard/risk analysis：** 展示何时 CASM 应当 relax、fallback 或拒绝强制周期化。
5. **Calibration sensitivity：** 最后用于说明选定 policy 对 development sample composition 的依赖程度。

因此，Figure 5 最合适的角色是：

> supporting evidence for low calibration burden

而不是：

> the main proof that CASM is novel or superior

## 十四、现稿中需要同步修正的地方

当前草稿仍有与本审计直接冲突的内容：

1. [Frozen operating point and scale analysis](../0904_1335_overleaf/casm_v2.tex#L317) 仍写 GTZAN `final1`，而当前 Figure 5 已改为 Beat This GTZAN `final0`。
2. [Figure 5 placeholder caption](../0904_1335_overleaf/casm_v2.tex#L590) 仍写成 “train Semi-Markov/data scaling”，这在概念上不准确。
3. 现有 mechanism report 中“CASM 与 DBN 使用相同 calibration population/selection rule”的表述需要改正。
4. 如果正文继续使用 Frozen-4F，必须披露它是 post-hoc/exploratory operating point，不能宣称 4F 最优。

## 最终判断

这张图提出了一个值得研究的问题，但当前实验还没有公平回答 CASM 与 DBN 谁更稳定。

CASM 图单独来看，是一项有效的 configuration-selection sensitivity stress test；固定 evaluation panel 使它可以准确描述在该 panel 上由 calibration subset 引起的性能变化。SMC fold0 的小样本限制了 population inference，GTZAN final0 则提供了更强但仍有限的 external-transfer evidence。

当前 DBN 图忠实地揭示了 global tempo-support selection 的跨 corpus 风险，但由于 calibration data、objective、search procedure 和 support variation 与 CASM 不匹配，它还不能证明 semi-Markov 的结构性优势。

论文最应坚持的核心是：

> CASM is not parameter-free and is not a decoder trained by gradient descent. It is a globally calibrated, parameter-frozen structured decoder whose duration potential is conditioned on local activation-derived context. Its practical promise is reduced per-track manual intervention and improved portability, not the elimination of model selection itself.

在公平、预注册、outer-fold matched 的重跑完成之前，Figure 5 应保持为探索性辅助材料；完成之后，它才有资格支持“低校准负担与更低 selection sensitivity”的正文结论。
