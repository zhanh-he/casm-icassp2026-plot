# Beat Tracking 论文与中文翻译索引

本目录收录 8 篇论文的原文 PDF，以及每篇论文以下四部分的中文翻译：

- Abstract（摘要）
- Introduction（引言）
- Related Work / Related Works（相关工作）
- Conclusion / Conclusions（结论）

翻译文件使用 Markdown，按原文段落分段，引用编号保留不变。对于原文没有独立“Related Work”或“Conclusion”标题的论文，译稿中会明确注明原文章节对应关系，不会把补写的总结冒充原文翻译。

## 文件对照

| # | 论文 | PDF | 中文译稿 | 年份 |
|---|---|---|---|---:|
| 01 | Beat This! Accurate Beat Tracking Without DBN Postprocessing | `01_Beat_This_Accurate_Beat_Tracking_Without_DBN_Postprocessing.pdf` | `01_Beat_This_中文翻译.md` | 2024 |
| 02 | BeatFM: Improving Beat Tracking with Pre-trained Music Foundation Model | `02_BeatFM_Improving_Beat_Tracking_with_Pretrained_Music_Foundation_Model.pdf` | `02_BeatFM_中文翻译.md` | 2025 |
| 03 | HingeNet: A Harmonic-Aware Fine-Tuning Approach for Beat Tracking | `03_HingeNet_Harmonic_Aware_Fine_Tuning_for_Beat_Tracking.pdf` | `03_HingeNet_中文翻译.md` | 2025 |
| 04 | The SMC Blind Spot: A Failure Mode Analysis of State-of-the-Art Beat Tracking | `04_The_SMC_Blind_Spot.pdf` | `04_SMC_Blind_Spot_中文翻译.md` | 2026 |
| 05 | Masked Diffusion Enables Coherent Beat Tracking | `05_Masked_Diffusion_Enables_Coherent_Beat_Tracking.pdf` | `05_Masked_Diffusion_中文翻译.md` | 2026 |
| 06 | Local Periodicity-Based Beat Tracking for Expressive Classical Piano Music | `06_Local_Periodicity_Based_Beat_Tracking_PLPDP.pdf` | `06_PLPDP_中文翻译.md` | 2023 |
| 07 | BeatMamba: Bidirectional Selective State-Space Modeling for Efficient Beat Tracking | `07_BeatMamba_Bidirectional_Selective_State_Space_Modeling_for_Efficient_Beat_Tracking.pdf` | `07_BeatMamba_中文翻译.md` | 2026 |
| 08 | What Makes Beat Tracking Difficult? A Case Study on Chopin Mazurkas | `08_What_Makes_Beat_Tracking_Difficult_Chopin_Mazurkas.pdf` | `08_Chopin_Mazurkas_中文翻译.md` | 2010 |

## 两个标题说明

1. 用户列出的 “Local periodicity and dynamics based post-processing for beat tracking” 对应正式论文 **Local Periodicity-Based Beat Tracking for Expressive Classical Piano Music**。其方法名为 PLPDP，即 predominant local pulse-based dynamic programming tracking。

2. “What makes beat tracking difficult” 的正式副标题是 **A Case Study on Chopin Mazurkas**。

## PLPDP 的后续工作线索

这里有两项容易被统称为“续作”的工作，性质并不相同：

1. **What Can Go Wrong When Conducting Beat Tracking Experiments**（Chiu & Müller，ISMIR 2023 Late-Breaking Demo）是对 PLPDP 实验流程的技术复查。作者发现 madmom 与 ASAP 中不一致的音频格式、以及部分不准确标注会显著影响结果；修正后，PLPDP 的核心结论不变。它更像“实验更正与复盘”。

2. **dPLP: A Differentiable Version of Predominant Local Pulse Estimation**（Chiu、Strahl、Müller，ISMIR 2025）把传统 PLP 选择局部最优周期核时的 `max` 操作替换为基于 softmax 的加权，使 PLP 可作为中间层或损失函数进入端到端深度学习。它是方法层面更直接的后续发展。

## 建议阅读顺序

如果目标是写 CASM / beat post-processing 论文，可按以下顺序阅读：

1. `08`：先理解表现性音乐为何会让跟踪器失败。
2. `06`：理解全局速度假设的局限，以及 PLPDP 如何引入局部周期性。
3. `01`：理解为什么可以移除 DBN，以及无 DBN 系统的设计取舍。
4. `04`：从 SMC 的逐轨失效分析理解“激活函数上限”和“速度先验上限”。
5. `07`：看固定节拍间隔正则化如何进入训练目标，以及它在复杂音乐上的风险。
6. `05`：看多解问题与迭代生成如何减少不连贯输出。
7. `02`、`03`：最后补足基础模型表征与参数高效微调方向。

## 使用说明

- 译文适合做论文写作前的精读与结构参考；正式引用仍应引用英文原文。
- F1、CMLt、AMLt、BPM、DBN、HMM、TCN、SSM 等缩写保留原文形式。
- 同一术语尽量在全部译稿中保持一致；每篇文件开头列有该篇的术语约定。
