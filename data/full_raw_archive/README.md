---
title: CASM fixed-fold0 exhaustive raw artifact archive
type: raw-artifact-index
status: completed
created: 2026-09-02
updated: 2026-09-02
tags:
  - project/beat-mscnn
  - casm
  - provenance
  - raw-artifacts
---

# CASM fixed-fold0 exhaustive raw artifact archive

这是一份 vault 内的只读回收副本，对应 folds 1–7 全部 `1F/2F/4F/7F = 7/21/35/1`
combinations、固定 SMC fold0 `N=27` 与 GTZAN final1 `N=993`。

优先入口：

- 正式解释：[[2026-09-02_casm_fixed_fold0_exhaustive_combination_scaling_final_report]]；
- 全部 64 组未舍入小分数：[[2026-09-02_casm_fixed_fold0_exhaustive_combination_score_ledger]]；
- `formal_key_results/`：65-row compact results、64-row selection、family summary 与 locks；
- `independent_analysis/`：独立 45-cell 重算、趋势解释与 Markdown table receipts；
- `figure/`：canonical 130-row plotting ledger、PNG/SVG、builder 与 figure manifest；
- `qa_staging/bundle/`：lab5090 970-file QA bundle（968 manifest records）；
- `qa_staging/qa/`：Gadi job `178019643.gadi-pbs` 的 PASS、逐曲重聚合与 checksum receipts；
- `qa_staging/gadi_logs/`：PBS log；`qa_staging/receipts/`：transfer/job receipts。

关键校验值：

- bundle manifest SHA-256：
  `0b76fe89e26f1c76c3c49ed553cd08370ee64fc00781a52f14b1022f38c9e8c1`；
- Gadi QA result SHA-256：
  `b67713641cfa49baf2b78c5c572e87713d61eb5e717822d18d78de9631d0f489`；
- Gadi checksum receipt SHA-256：
  `916ea5564acdf12dd78471ffa0e8d5a31debab7624bc7d3d347312e3d620ee5e`；
- fixed-panel 65-row result SHA-256：
  `2a710ea97794ecbee79ab0b7363f37debfd76fe85a2a5bd82fb6a7e2818345f6`；
- canonical plotting ledger SHA-256：
  `dc160e0a7dfbbf927801c1377fcc5cf4ea4500ae11c9ad11bd0621aea6a9c527`。

GTZAN `final1` 是 post-hoc/test-conditioned sensitivity checkpoint；本 archive 不改变其证据资格。
