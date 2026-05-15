# Reviewed Datasheet KPI Findings

This benchmark slice evaluates the 9 fully reviewed, non-empty ground-truth datasheets in `corpus/ground_truth` across all 7 configured parser output types. The 3 zero-table Nokia datasheets are omitted from this view.

Scores were generated with `evaluation/llm_rescore_reviewed.py`, using the repository KPI definitions:

- `TCA`: Table Cell Accuracy
- `FLS`: Footnote Linkage Score
- `SS`: Structure Score
- `MMNS`: Multi-modulation Normalization Score
- `Composite`: weighted quality score using `0.40*TCA + 0.25*FLS + 0.20*SS + 0.15*MMNS`

`FLS` and `MMNS` are scored only where applicable, then the composite is reweighted over the available KPI components.

## Summary Results

| Rank | Parser | Composite | TCA | FLS | SS | MMNS | Speed score | Seconds/page |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | `docling` | 0.8270 | 0.8521 | 0.7284 | 0.8983 | 0.6500 | 0.6977 | 1.7698 |
| 2 | `unstructured_hires` | 0.8170 | 0.8485 | 0.7284 | 0.8499 | 0.6500 | 0.6751 | 2.2242 |
| 3 | `marker` | 0.7658 | 0.8080 | 0.5972 | 0.8336 | 0.6500 | 0.5691 | 7.0003 |
| 4 | `pymupdf4llm` | 0.6652 | 0.6681 | 0.4486 | 0.8200 | 0.8500 | 0.8455 | 0.5409 |
| 5 | `unstructured_fast` | 0.1873 | 0.0000 | 0.2539 | 0.4000 | 0.9000 | 0.9535 | 0.1353 |
| 6 | `opendataloader_heuristic` | 0.0637 | 0.0000 | 0.0000 | 0.2346 | 0.0000 | 1.0000 | 0.0000 |
| 7 | `opendataloader_hybrid` | 0.0637 | 0.0000 | 0.0000 | 0.2346 | 0.0000 | 1.0000 | 0.0000 |

## Key Findings

`docling` is the best overall parser on the reviewed subset, with the highest composite score (`0.8270`) and the strongest structure score (`0.8983`).

`unstructured_hires` is very close to `docling`, with nearly identical table cell accuracy and footnote linkage. Its main gap is structure score and runtime.

`marker` is a strong third-place parser, with good table extraction quality but slower throughput than the other high-quality options.

`pymupdf4llm` is the fastest high-quality parser and has the best `MMNS` score, but its lower table cell accuracy and footnote linkage reduce its overall composite.

`unstructured_fast` preserves some text and modulation cues, but it emits no usable table objects for TCA in this corpus snapshot, so its composite is much lower despite excellent speed.

`opendataloader_heuristic` and `opendataloader_hybrid` produced `library not installed` outputs in this run. Their quality scores should be treated as failed-run results rather than parser capability limits.

## Reviewed Datasheets

The rescoring scope includes:

- `AdTran 1442440F1 Datasheet`
- `Arpers FN-TRAN-GC-COM Copper Small Form Pluggable`
- `ATGBICS 1442120G1 AdTran Compatible Transceiver SFP 1000Base-BX-D`
- `Ciena 160-9116-900 compatible SFP+ transceiver`
- `Cisco CFP2-DCO`
- `Smartoptics QSFP-DD TQD029-TUNC-SO`
- `Smartoptics QSFP28 TQ2025-TUNC-SO ds-tq2028-tunc-so-qsfp28-100g-coherent-dwdm-sff-r6.4`
- `Smartoptics QSFP28 TQ2025-TUNC-SO`
- `so-xfp-er-dxxxx`

## Reproduce

Run:

```powershell
python evaluation\llm_rescore_reviewed.py
```

Generated local artifacts:

- `reports/llm_rescore_reviewed_summary.csv`
- `reports/llm_rescore_reviewed_detail.csv`
- `reports/llm_rescore_reviewed.json`

