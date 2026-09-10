/**
 * 浏览器本地推理（M6 · 离线备选）：onnxruntime-web 加载 ONNX 模型，
 * 复刻 backend/runtime/model_runtime.py 的 /mrc 与 /similarity 算法，
 * 使离线结果与在线端可比（技术方案 §10.3 一致性要求）。
 */
import * as ort from "onnxruntime-web";
import { BertChineseTokenizer } from "./bert-tokenizer";

/** 与在线运行时一致的超参（model_runtime.py 常量） */
const MAX_SEQ_LEN = 512;
const MAX_SPAN_TOKENS = 64;
const SIM_MAX_LEN = 128;

export interface MrcResult {
  /** "是否含答案"概率（0–1） */
  has_answer_prob: number;
  /** 学生答案内字符级闭区间起点 */
  start: number;
  /** 学生答案内字符级闭区间终点（含）——与 Rust MrcOutput 契约一致 */
  end: number;
}

function logSoftmax(xs: Float32Array): Float32Array {
  let m = -Infinity;
  for (const x of xs) m = Math.max(m, x);
  let z = 0;
  const out = new Float32Array(xs.length);
  for (let i = 0; i < xs.length; i++) {
    out[i] = xs[i] - m;
    z += Math.exp(out[i]);
  }
  const lz = Math.log(z);
  for (let i = 0; i < xs.length; i++) out[i] -= lz;
  return out;
}

function feeds(enc: {
  inputIds: Uint32Array;
  attentionMask: Uint32Array;
  tokenTypeIds: Uint32Array;
}): Record<string, ort.Tensor> {
  const toI64 = (u: Uint32Array) => BigInt64Array.from(u as unknown as number[], (v) => BigInt(v));
  return {
    input_ids: new ort.Tensor("int64", toI64(enc.inputIds), [1, enc.inputIds.length]),
    attention_mask: new ort.Tensor("int64", toI64(enc.attentionMask), [1, enc.attentionMask.length]),
    token_type_ids: new ort.Tensor("int64", toI64(enc.tokenTypeIds), [1, enc.tokenTypeIds.length]),
  };
}

export class LocalInference {
  private tok: BertChineseTokenizer;
  private modelBase: string;
  private mrcSession?: ort.InferenceSession;
  private simSession?: ort.InferenceSession;

  private constructor(tok: BertChineseTokenizer, modelBase: string) {
    this.tok = tok;
    this.modelBase = modelBase;
  }

  static async create(modelBase = "/wasm/models"): Promise<LocalInference> {
    // WASM 二进制从本站加载，保证完全离线可用（不走 CDN）
    ort.env.wasm.wasmPaths = "/wasm/ort/";
    const tok = await BertChineseTokenizer.load(`${modelBase}/vocab.txt`);
    return new LocalInference(tok, modelBase);
  }

  /** 惰性创建会话：优先 INT8 量化版，缺失时回落 FP32。 */
  private async ensureMrc(): Promise<ort.InferenceSession> {
    if (!this.mrcSession) {
      const url = await pickModel(`${this.modelBase}/mrc`);
      this.mrcSession = await ort.InferenceSession.create(url, {
        executionProviders: ["wasm"],
        graphOptimizationLevel: "all",
      });
    }
    return this.mrcSession;
  }

  private async ensureSim(): Promise<ort.InferenceSession> {
    if (!this.simSession) {
      const url = await pickModel(`${this.modelBase}/sim`);
      this.simSession = await ort.InferenceSession.create(url, {
        executionProviders: ["wasm"],
        graphOptimizationLevel: "all",
      });
    }
    return this.simSession;
  }

  /**
   * MRC 多候选抽取：与在线端 /mrc 完全同构——
   * log_softmax 后以 null 概率（[CLS] 位）做有答判定，上下文区间内
   * 枚举 ≤MAX_SPAN_TOKENS 的最优跨度，输出字符级闭区间偏移。
   */
  async mrcExtract(candidate: string, studentAnswer: string): Promise<MrcResult> {
    const sess = await this.ensureMrc();
    const enc = this.tok.encodePair(candidate, studentAnswer, MAX_SEQ_LEN);
    const { start_logits: sOut, end_logits: eOut } = (await sess.run(feeds(enc))) as unknown as {
      start_logits: ort.Tensor;
      end_logits: ort.Tensor;
    };
    const sProbs = logSoftmax(sOut.data as Float32Array);
    const eProbs = logSoftmax(eOut.data as Float32Array);

    const ctxIdx: number[] = [];
    for (let i = 0; i < enc.sequenceIds.length; i++) {
      if (enc.sequenceIds[i] === 1) ctxIdx.push(i);
    }
    if (ctxIdx.length === 0) return { has_answer_prob: 0, start: 0, end: 0 };
    const lo = ctxIdx[0];
    const hi = ctxIdx[ctxIdx.length - 1];

    const nullLogprob = sProbs[0] + eProbs[0];
    let bestScore = -1e12;
    let bestI = lo;
    let bestJ = lo;
    for (let i = lo; i <= hi; i++) {
      const jMax = Math.min(i + MAX_SPAN_TOKENS - 1, hi);
      for (let j = i; j <= jMax; j++) {
        const score = sProbs[i] + eProbs[j];
        if (score > bestScore) {
          bestScore = score;
          bestI = i;
          bestJ = j;
        }
      }
    }
    const hasAnswerProb = 1 / (1 + Math.exp(nullLogprob - bestScore));

    const startChar = enc.offsets[bestI][0];
    const endCharExcl = enc.offsets[bestJ][1];
    return { has_answer_prob: hasAnswerProb, start: startChar, end: Math.max(endCharExcl - 1, startChar) };
  }

  /** 得分点文本 ↔ 学生答案整体的余弦相似度（注意力掩码均值池化）。 */
  async similarity(pointText: string, studentAnswer: string): Promise<number> {
    // onnxruntime-web 同一会话不允许并发 run，两次编码必须串行
    const va = await this.embed(pointText);
    const vb = await this.embed(studentAnswer);
    let dot = 0;
    let na = 0;
    let nb = 0;
    for (let i = 0; i < va.length; i++) {
      dot += va[i] * vb[i];
      na += va[i] * va[i];
      nb += vb[i] * vb[i];
    }
    return dot / (Math.sqrt(na) * Math.sqrt(nb) + 1e-9);
  }

  private async embed(text: string): Promise<Float32Array> {
    const sess = await this.ensureSim();
    const enc = this.tok.encode(text, SIM_MAX_LEN);
    const { last_hidden_state: hidden } = (await sess.run(feeds(enc))) as unknown as {
      last_hidden_state: ort.Tensor;
    };
    const data = hidden.data as Float32Array;
    const dim = hidden.dims[2];
    const out = new Float32Array(dim);
    let valid = 0;
    for (let t = 0; t < enc.attentionMask.length; t++) {
      if (enc.attentionMask[t] === 0) continue;
      valid += 1;
      for (let d = 0; d < dim; d++) out[d] += data[t * dim + d];
    }
    for (let d = 0; d < dim; d++) out[d] /= valid;
    return out;
  }
}

/** 优先 INT8，404 时回落 FP32。 */
async function pickModel(dirUrl: string): Promise<string> {
  const int8 = `${dirUrl}/model.int8.onnx`;
  try {
    const res = await fetch(int8, { method: "HEAD" });
    if (res.ok) return int8;
  } catch {
    /* 忽略：走 FP32 回落 */
  }
  return `${dirUrl}/model.onnx`;
}

export { BertChineseTokenizer };
