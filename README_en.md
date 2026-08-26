# RubricSpan · Yuewei — A Subjective-Answer Grading Teacher Model

> A **local-first** intelligent grading system for Chinese subjective answers (humanities short-answer / essay / document-analysis questions). A large model generates training labels offline; a lightweight encoder model is trained to run on a commodity GPU (≥8 GB VRAM), closing the loop of "upload exam paper / question → answer recognition → automatic scoring → teacher review" via a web frontend. Fully local; separated frontend/backend, training/inference, and online/offline dual modes.

## Key Features

- **Interpretable scoring**: alongside the score, the exact student-text span that hits each scoring point is highlighted for teacher review.
- **Local execution**: the entire scoring pipeline runs on-device inference with no dependency on an online LLM.
- **Synonym / equivalent-answer handling**: alias expansion + semantic-similarity fallback correctly handles answers like "戊戌变法 / 百日维新 / 维新运动" (Hundred Days' Reform).
- **Natural-language standard answers**: teachers paste a natural-language rubric; an LLM parses it into a structured scoring config (points + weights + aliases).
- **Paper exam intake**: scanned / photographed sheets via OCR (suspended since M8 together with the retired Python runtime; native Rust port pending).
- **Dual backend**: Rust + GPU online service (production preferred) and WASM in-browser offline demo (fallback).

## Tech Stack

| Layer | Choice |
|---|---|
| Frontend | React 19 + Next.js 15 (App Router) + Radix UI + Tailwind CSS |
| Backend (online) | Full-stack Rust: Axum gateway + native inference via ort (ONNX Runtime), single binary without Python (GPU/CPU) |
| Backend (offline) | Lightweight model + WASM (in-browser inference) |
| Models | `Langboat/mengzi-bert-base` (MRC extraction) + `shibing624/text2vec-base-chinese` (similarity fallback) |
| OCR | RapidOCR (ONNX Runtime; suspended since M8, native Rust port pending) |
| Training | Python + PyTorch + Transformers / Sentence-Transformers |
| Storage | SQLite + local filesystem |

## Repository Layout

```
RubricSpan/
├── contracts/          # Frozen contracts: OpenAPI, JSON Schema, model-artifact spec
├── train/              # Python training side: labeling / alignment / training / eval / export
├── backend/            # Rust backend (Cargo workspace: server / scoring / inference / OCR / storage)
├── frontend/           # Next.js 15 frontend (grading workbench, etc.)
├── wasm/               # WASM offline inference build (fallback mode)
├── data/               # Data directory (raw / synthetic / processed; not committed)
├── models/             # Model artifacts (not committed; see contracts/model-artifacts.md)
├── docs/               # Project docs (VitePress site source)
└── .github/            # CI workflows and Issue/PR templates
```

## Quick Start

> Baseline: NVIDIA GPU (≥8GB VRAM) + CUDA 12, Python 3.10+, Rust stable, Node.js 20+.

### Backend (Rust online service)

```bash
cd backend
cargo run -p rubricspan-server
```

### Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

### Training pipeline (Python)

```bash
cd train
python -m venv .venv
.venv\Scripts\activate        # Windows; Linux/macOS use source .venv/bin/activate
pip install -r requirements.txt
```

## Documentation

All documentation lives under [`docs/`](docs/) and is published as a VitePress site via GitHub Pages (see `.github/workflows/docs.yml`):

- [Technical Plan (Plan Book)](docs/project/plan.md)
- [Execution Plan](docs/project/execution-plan.md)
- Component guides: [Backend](docs/guides/guide-backend.md) · [Frontend](docs/guides/guide-frontend.md) · [Training](docs/guides/guide-training.md)
- [M0 Environment Review](docs/milestone-m0-review.md)
- [M1 Labeling Review](docs/milestone-m1-review.md)
- [End-to-End Evaluation Report](docs/reports/m7-eval-report.md)
- [Deployment Guide](docs/guides/deployment.md)
- [Bad Cases](docs/quality/bad-cases.md)
- [Contract Changelog](docs/quality/changelog-contracts.md)
- [Licenses & Compliance](docs/licenses.md)

## Milestones

Data & Environment → LLM Labeling → Model Training & Export → OCR Integration → Rust Online Backend → Frontend → WASM Offline Fallback → Integration / Evaluation / Delivery (13 weeks total; see Execution Plan §3).

Current status: **M0–M7 all complete.** Delivered: FP32+INT8 dual models (ONNX), the Rust online service, the WASM in-browser offline demo, and the full training/evaluation toolchain. The [End-to-End Evaluation Report](docs/reports/m7-eval-report.md) shows system-level ScoreCorr **0.959** (target ≥0.85 ✅) and equivalence credit rate **97.4%** (target ≥80% ✅); Point-Acc 78.4% (affected by gold-label disagreement — see the [arbitration sheet](docs/reports/arbitration-sheet.md)) and model-level EM/F1 were reviewed and deferred to the iteration loop ([M7 review](docs/milestone-m7-review.md)).

The in-browser offline single-question demo is served at `/offline` once the frontend is running ([usage notes](docs/guides/wasm-offline.md)); see the [Deployment Guide](docs/guides/deployment.md) for operational details.

## License

[AGPL-3.0](LICENSE) — released under the GNU Affero General Public License v3.0. When the software is offered over a network, modified server-source must be made available to users (see LICENSE §13).
