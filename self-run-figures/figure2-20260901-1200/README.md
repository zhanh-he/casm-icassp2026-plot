# CASM data-scaling 3×3 绘图包

这个文件夹可以独立运行。默认命令会从 130 行正式 plotting CSV 重新生成现有的 3×3 图；每个浅蓝散点是一种 development-fold combination，深蓝折线连接各 family 的等权均值。

## 一键画图

```bash
cd /Users/jollibear/Documents/casm-datascaling-plot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python plot_casm_datascaling_3x3.py
```

如果本机有 `uv`，无需先建环境：

```bash
cd /Users/jollibear/Documents/casm-datascaling-plot
uv run --with numpy --with matplotlib python plot_casm_datascaling_3x3.py
```

输出位于 `output/`：PNG、SVG、图中 family mean 汇总表和带 SHA-256 的 manifest。加 `--show` 会同时弹出 Matplotlib 窗口。

## 怎样单独折腾九个小图

打开 `plot_casm_datascaling_3x3.py` 顶部：

- `FIGURE_TWEAKS`：整张图的尺寸、字体、颜色、散点、折线、排版。
- `PANEL_TWEAKS`：九个 subplot 各自的覆盖项；空字典表示沿用正式图设置。

例如只改左上角 GTZAN Beat F1：

```python
"gtzan_final1.beat.beat_fmeasure": {
    "ylim": (87.486, 90.20),
    "yticks": [89.486, 89.70, 89.90, 90.10],
    "title": "My GTZAN Beat F1",
    "mean_color": "#DC2626",
    "mean_label_offsets": [(0, 7), (0, 7), (0, 10), (0, 7), (0, 7)],
},
```

九个 key 已经全部列在脚本里，支持 `ylim`、`yticks`、`title`、`ylabel`、`xlabels`、`show_mean_labels`、`mean_label_offsets`、`scatter_color`、`mean_color`。

## 数据目录

- `data/plotting/`：画图唯一需要的 canonical 130-row CSV 和 source receipt。
- `data/formal_results/`：组合级正式结果、score/config lock、候选与 checkpoint 摘要。
- `data/summaries/`：精确分数表和独立复核摘要。
- `data/full_raw_archive/`：完整实验归档，包括 per-piece ledgers、各 stage 表、QA bundle、日志与 manifests；保留它是为了以后换图或审计。
- `original_reference/`：当前正式 PNG/SVG 及原始 figure manifest，用来对照。

正式 plotting CSV 的 SHA-256：

`dc160e0a7dfbbf927801c1377fcc5cf4ea4500ae11c9ad11bd0621aea6a9c527`

注意：GTZAN `final1` 这一行是 post-hoc/test-conditioned sensitivity panel，不应改写成 clean frozen model-selection evidence；脚本会把这条限定保留在图的副标题里。
