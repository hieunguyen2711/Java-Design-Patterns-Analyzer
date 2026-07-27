# PIQS Automated-Scorer Replication of Kim (2025) — Validation Report

**Study.** Does my automated PIQS scorer (`app/services/piqs_service.py`, unmodified) reproduce the manual PIQS scores that Kim published in *“Comparative analysis of design pattern implementation validity in LLM-based code refactoring”*, J. Syst. Softw. 230 (2025) 112519, for his 10 LLM-refactored programs (POSS × 5 LLMs, SWS × 5 LLMs)?

**Answer, up front.** Individual-property agreement is **106/160 = 66.2%**. Only **16/40 (case, LLM, pattern) scoring units reproduce all three of Kim's PSR/CPC/PIQS exactly.** The scorer is **not yet a faithful automation of Kim's manual rubric**: Factory Method and Observer are badly misaligned, Composite and Strategy have systematic single-property faults, and a handful of Kim's own published numbers are internally inconsistent. Details, causes, and per-property fix recommendations below. **No scoring code was modified.**

### How to reproduce

```
unzip each *.zip from Design-Pattern-Applications/ into scratchpad (read-only on Kim's files)
python validation/build_manifest.py   # -> validation/kim_file_manifest.json
python validation/run_scorer.py       # -> validation/kim_replication_raw.json (+ javac)
python validation/compare.py          # -> validation/kim_comparison.json
python validation/make_report.py      # -> this file
```
Full command log: `validation/commands.log`. Scorer Python: 3.13.7.

---

## Step 1 — Corpus map and anomalies

Kim's repo ships **12 ZIPs**: 2 originals (`POS.zip`, `SmartWallet.zip`) and 10 refactored (`Refactored<POS|SWS><LLM>.zip`). All 10 expected (case × LLM) combinations are present; the manifest is `validation/kim_file_manifest.json` (145 `.java` files indexed, 40 scoring units).

Anomalies / things that did not fit the expected structure:

- **Two extra programs.** `POS` (12 files) and `SmartWallet` (6 files) are Kim's pre-refactoring base programs, not LLM output. They are **not** in Kim's Tables 13/16/17 and are excluded from scoring (recorded in the manifest with role `original_base`).

- **`POS` has 12 `.java` files vs the “11 classes”** stated for POSS. The extra file is `itemDescription.java` (lower-case name). Irrelevant to scoring (base program not scored), noted for completeness.

- **Nested folder layout.** Every ZIP expands to `<Program>/<Program>/src/...`; the refactored ones use `src/main/java/com/mycompany/<pkg>/`, the originals use `src/pointofsale` or `src/main/java/.../smartwallet`. Handled.

- **“Meta” = Llama 3.1-405B.** Folder names map cleanly to the five LLMs; no ambiguous names, no duplicated programs.

- **One interpretive point (not a blocker).** A design pattern is *not* a per-file attribute: each refactored program embodies all four of its case study's patterns at once. So the manifest maps files to (case study, LLM) and treats **(case study, LLM, pattern)** as the scoring unit — 4 patterns × 5 LLMs × 2 case studies = 40 units. If you intended a stricter one-pattern-per-file mapping, tell me and I will redo it.

---

## Step 2 — Metric definition check (weights & formulas)

Confirmed **identical** to Kim's Table 9 and the PIQS/PSR/CPC formulas. From `piqs_service.py`:

| Pattern | Weights in code | Total | Matches Kim |
|---|---|---|:--:|
| Factory Method | F1=2,F2=3,F3=3,F4=3,F5=2 | 13 | ✅ |
| Strategy | S1=3,S2=3,S3=2,S4=3 | 11 | ✅ |
| Composite | C1=3,C2=2,C3=3,C4=3,C5=3 | 14 | ✅ |
| Observer | O1=2,O2=3,O3=3,O4=3 | 11 | ✅ |
| Singleton | G1=3 | 3 | ✅ |

`PSR = satisfied/total*100` (line 115), `CPC = Σ(w·s)/Σw*100` (line 116), `PIQS = PSR*0.6 + CPC*0.4` (line 117). No weight or formula difference. The disagreements below are **entirely in the property predicates**, never in the weighting/aggregation.

### Verification of the Composite-row correction (task asked me to check)

I recomputed every one of Kim's 40 published (PSR, CPC, PIQS) triples from the failing-property set implied by his tables. **All 40 are internally consistent** once the Composite row is corrected as the task describes:

