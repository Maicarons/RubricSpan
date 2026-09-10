/**
 * BERT 中文 WordPiece 分词器（浏览器离线用，M6）。
 *
 * 与 HuggingFace BertTokenizerFast（do_lower_case=true，mengzi-bert /
 * text2vec-base-chinese 均如此）对齐的关键行为：
 * - 控制字符移除、空白折叠、CJK 字符独立切分、标点独立切分；
 * - 小写化 + NFD 去音符；
 * - WordPiece 贪婪最长匹配（## 续片），整词失败回退 [UNK]。
 *
 * **偏移单位**：所有 start/end 一律为 Unicode 标量（码点）下标，
 * 与 Rust 端 `char` 计数及 Python 运行时契约一致（BMP 内与 UTF-16 下标相同）。
 */

export interface TokenWithSpan {
  token: string;
  /** 起始码点下标（含） */
  start: number;
  /** 结束码点下标（不含） */
  end: number;
}

export interface PairEncoding {
  inputIds: Uint32Array;
  attentionMask: Uint32Array;
  tokenTypeIds: Uint32Array;
  /** 每个 token 的 (start, end) 码点区间；特殊 token 为 [0,0) */
  offsets: Array<[number, number]>;
  /** 0=句子 A（query），1=句子 B（context），特殊 token 为 null */
  sequenceIds: Array<number | null>;
}

interface NormChar {
  ch: string;
  srcStart: number;
}

const CJK_RANGES: Array<[number, number]> = [
  [0x4e00, 0x9fff],
  [0x3400, 0x4dbf],
  [0x20000, 0x2a6df],
  [0x2a700, 0x2b73f],
  [0x2b740, 0x2b81f],
  [0x2b820, 0x2ceaf],
  [0xf900, 0xfaff],
  [0x2f800, 0x2fa1f],
];

function isCjk(cp: number): boolean {
  return CJK_RANGES.some(([lo, hi]) => cp >= lo && cp <= hi);
}

function isWhitespace(ch: string): boolean {
  return ch === " " || ch === "\t" || ch === "\n" || ch === "\r";
}

function isControl(ch: string): boolean {
  const cp = ch.codePointAt(0)!;
  // HF 定义：\t\n\r 不算控制字符（按空白处理）
  if (ch === "\t" || ch === "\n" || ch === "\r") return false;
  return (cp < 0x20 && cp !== 0) || cp === 0x7f || (cp >= 0x80 && cp < 0xa0);
}

function isPunct(ch: string): boolean {
  const cp = ch.codePointAt(0)!;
  if (
    (cp >= 33 && cp <= 47) ||
    (cp >= 58 && cp <= 64) ||
    (cp >= 91 && cp <= 96) ||
    (cp >= 123 && cp <= 126)
  ) {
    return true;
  }
  return /\p{P}/u.test(ch);
}

/** 清洗 + 小写 + 去音符后的连续片段；每个规范化字符记录其源码点下标 */
interface Word {
  chars: NormChar[];
}

function basicWords(text: string): Word[] {
  const out: Word[] = [];
  let cur: NormChar[] = [];
  const flush = () => {
    if (cur.length > 0) {
      out.push({ chars: cur });
      cur = [];
    }
  };
  const scalars = Array.from(text);
  for (let i = 0; i < scalars.length; i++) {
    const ch = scalars[i];
    const cp = ch.codePointAt(0)!;
    if (cp === 0 || (isControl(ch) && !isWhitespace(ch))) continue;
    if (isControl(ch)) {
      flush();
      continue;
    }
    if (isWhitespace(ch)) {
      flush();
      continue;
    }
    if (isCjk(cp) || isPunct(ch)) {
      flush();
      out.push({ chars: [{ ch, srcStart: i }] });
      continue;
    }
    // 普通字符：小写 + NFD 去音符（组合音符被丢弃，映射仍逐字符精确）
    for (const part of Array.from(ch.toLowerCase().normalize("NFD"))) {
      if (/\p{M}/u.test(part)) continue;
      cur.push({ ch: part, srcStart: i });
    }
  }
  flush();
  return out;
}

export class BertChineseTokenizer {
  private vocab: Map<string, number>;
  readonly unkToken = "[UNK]";
  readonly clsToken = "[CLS]";
  readonly sepToken = "[SEP]";
  readonly padToken = "[PAD]";

  private constructor(vocabLines: string[]) {
    this.vocab = new Map(vocabLines.map((t, i) => [t, i]));
  }

  static async load(vocabUrl: string): Promise<BertChineseTokenizer> {
    const res = await fetch(vocabUrl);
    if (!res.ok) throw new Error(`vocab.txt 加载失败：${res.status} ${vocabUrl}`);
    return new BertChineseTokenizer((await res.text()).split("\n").map((l) => l.replace(/\r$/, "")));
  }