- **Claude / POSS / Composite** → 100 / 100 / 100 (all C pass). Check: Claude POSS average PIQS = (78.77 + 100 + **100** + 77.73)/4 = 89.12 ✅ (matches Kim's published per-model average).

- **Gemini / POSS / Composite** → 40 / 35.71 / 38.29 (C1,C4,C5 fail). Check: PSR 2/5=40, CPC (2+3)/14=35.71, PIQS 38.29; Gemini POSS average = (100+100+**38.29**+22.27)/4 = 65.14 ✅.

So the printed table's Claude↔Gemini Composite swap is confirmed, and my comparison uses the corrected values. (The per-model averages, not the swapped cells, are self-consistent.)

---

## 1 — Headline agreement rate

- **Property-level:** **106/160 individual property judgments agree = 66.2%.** (The task's “roughly 40” refers to the 40 scoring units; scored at the individual-property level there are 160 judgments — POSS: 5 LLMs × (5+4+5+4)=90; SWS: 5 × (5+4+1+4)=70.)

- **Score-level:** 16/40 (case, LLM, pattern) units match Kim's PSR, CPC and PIQS exactly.

- **By pattern:** Factory 19/50 (38%); Strategy 38/40 (95%); Composite 18/25 (72%); Observer 26/40 (65%); Singleton 5/5 (100%).

---

## 2 — Property-level comparison (one row per case, LLM, pattern, property)

`S`=satisfied, `·`=not satisfied. ✅=match, ❌=mismatch.

| Case | LLM | Pattern | Prop | Kim | Mine | Match |
|---|---|---|---|:--:|:--:|:--:|
| POSS | ChatGPT | Factory | F1 | · | S | ❌ |
| POSS | ChatGPT | Factory | F2 | S | S | ✅ |
| POSS | ChatGPT | Factory | F3 | S | S | ✅ |
| POSS | ChatGPT | Factory | F4 | S | S | ✅ |
| POSS | ChatGPT | Factory | F5 | S | S | ✅ |
| POSS | ChatGPT | Strategy | S1 | S | S | ✅ |
| POSS | ChatGPT | Strategy | S2 | S | S | ✅ |
| POSS | ChatGPT | Strategy | S3 | S | · | ❌ |
| POSS | ChatGPT | Strategy | S4 | S | S | ✅ |
| POSS | ChatGPT | Composite | C1 | S | S | ✅ |
| POSS | ChatGPT | Composite | C2 | S | S | ✅ |
| POSS | ChatGPT | Composite | C3 | S | S | ✅ |
| POSS | ChatGPT | Composite | C4 | S | S | ✅ |
| POSS | ChatGPT | Composite | C5 | S | · | ❌ |
| POSS | ChatGPT | Observer | O1 | S | · | ❌ |
| POSS | ChatGPT | Observer | O2 | S | S | ✅ |
| POSS | ChatGPT | Observer | O3 | S | S | ✅ |
| POSS | ChatGPT | Observer | O4 | S | S | ✅ |
| POSS | Claude | Factory | F1 | S | · | ❌ |
| POSS | Claude | Factory | F2 | S | · | ❌ |
| POSS | Claude | Factory | F3 | S | · | ❌ |
| POSS | Claude | Factory | F4 | · | S | ❌ |
| POSS | Claude | Factory | F5 | S | S | ✅ |
| POSS | Claude | Strategy | S1 | S | S | ✅ |
| POSS | Claude | Strategy | S2 | S | S | ✅ |
| POSS | Claude | Strategy | S3 | S | S | ✅ |
| POSS | Claude | Strategy | S4 | S | S | ✅ |
| POSS | Claude | Composite | C1 | S | S | ✅ |
| POSS | Claude | Composite | C2 | S | S | ✅ |
| POSS | Claude | Composite | C3 | S | S | ✅ |
| POSS | Claude | Composite | C4 | S | S | ✅ |
| POSS | Claude | Composite | C5 | S | · | ❌ |
| POSS | Claude | Observer | O1 | · | · | ✅ |
| POSS | Claude | Observer | O2 | S | S | ✅ |
| POSS | Claude | Observer | O3 | S | S | ✅ |
| POSS | Claude | Observer | O4 | S | S | ✅ |
| POSS | Copilot | Factory | F1 | · | · | ✅ |
| POSS | Copilot | Factory | F2 | S | · | ❌ |
| POSS | Copilot | Factory | F3 | S | · | ❌ |
| POSS | Copilot | Factory | F4 | S | · | ❌ |
| POSS | Copilot | Factory | F5 | S | S | ✅ |
| POSS | Copilot | Strategy | S1 | S | S | ✅ |
| POSS | Copilot | Strategy | S2 | S | S | ✅ |
| POSS | Copilot | Strategy | S3 | S | S | ✅ |
| POSS | Copilot | Strategy | S4 | S | S | ✅ |
| POSS | Copilot | Composite | C1 | · | S | ❌ |
| POSS | Copilot | Composite | C2 | S | S | ✅ |
| POSS | Copilot | Composite | C3 | S | S | ✅ |
| POSS | Copilot | Composite | C4 | · | S | ❌ |
| POSS | Copilot | Composite | C5 | · | · | ✅ |
| POSS | Copilot | Observer | O1 | · | · | ✅ |
| POSS | Copilot | Observer | O2 | S | S | ✅ |
| POSS | Copilot | Observer | O3 | S | S | ✅ |
| POSS | Copilot | Observer | O4 | S | S | ✅ |
| POSS | Gemini | Factory | F1 | S | · | ❌ |
| POSS | Gemini | Factory | F2 | S | · | ❌ |
| POSS | Gemini | Factory | F3 | S | · | ❌ |
| POSS | Gemini | Factory | F4 | S | S | ✅ |
| POSS | Gemini | Factory | F5 | S | S | ✅ |
| POSS | Gemini | Strategy | S1 | S | S | ✅ |
| POSS | Gemini | Strategy | S2 | S | S | ✅ |
| POSS | Gemini | Strategy | S3 | S | S | ✅ |
| POSS | Gemini | Strategy | S4 | S | S | ✅ |
| POSS | Gemini | Composite | C1 | · | S | ❌ |
| POSS | Gemini | Composite | C2 | S | S | ✅ |
| POSS | Gemini | Composite | C3 | S | S | ✅ |
| POSS | Gemini | Composite | C4 | · | S | ❌ |
| POSS | Gemini | Composite | C5 | · | · | ✅ |
| POSS | Gemini | Observer | O1 | S | · | ❌ |
| POSS | Gemini | Observer | O2 | · | S | ❌ |
| POSS | Gemini | Observer | O3 | · | S | ❌ |
| POSS | Gemini | Observer | O4 | · | S | ❌ |
| POSS | Meta | Factory | F1 | S | · | ❌ |
| POSS | Meta | Factory | F2 | S | · | ❌ |
| POSS | Meta | Factory | F3 | S | · | ❌ |
| POSS | Meta | Factory | F4 | S | S | ✅ |
| POSS | Meta | Factory | F5 | S | S | ✅ |
| POSS | Meta | Strategy | S1 | S | S | ✅ |
| POSS | Meta | Strategy | S2 | S | S | ✅ |
| POSS | Meta | Strategy | S3 | S | S | ✅ |
| POSS | Meta | Strategy | S4 | S | S | ✅ |
| POSS | Meta | Composite | C1 | S | S | ✅ |
| POSS | Meta | Composite | C2 | S | S | ✅ |
| POSS | Meta | Composite | C3 | S | S | ✅ |
| POSS | Meta | Composite | C4 | S | S | ✅ |
| POSS | Meta | Composite | C5 | S | · | ❌ |
| POSS | Meta | Observer | O1 | S | · | ❌ |
| POSS | Meta | Observer | O2 | S | S | ✅ |
| POSS | Meta | Observer | O3 | S | S | ✅ |
| POSS | Meta | Observer | O4 | S | S | ✅ |
| SWS | ChatGPT | Factory | F1 | · | · | ✅ |
| SWS | ChatGPT | Factory | F2 | S | · | ❌ |
| SWS | ChatGPT | Factory | F3 | S | · | ❌ |
| SWS | ChatGPT | Factory | F4 | · | · | ✅ |
| SWS | ChatGPT | Factory | F5 | · | S | ❌ |
| SWS | ChatGPT | Strategy | S1 | S | S | ✅ |
| SWS | ChatGPT | Strategy | S2 | S | S | ✅ |
| SWS | ChatGPT | Strategy | S3 | S | S | ✅ |
| SWS | ChatGPT | Strategy | S4 | S | S | ✅ |
| SWS | ChatGPT | Observer | O1 | · | · | ✅ |
| SWS | ChatGPT | Observer | O2 | S | S | ✅ |
| SWS | ChatGPT | Observer | O3 | S | · | ❌ |
| SWS | ChatGPT | Observer | O4 | S | S | ✅ |
| SWS | ChatGPT | Singleton | G1 | S | S | ✅ |
| SWS | Claude | Factory | F1 | S | · | ❌ |
| SWS | Claude | Factory | F2 | S | S | ✅ |
| SWS | Claude | Factory | F3 | S | S | ✅ |
| SWS | Claude | Factory | F4 | S | · | ❌ |
| SWS | Claude | Factory | F5 | · | S | ❌ |
| SWS | Claude | Strategy | S1 | S | S | ✅ |
| SWS | Claude | Strategy | S2 | S | S | ✅ |
| SWS | Claude | Strategy | S3 | S | S | ✅ |
| SWS | Claude | Strategy | S4 | S | S | ✅ |
| SWS | Claude | Observer | O1 | · | · | ✅ |
| SWS | Claude | Observer | O2 | S | S | ✅ |
| SWS | Claude | Observer | O3 | S | S | ✅ |
| SWS | Claude | Observer | O4 | S | S | ✅ |
| SWS | Claude | Singleton | G1 | S | S | ✅ |
| SWS | Copilot | Factory | F1 | · | S | ❌ |
| SWS | Copilot | Factory | F2 | S | S | ✅ |
| SWS | Copilot | Factory | F3 | S | S | ✅ |
| SWS | Copilot | Factory | F4 | S | · | ❌ |
| SWS | Copilot | Factory | F5 | · | S | ❌ |
| SWS | Copilot | Strategy | S1 | S | S | ✅ |
| SWS | Copilot | Strategy | S2 | S | S | ✅ |
| SWS | Copilot | Strategy | S3 | S | · | ❌ |
| SWS | Copilot | Strategy | S4 | S | S | ✅ |
| SWS | Copilot | Observer | O1 | S | · | ❌ |
| SWS | Copilot | Observer | O2 | S | · | ❌ |
| SWS | Copilot | Observer | O3 | S | · | ❌ |
| SWS | Copilot | Observer | O4 | S | · | ❌ |
| SWS | Copilot | Singleton | G1 | S | S | ✅ |
| SWS | Gemini | Factory | F1 | S | · | ❌ |
| SWS | Gemini | Factory | F2 | S | · | ❌ |
| SWS | Gemini | Factory | F3 | S | · | ❌ |
| SWS | Gemini | Factory | F4 | S | · | ❌ |
| SWS | Gemini | Factory | F5 | · | S | ❌ |
| SWS | Gemini | Strategy | S1 | S | S | ✅ |
| SWS | Gemini | Strategy | S2 | S | S | ✅ |
| SWS | Gemini | Strategy | S3 | S | S | ✅ |
| SWS | Gemini | Strategy | S4 | S | S | ✅ |
| SWS | Gemini | Observer | O1 | · | · | ✅ |
| SWS | Gemini | Observer | O2 | S | · | ❌ |
| SWS | Gemini | Observer | O3 | · | · | ✅ |
| SWS | Gemini | Observer | O4 | · | · | ✅ |
| SWS | Gemini | Singleton | G1 | S | S | ✅ |
| SWS | Meta | Factory | F1 | · | · | ✅ |
| SWS | Meta | Factory | F2 | S | S | ✅ |
| SWS | Meta | Factory | F3 | S | · | ❌ |
| SWS | Meta | Factory | F4 | S | · | ❌ |
| SWS | Meta | Factory | F5 | · | S | ❌ |
| SWS | Meta | Strategy | S1 | S | S | ✅ |
| SWS | Meta | Strategy | S2 | S | S | ✅ |
| SWS | Meta | Strategy | S3 | S | S | ✅ |
| SWS | Meta | Strategy | S4 | S | S | ✅ |
| SWS | Meta | Observer | O1 | S | · | ❌ |
| SWS | Meta | Observer | O2 | S | · | ❌ |
| SWS | Meta | Observer | O3 | · | · | ✅ |
| SWS | Meta | Observer | O4 | · | · | ✅ |
| SWS | Meta | Singleton | G1 | S | S | ✅ |

---

## 3 — Score-level comparison (one row per case, LLM, pattern)

| Case | LLM | Pattern | Kim PSR/CPC/PIQS | My PSR/CPC/PIQS | ΔPSR | ΔCPC | ΔPIQS |
|---|---|---|---|---|--:|--:|--:|
| POSS | ChatGPT | Factory | 80.00/84.62/81.85 | 100.00/100.00/100.00 | 20.00 | 15.38 | 18.15 |
| POSS | ChatGPT | Strategy | 100.00/100.00/100.00 | 75.00/81.82/77.73 | 25.00 | 18.18 | 22.27 |
| POSS | ChatGPT | Composite | 100.00/100.00/100.00 | 80.00/78.57/79.43 | 20.00 | 21.43 | 20.57 |
| POSS | ChatGPT | Observer | 100.00/100.00/100.00 | 75.00/81.82/77.73 | 25.00 | 18.18 | 22.27 |
| POSS | Claude | Factory | 80.00/76.92/78.77 | 40.00/38.46/39.38 | 40.00 | 38.46 | 39.39 |
| POSS | Claude | Strategy | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| POSS | Claude | Composite | 100.00/100.00/100.00 | 80.00/78.57/79.43 | 20.00 | 21.43 | 20.57 |
| POSS | Claude | Observer | 75.00/81.82/77.73 | 75.00/81.82/77.73 | 0.00 | 0.00 | 0.00 |
| POSS | Copilot | Factory | 80.00/84.62/81.85 | 20.00/15.38/18.15 | 60.00 | 69.24 | 63.70 |
| POSS | Copilot | Strategy | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| POSS | Copilot | Composite | 40.00/35.71/38.29 | 80.00/78.57/79.43 | 40.00 | 42.86 | 41.14 |
| POSS | Copilot | Observer | 75.00/81.82/77.73 | 75.00/81.82/77.73 | 0.00 | 0.00 | 0.00 |
| POSS | Gemini | Factory | 100.00/100.00/100.00 | 40.00/38.46/39.38 | 60.00 | 61.54 | 60.62 |
| POSS | Gemini | Strategy | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| POSS | Gemini | Composite | 40.00/35.71/38.29 | 80.00/78.57/79.43 | 40.00 | 42.86 | 41.14 |
| POSS | Gemini | Observer | 25.00/18.18/22.27 | 75.00/81.82/77.73 | 50.00 | 63.64 | 55.46 |
| POSS | Meta | Factory | 100.00/100.00/100.00 | 40.00/38.46/39.38 | 60.00 | 61.54 | 60.62 |
| POSS | Meta | Strategy | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| POSS | Meta | Composite | 100.00/100.00/100.00 | 80.00/78.57/79.43 | 20.00 | 21.43 | 20.57 |
| POSS | Meta | Observer | 100.00/100.00/100.00 | 75.00/81.82/77.73 | 25.00 | 18.18 | 22.27 |
| SWS | ChatGPT | Factory | 40.00/46.15/42.46 | 20.00/15.38/18.15 | 20.00 | 30.77 | 24.31 |
| SWS | ChatGPT | Strategy | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| SWS | ChatGPT | Observer | 75.00/81.82/77.73 | 50.00/54.55/51.82 | 25.00 | 27.27 | 25.91 |
| SWS | ChatGPT | Singleton | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| SWS | Claude | Factory | 80.00/84.62/81.85 | 60.00/61.54/60.62 | 20.00 | 23.08 | 21.23 |
| SWS | Claude | Strategy | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| SWS | Claude | Observer | 75.00/81.82/77.73 | 75.00/81.82/77.73 | 0.00 | 0.00 | 0.00 |
| SWS | Claude | Singleton | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| SWS | Copilot | Factory | 60.00/69.23/63.69 | 80.00/76.92/78.77 | 20.00 | 7.69 | 15.08 |
| SWS | Copilot | Strategy | 100.00/100.00/100.00 | 75.00/81.82/77.73 | 25.00 | 18.18 | 22.27 |
| SWS | Copilot | Observer | 100.00/100.00/100.00 | 0.00/0.00/0.00 | 100.00 | 100.00 | 100.00 |
| SWS | Copilot | Singleton | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| SWS | Gemini | Factory | 80.00/84.62/81.85 | 20.00/15.38/18.15 | 60.00 | 69.24 | 63.70 |
| SWS | Gemini | Strategy | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| SWS | Gemini | Observer | 25.00/27.27/25.91 | 0.00/0.00/0.00 | 25.00 | 27.27 | 25.91 |
| SWS | Gemini | Singleton | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| SWS | Meta | Factory | 60.00/69.23/63.69 | 40.00/38.46/39.38 | 20.00 | 30.77 | 24.31 |
| SWS | Meta | Strategy | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |
| SWS | Meta | Observer | 50.00/45.45/48.18 | 0.00/0.00/0.00 | 50.00 | 45.45 | 48.18 |
| SWS | Meta | Singleton | 100.00/100.00/100.00 | 100.00/100.00/100.00 | 0.00 | 0.00 | 0.00 |

### Overall PIQS per model (Kim Table 17) vs mine

| LLM | Kim POSS | Mine POSS | Kim SWS | Mine SWS | Kim overall | Mine overall |
|---|--:|--:|--:|--:|--:|--:|
| ChatGPT | 95.46 | 83.72 | 80.05 | 67.49 | 87.75 | 75.61 |
| Claude | 89.12 | 74.14 | 89.89 | 84.59 | 89.51 | 79.36 |
| Copilot | 74.46 | 68.83 | 90.92 | 64.12 | 82.69 | 66.48 |
| Gemini | 65.14 | 74.14 | 76.94 | 54.54 | 71.04 | 64.34 |
| Meta | 100.00 | 74.14 | 77.97 | 59.84 | 88.98 | 66.99 |

> The overall column is the mean of the two case-study means (as in Kim's Table 17). My overall numbers are depressed mainly by Factory Method and Observer, the two most misaligned patterns.

---

## 4 — Disagreement analysis

All **54** mismatches, classified:

| Cause | Count |
|---|--:|
| too strict → false positive (I fail code Kim accepted) | 33 |
| too loose → false negative (I pass code Kim rejected) | 10 |
| source could not be parsed | 1 |
| Kim's published numbers internally inconsistent | 9 |
| genuine ambiguity in the property definition | 1 |

Full itemised classification (each row is one mismatch from the table in §2):

| Case | LLM | Pattern | Prop | Dir. | Cause | Why (with code evidence) |
|---|---|---|---|:--:|---|---|
| POSS | ChatGPT | Factory | F1 | Kim · / me S | LOOSE | F1 matches ANY abstract class; it latched onto `abstract class SaleComponent` (Composite component). The real creator `PaymentFactory` is a concrete class. |
| POSS | ChatGPT | Strategy | S3 | Kim S / me · | STRICT | is_context requires a stored strategy field or setter; here the strategy is a local var in main and passed as a parameter (RefactoredPOSChatGPT.java:47). |
| POSS | ChatGPT | Composite | C5 | Kim S / me · | STRICT | uniform check keys off abstract_components[0], which is an arbitrary interface (Strategy/Observer), not SaleComponent. |
| POSS | ChatGPT | Observer | O1 | Kim S / me · | STRICT | abstract subject `InventorySubject` is an interface, but subject_candidates only includes kind=='class', so O1 can never see it. |
| POSS | Claude | Factory | F1 | Kim S / me · | STRICT | creator is `interface PaymentFactory`; F1 requires an abstract class. |
| POSS | Claude | Factory | F2 | Kim S / me · | STRICT | concrete factories use `implements PaymentFactory`; F2 only recognises `extends`. |
| POSS | Claude | Factory | F3 | Kim S / me · | STRICT | override detection only follows `extends`, not interface `implements`. |
| POSS | Claude | Factory | F4 | Kim · / me S | AMBIG | F2/F3/F4 all have weight 3 and are arithmetically indistinguishable; Kim's 'F4 fails' label is prose-derived (task warns prose is unreliable). My F4 passes (createPayment returns new CashPayment). |
| POSS | Claude | Composite | C5 | Kim S / me · | STRICT | uniform check keys off arbitrary abstract_components[0]. |
| POSS | Copilot | Factory | F2 | Kim S / me · | STRICT | single static factory + product subclasses; F2 only recognises `extends`. |
| POSS | Copilot | Factory | F3 | Kim S / me · | STRICT | override via interface not detected. |
| POSS | Copilot | Factory | F4 | Kim S / me · | PARSE | `createPayment(...) throws Exception {` is not matched by the method regex (throws clause), so the method and its `Payment` return type are never seen; F4 cannot fire. |
| POSS | Copilot | Composite | C1 | Kim · / me S | LOOSE | the Strategy `Payment` / Observer `InventoryObserver` interfaces are counted as abstract components; no real Composite exists. |
| POSS | Copilot | Composite | C4 | Kim · / me S | LOOSE | Register (has addSale/addInventory) is mislabeled a composite and ByCash/ByCreditCard leaves; no real Composite exists. |
| POSS | Gemini | Factory | F1 | Kim S / me · | STRICT | creator is `interface PaymentFactory`. |
| POSS | Gemini | Factory | F2 | Kim S / me · | STRICT | factories use `implements`. |
| POSS | Gemini | Factory | F3 | Kim S / me · | STRICT | override via interface not detected. |
| POSS | Gemini | Composite | C1 | Kim · / me S | LOOSE | Payment/InventoryObserver interfaces counted as components; no real Composite. |
| POSS | Gemini | Composite | C4 | Kim · / me S | LOOSE | spurious composite/leaf from unrelated classes. |
| POSS | Gemini | Observer | O1 | Kim S / me · | KIM | Kim's numeric O1=satisfied is semantically impossible: there is NO abstract subject (ItemInventory is a concrete class, no Subject interface). My O1=not satisfied matches the code. |
| POSS | Gemini | Observer | O2 | Kim · / me S | KIM | `interface InventoryObserver{void update(...)}` genuinely exists, so O2 is defensibly satisfied; Kim's numeric O2=fail contradicts the code. |
| POSS | Gemini | Observer | O3 | Kim · / me S | KIM | ItemInventory.notifyObservers iterates observers and calls update(); O3 is defensibly satisfied. Kim's numeric O3=fail contradicts the code. |
| POSS | Gemini | Observer | O4 | Kim · / me S | KIM | Register implements InventoryObserver.update(); O4 defensibly satisfied. Kim's numeric O4=fail contradicts the code. |
| POSS | Meta | Factory | F1 | Kim S / me · | STRICT | creator is `interface PaymentFactory`. |
| POSS | Meta | Factory | F2 | Kim S / me · | STRICT | PaymentFactoryImpl uses `implements`. |
| POSS | Meta | Factory | F3 | Kim S / me · | STRICT | override via interface not detected. |
| POSS | Meta | Composite | C5 | Kim S / me · | STRICT | uniform check keys off arbitrary abstract_components[0]. |
| POSS | Meta | Observer | O1 | Kim S / me · | STRICT | abstract subject `InventorySubject` is an interface, invisible to subject_candidates (kind=='class' only). |
| SWS | ChatGPT | Factory | F2 | Kim S / me · | KIM | ChatGPT's SWS has NO factory class at all; Kim's F2=satisfied (creator has a concrete implementation) is indefensible. My F2=not satisfied matches the code. |
| SWS | ChatGPT | Factory | F3 | Kim S / me · | KIM | No factory exists; Kim's F3=satisfied is indefensible. |
| SWS | ChatGPT | Factory | F5 | Kim · / me S | LOOSE | F5 counts `AddFundsStrategy implements TransactionStrategy` etc. as 'products'; Wallet has no product interface, which is why Kim fails F5. |
| SWS | ChatGPT | Observer | O3 | Kim S / me · | STRICT | notification is a direct single-observer call `auditLog.update(...)` (User.java:25,37) with no observer collection, no loop, and no recognised subject class; O3 requires a subject with a notify method iterating a collection. |
| SWS | Claude | Factory | F1 | Kim S / me · | STRICT | creator is `interface WalletFactory`. |
| SWS | Claude | Factory | F4 | Kim S / me · | STRICT | createWallet returns the CONCRETE class `Wallet`; F4 only recognises products whose type is an abstract type. |
| SWS | Claude | Factory | F5 | Kim · / me S | LOOSE | F5 counts Strategy/Observer implementers as products; Wallet has no product interface. |
| SWS | Copilot | Factory | F1 | Kim · / me S | KIM | Copilot's SWS genuinely has `abstract class WalletFactory` + `ConcreteWalletFactory extends WalletFactory`, so an abstract creator exists (my F1=satisfied). Kim's F1=fail while F2/F3/F4=pass is internally inconsistent. |
| SWS | Copilot | Factory | F4 | Kim S / me · | STRICT | createWallet returns the concrete `Wallet`; F4 only recognises abstract-typed products. |
| SWS | Copilot | Factory | F5 | Kim · / me S | LOOSE | Strategy implementers counted as products. |
| SWS | Copilot | Strategy | S3 | Kim S / me · | STRICT | Wallet.performTransaction(amount, TransactionStrategy strategy) receives the strategy as a parameter (Wallet.java:28), not a stored field/setter; is_context fails. |
| SWS | Copilot | Observer | O1 | Kim S / me · | STRICT | observer callback is `notify(Transaction)` not `update`; and the subject Wallet is a concrete class with no abstract subject. O1 cannot see it. |
| SWS | Copilot | Observer | O2 | Kim S / me · | STRICT | `interface TransactionObserver{void notify(...)}` is not recognised because O2 requires an interface method named exactly `update`. |
| SWS | Copilot | Observer | O3 | Kim S / me · | STRICT | Wallet.notifyObservers loops and calls `observer.notify(...)`, but O3 requires a literal `.update(` call. |
| SWS | Copilot | Observer | O4 | Kim S / me · | STRICT | no observer_types found (callback named `notify`), so concrete_observers is empty and O4 fails. |
| SWS | Gemini | Factory | F1 | Kim S / me · | STRICT | creator is `interface WalletFactory`. |
| SWS | Gemini | Factory | F2 | Kim S / me · | STRICT | DefaultWalletFactory uses `implements`. |
| SWS | Gemini | Factory | F3 | Kim S / me · | STRICT | override via interface not detected. |
| SWS | Gemini | Factory | F4 | Kim S / me · | STRICT | createWallet returns the concrete `Wallet`; F4 only recognises abstract-typed products. |
| SWS | Gemini | Factory | F5 | Kim · / me S | LOOSE | Strategy implementers counted as products. |
| SWS | Gemini | Observer | O2 | Kim S / me · | STRICT | `interface AuditLogObserver{void onLogEvent(...)}` not recognised; O2 requires a method named exactly `update`. |
| SWS | Meta | Factory | F3 | Kim S / me · | KIM | Meta's SWS has NO factory; Kim's F3=satisfied is indefensible. My F3=not satisfied matches the code. |
| SWS | Meta | Factory | F4 | Kim S / me · | KIM | No factory exists; Kim's F4=satisfied is indefensible. |
| SWS | Meta | Factory | F5 | Kim · / me S | LOOSE | Strategy implementers counted as products. |
| SWS | Meta | Observer | O1 | Kim S / me · | STRICT | `AuditLog extends Observable` (java.util.Observable); the JDK subject/observer framework is invisible to the scorer, which only recognises hand-rolled interfaces + literal notify methods. |
| SWS | Meta | Observer | O2 | Kim S / me · | STRICT | uses java.util.Observer via Observable; no hand-rolled `update` interface for O2 to find. |


### Root causes, grouped (with code)

**A. Factory Method predicates assume class-inheritance and are the single biggest source of error (F1–F5 all < 55% reliable).**
Kim's corpus overwhelmingly implements Factory Method with an **interface** creator, but the scorer's Factory predicates are written for **abstract-class** creators and `extends`-based hierarchies.

- **F1 (`any class that is_abstract`)** is doubly wrong. It ignores interface creators *and* accepts any abstract class regardless of role. Claude/Gemini/Meta POSS and Claude/Gemini SWS all declare the creator as an interface, e.g.:
  ```java
  // RefactoredPOSClaude/PaymentFactory.java:12
  interface PaymentFactory { PaymentStrategy createPayment(); }
  ```
  → no abstract *class* → my F1 = not satisfied, Kim = satisfied. Conversely, ChatGPT POSS has a *concrete* factory but an unrelated abstract Composite component, so F1 fires on the wrong type:
  ```java
  // RefactoredPOSChatGPT/PaymentFactory.java:12  (concrete!)
  class PaymentFactory { public static PaymentStrategy getPaymentMethod(String type){...} }
  // RefactoredPOSChatGPT/SaleComponent.java:12   <- my F1 matched THIS
  abstract class SaleComponent { ... }
  ```

- **F2 / F3 only recognise `extends`.** Interface factories use `implements`:
  ```java
  // RefactoredPOSClaude/CashPaymentFactory.java:12-16
  class CashPaymentFactory implements PaymentFactory {
      @Override public PaymentStrategy createPayment() { return new CashPayment(); }
  }
  ```
  My F2 (`concrete class with .extends`) and F3 (override via `extends`) both miss this → false negatives everywhere the factory is interface-based.

- **F4 requires the product's static type to be an *abstract* type.** SWS returns a **concrete** `Wallet`:
  ```java
  // RefactoredSWSClaude/StandardWalletFactory.java:13-15
  public Wallet createWallet(String currency) { return new Wallet(currency); }
  ```
  `Wallet` is a concrete class, not in `product_names`, so F4 cannot fire (Claude/Copilot/Gemini SWS). Kim accepts it.

- **F5 counts Strategy/Observer implementers as “products.”** In every SWS program Kim fails F5 because `Wallet` implements no product interface, but my `is_product_exists` is satisfied by unrelated strategy classes:
  ```java
  // RefactoredSWSClaude/DepositStrategy... implements TransactionStrategy  (an abstract type)
  ```
  → 5/5 SWS false positives on F5.

**B. Parser limitation: methods with a `throws` clause are dropped.** `_METHOD_SIG_RE` requires `)` to be followed directly by `{`/`;`, so a `throws` clause breaks the match:
```java
// RefactoredPOSCopilot/PaymentFactory.java:13
public static Payment createPayment(String paymentType) throws Exception { ... return new ByCash(); }
```
This method is never extracted; its `Payment` return type is invisible, so F4 (and `hasFactory`) cannot fire even though this *is* a correct interface-typed factory. Independently, the method extractor also re-scans method bodies and captures statements like `observers.add(observer);` as phantom methods (e.g. Copilot's `PaymentFactory` “methods” come out as `ByCash`, `ByCreditCard`, `Exception`). This noise mostly perturbs Factory/Observer name-matching.

**C. Composite is anchored on “any interface = a component” and “any add/remove-named method = a composite.”** In the two POSS programs with **no** Composite (Copilot, Gemini — there is no `SaleComponent`), the Strategy/Observer interfaces masquerade as components and `Register.addSale/addInventory` masquerades as a composite:
```java
// RefactoredPOSCopilot/Register.java:36,40  -> makes Register a "composite"
public void addSale(Sale s){...}   public void addInventory(Item item,int q){...}
// the REAL container, Sale, implements NO component interface, so it is ignored:
// RefactoredPOSCopilot/Sale.java:16   class Sale { private List<SaleLineItem> slis; public void add(SaleLineItem sli){...} }
```
→ C1 and C4 false-positive for Copilot/Gemini. **C5 (uniform treatment)** fails on the *real* composites (ChatGPT/Claude/Meta) because the check keys off `abstract_components[0]` — an arbitrary interface — and `composites[0]`/`leaves[0]`, not the actual `SaleComponent` API. So C5 is 0 for all five POSS programs (wrong for 3, right for 2).

**D. Strategy S3 (context) requires a stored strategy field or setter; it rejects strategy-as-parameter.** ChatGPT POSS and Copilot SWS pass the strategy in as a method argument:
```java
// RefactoredPOSChatGPT/RefactoredPOSChatGPT.java:47   PaymentStrategy payment = PaymentFactory.getPaymentMethod(paymentType);
// RefactoredSWSCopilot/Wallet.java:28   public String performTransaction(double amount, TransactionStrategy strategy){ strategy.execute(...); }
```
`is_context` needs `(field or setter) AND execute`, so these “contexts” are not recognised. (S1/S2/S4 are 100% reliable — Strategy is otherwise fine.)

**E. Observer hard-codes the callback name `update` and a collection+loop notification shape; it cannot see interface subjects or the JDK Observer framework.**
- **O1** checks `is_abstract` only among `subject_candidates`, which are filtered to `kind=='class'`. Every real subject here is either an interface (`InventorySubject`) or a concrete class, so **O1 is 0 in all 10 programs** — right when Kim also fails it, wrong otherwise.
  ```java
  // RefactoredPOSChatGPT/InventorySubject.java:12   interface InventorySubject { void addObserver(...); void notifyObservers(...);}  <- invisible to O1
  ```
- **O2/O3/O4** depend on an interface method literally named `update` and a `.update(` call. Copilot SWS (`notify`), Gemini SWS (`onLogEvent`), and Meta SWS (`java.util.Observable`) therefore score **0/0/0/0** although their Observer implementations are real:
  ```java
  // RefactoredSWSCopilot/TransactionObserver.java:12   interface TransactionObserver { void notify(Transaction t); }
  // RefactoredSWSGemini/AuditLogObserver.java:12       interface AuditLogObserver { void onLogEvent(String s); }
  // RefactoredSWSMeta/AuditLog.java:14                 class AuditLog extends Observable { void logAction(...){ setChanged(); notifyObservers(...);} }
  ```
- **O3 also rejects single-observer direct notification.** SWS ChatGPT notifies one directly-held observer with no collection/loop, so O3 fails although notification clearly happens:
  ```java
  // RefactoredSWSChatGPT/User.java:18,25,37   Observer auditLog; ... auditLog.update("User created: "+name); ... auditLog.update("Wallet added: "+currency);
  ```

**F. A distinct category: Kim's own published numbers are internally inconsistent in several cells** (the task warned about this; treating the numeric tables as authoritative surfaces them as “mismatches” that are really Kim-side problems):
- **POSS / Gemini / Observer** — near-total inversion. Kim's numeric row (PSR 25) forces **O1 satisfied, O2/O3/O4 not**, but the code has **no abstract subject at all** (`ItemInventory` is a concrete class) while it *does* have a working `update` interface, a notify-loop, and a concrete observer. My verdict (O1 not satisfied, O2/O3/O4 satisfied) is the defensible reading; Kim's numeric O1=satisfied is impossible. (The task itself flags Gemini/Observer prose↔number conflict.)
- **SWS / ChatGPT / Factory** and **SWS / Meta / Factory** — these programs contain **no factory class whatsoever**, yet Kim's numbers mark F2/F3 (ChatGPT) and F3/F4 (Meta) satisfied. “Creator has a concrete implementation” cannot hold when no creator exists. My not-satisfied verdicts match the code.
- **SWS / Copilot / Factory / F1** — Copilot's SWS *does* have `abstract class WalletFactory` + `ConcreteWalletFactory extends WalletFactory`, so an abstract creator exists (my F1 satisfied), yet Kim marks F1 failed while F2/F3/F4 pass — internally inconsistent.

These Kim-side cases (9 of the 54 mismatches) are **not** scorer defects; if anything they show the automated scorer disagreeing *correctly* with a flawed manual cell.

---

## 5 — Per-property reliability

Flag = agreement < 80% → unreliable for the main study.

| Prop | Meaning | Tested | Agree | Agreement | Reliable? |
|---|---|--:|--:|--:|:--:|
| F1 | abstract creator exists | 10 | 3 | 30.0% | ❌ **UNRELIABLE** |
| F2 | creator has concrete impl | 10 | 4 | 40.0% | ❌ **UNRELIABLE** |
| F3 | concrete creator overrides factory method | 10 | 3 | 30.0% | ❌ **UNRELIABLE** |
| F4 | factory creates correct product type | 10 | 4 | 40.0% | ❌ **UNRELIABLE** |
| F5 | concrete products implement product interface | 10 | 5 | 50.0% | ❌ **UNRELIABLE** |
| S1 | abstract strategy exists | 10 | 10 | 100.0% | ✅ |
| S2 | strategy has concrete impl | 10 | 10 | 100.0% | ✅ |
| S3 | context class exists | 10 | 8 | 80.0% | ✅ |
| S4 | strategies implement algorithm | 10 | 10 | 100.0% | ✅ |
| C1 | abstract component exists | 5 | 3 | 60.0% | ❌ **UNRELIABLE** |
| C2 | leaf exists | 5 | 5 | 100.0% | ✅ |
| C3 | composite exists | 5 | 5 | 100.0% | ✅ |
| C4 | composite & leaf implement component | 5 | 3 | 60.0% | ❌ **UNRELIABLE** |
| C5 | uniform treatment | 5 | 2 | 40.0% | ❌ **UNRELIABLE** |
| O1 | abstract subject exists | 10 | 5 | 50.0% | ❌ **UNRELIABLE** |
| O2 | abstract observer exists | 10 | 6 | 60.0% | ❌ **UNRELIABLE** |
| O3 | subject notifies observers | 10 | 7 | 70.0% | ❌ **UNRELIABLE** |
| O4 | observers update on notify | 10 | 8 | 80.0% | ✅ |
| G1 | private constructor / singleton | 5 | 5 | 100.0% | ✅ |

**Reliable (≥80%):** S1,S2,S4 (100%), G1 (100%), C2,C3 (100%), O4 (80%), S3 (80%). **Unreliable:** all five Factory properties (30–50%), C1,C4 (60%), C5 (40%), O1 (50%), O2 (60%), O3 (70%). Note several 'agreements' are **coincidental** (right verdict, wrong reason) — e.g. SWS F2/F3 pass only because an unrelated class uses `extends` (User extends Subject/Observable) — so true reliability of Factory is even lower than the raw percentages suggest.

---

## 6 — Compilation results (`javac` 21)

| Case | LLM | Compiles? | Kim says executable? | Match | First javac error |
|---|---|:--:|:--:|:--:|---|
| POSS | ChatGPT | ✅ yes | yes | ✅ |  |
| POSS | Claude | ✅ yes | yes | ✅ |  |
| POSS | Copilot | ❌ no | no | ✅ | POS.java:37: cannot find symbol |
| POSS | Gemini | ❌ no | no | ✅ | InventoryObserver.java:13: cannot find symbol (8 errors) |
| POSS | Meta | ❌ no | no | ✅ | RefactoredPOSMeta.java:45: components has private access in Sale |
| SWS | ChatGPT | ✅ yes | no | ❌ |  |
| SWS | Claude | ✅ yes | yes | ✅ |  |
| SWS | Copilot | ❌ no | no | ✅ | RefactoredSWSCopilot.java:37: void cannot be converted to AuditLog |
| SWS | Gemini | ❌ no | no | ✅ | DefaultWalletFactory.java:15: constructor Wallet cannot be applied (11 errors) |
| SWS | Meta | ❌ no | no | ✅ | RefactoredSWSMeta.java:16: cannot find symbol |

**Match with Kim: 9/10.** Kim: *“only ChatGPT and Claude produced executable POSS programs, and only Claude produced an executable SWS program.”* My javac results agree on all POSS programs and on SWS Claude/Copilot/Gemini/Meta. **The one contradiction: SWS / ChatGPT compiles cleanly for me** (javac 21, no errors) whereas Kim reports it non-executable. Likely explanations: (a) “executable” for Kim means *runs to completion*, not merely *compiles* — the program reads from `System.in`, so a run could stall or throw at runtime while still compiling; or (b) toolchain/version differences. Worth a manual `java` run to settle, but by the objective `javac` criterion it compiles.

---

## 7 — Recommendation per property

Legend: **KEEP** = matches Kim reliably; **FIX** = automatable, predicate needs work; **DROP** = too ambiguous / manual-judgement-heavy to automate for the main study.

| Prop | Verdict | Action |
|---|:--:|---|
| **F1** abstract creator | **FIX** | Accept an **interface** creator, and tie it to the creator role: an abstract type (interface *or* abstract class) that declares a method whose return type is a product and/or is implemented by ≥1 concrete factory. Do not accept an arbitrary abstract class. |
| **F2** creator has concrete impl | **FIX** | Treat `implements <Creator>` the same as `extends <Creator>`. Currently only `extends` counts. |
| **F3** concrete creator overrides factory method | **FIX** | Detect `@Override`/same-signature methods across **interface implementation**, not just class inheritance. |
| **F4** creates correct product type | **FIX** | (a) allow the product's static type to be a **concrete** class, not only an abstract type; (b) fix the `throws`-clause parser gap so factory methods declared `throws` are seen. |
| **F5** concrete products implement product interface | **FIX** | Anchor “product” to the *type the factory method returns*, not to “any concrete class implementing any abstract type.” This stops Strategy/Observer implementers counting as products (fixes all 5 SWS false positives). |
| **S1** abstract strategy | **KEEP** | 100%. |
| **S2** strategy has concrete impl | **KEEP** | 100%. |
| **S3** context class exists | **FIX** | Accept a class that receives/uses a strategy **via parameter or local variable**, not only via a stored field/setter. (80% now; the two misses are both parameter-style contexts.) |
| **S4** strategies implement algorithm | **KEEP** | 100%. |
| **C1** abstract component | **FIX** | Only count a component that actually participates in a part–whole hierarchy (a type used as the element type of a collection held by a composite of that same type), not any interface in the file. |
| **C2** leaf | **KEEP** | 100% here — but note it passes partly by luck; re-verify after C1/C3 are anchored to a real hierarchy. |
| **C3** composite | **KEEP\*** | 100% here, but “has an add/remove-named method” is fragile (it mislabels `Register.addSale`). Tighten to “holds a collection of the component type” when you fix C1/C4. |
| **C4** composite & leaf implement component | **FIX** | Follow from a corrected C1: require both the composite and the leaf to implement the *same* component type; stop firing on unrelated interfaces. |
| **C5** uniform treatment | **FIX** | Do not key off `abstract_components[0]`/`composites[0]`/`leaves[0]`. Compare the **actual component's** method set against the specific composite and leaf that implement it. (40% now.) |
| **O1** abstract subject | **FIX** | Include **interface** subjects: allow `subject_candidates` of `kind=='interface'`, and count an abstract subject when a Subject interface (or abstract class) declares attach/detach/notify. Currently structurally impossible to satisfy. |
| **O2** abstract observer | **FIX** | Do not hard-code the method name `update`. Detect the observer interface by its role (implemented by classes the subject notifies), accepting `notify`, `onLogEvent`, `java.util.Observer`, etc. |
| **O3** subject notifies observers | **FIX** | Generalise: accept notification through a single held observer (no loop) and callbacks not literally named `update`; recognise `java.util.Observable.notifyObservers`. |
| **O4** observers update on notify | **FIX** | Tie to the observer interface's actual callback method (see O2), not the literal name `update`. (80% now, best of the four, but same root fix.) |
| **G1** private constructor / singleton | **KEEP** | 100% (all 5 SWS Singletons agree). |

**Bottom line for the main study.** As-is, only **Strategy (minus S3), Singleton, and the Composite leaf/composite existence checks** are trustworthy. **Factory Method and Observer should not be used for per-property claims until FIXed** — they are 30–55% reliable and several agreements are coincidental. After the fixes above (most are small, well-scoped predicate changes; the `throws` parser gap is a one-line regex fix), re-run this exact harness to confirm before relying on the numbers. Separately, **flag the Kim-side inconsistent cells** (POSS Gemini Observer; SWS ChatGPT/Meta Factory; SWS Copilot F1) in the paper rather than treating them as scorer error.


---

*Generated by `validation/make_report.py`. Inputs: `kim_replication_raw.json`, `kim_comparison.json`, `kim_file_manifest.json`. Scorer read-only and unmodified throughout.*