  id(token: string): number {
    return this.vocab.get(token) ?? this.vocab.get(this.unkToken)!;
  }

  /** 词级 tokenize（含码点偏移），等价 BasicTokenizer + WordPiece 全流程。 */
  tokenize(text: string): TokenWithSpan[] {
    const out: TokenWithSpan[] = [];
    for (const word of basicWords(text)) {
      out.push(...this.wordpiece(word));
    }
    return out;
  }

  private wordpiece(word: Word): TokenWithSpan[] {
    const chars = word.chars.map((c) => c.ch);
    if (chars.length > 100) {
      return [{ token: this.unkToken, start: word.chars[0].srcStart, end: word.chars[99].srcStart + 1 }];
    }
    const pieces: Array<{ token: string; normStart: number; normEnd: number }> = [];
    let start = 0;
    let ok = true;
    while (start < chars.length) {
      let end = chars.length;
      let cur = "";
      while (start < end) {
        cur = (start > 0 ? "##" : "") + chars.slice(start, end).join("");
        if (this.vocab.has(cur)) break;
        end -= 1;
      }
      if (start === end) {
        ok = false;
        break;
      }
      pieces.push({ token: cur, normStart: start, normEnd: end });
      start = end;
    }
    if (!ok) {
      return [
        {
          token: this.unkToken,
          start: word.chars[0].srcStart,
          end: word.chars[word.chars.length - 1].srcStart + 1,
        },
      ];
    }
    return pieces.map((p) => ({
      token: p.token,
      start: word.chars[p.normStart].srcStart,
      end: word.chars[p.normEnd - 1].srcStart + 1,
    }));
  }

  /**
   * 句对编码：`[CLS] A [SEP] B [SEP]`，截断策略 only_second（优先压缩 B）。
   *
   * 不做 max_length 定长填充：导出的 ONNX 序列维是动态轴，注意力掩码已正确
   * 标注有效位，搜索又限定在 context token 区间内——结果与定长填充一致，
   * 但省去 512 定长序列的无效计算（浏览器 WASM 推理速度关键）。
   */
  encodePair(query: string, context: string, maxLen = 512): PairEncoding {
    const qt = this.tokenize(query);
    const ct = this.tokenize(context);

    const maxQueryLen = maxLen - 3; // [CLS] A [SEP] B [SEP]
    const q = qt.length > maxQueryLen ? qt.slice(0, Math.max(maxQueryLen, 0)) : qt;
    const budget = maxLen - (q.length + 3);
    const c = ct.slice(0, Math.max(budget, 0));

    const ids: number[] = [this.id(this.clsToken)];
    const types: number[] = [0];
    const seqIds: Array<number | null> = [null];
    const offsets: Array<[number, number]> = [[0, 0]];

    for (const t of q) {
      ids.push(this.id(t.token));
      types.push(0);
      seqIds.push(0);
      offsets.push([t.start, t.end]);
    }
    ids.push(this.id(this.sepToken));
    types.push(0);
    seqIds.push(null);
    offsets.push([0, 0]);

    for (const t of c) {
      ids.push(this.id(t.token));
      types.push(1);
      seqIds.push(1);
      offsets.push([t.start, t.end]);
    }
    ids.push(this.id(this.sepToken));
    types.push(1);
    seqIds.push(null);
    offsets.push([0, 0]);

    const n = ids.length;
    return {
      inputIds: Uint32Array.from(ids),
      attentionMask: new Uint32Array(n).fill(1),
      tokenTypeIds: Uint32Array.from(types),
      offsets,
      sequenceIds: seqIds,
    };
  }

  /** 单句编码：`[CLS] text [SEP]`。 */
  encode(text: string, maxLen = 512): Omit<PairEncoding, "sequenceIds"> & { sequenceIds: Array<0 | null> } {
    const t = this.tokenize(text).slice(0, maxLen - 2);
    const ids: number[] = [this.id(this.clsToken)];
    const types: number[] = [0];
    const offsets: Array<[number, number]> = [[0, 0]];
    for (const tok of t) {
      ids.push(this.id(tok.token));
      types.push(0);
      offsets.push([tok.start, tok.end]);
    }
    ids.push(this.id(this.sepToken));
    types.push(0);
    offsets.push([0, 0]);
    const n = ids.length;
    return {
      inputIds: Uint32Array.from(ids),
      attentionMask: new Uint32Array(n).fill(1),
      tokenTypeIds: Uint32Array.from(types),
      offsets,
      sequenceIds: new Array(n).fill(null),
    };
  }
}
