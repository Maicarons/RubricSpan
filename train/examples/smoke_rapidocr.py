"""M0-6 smoke test: RapidOCR local inference on RTX 4060 (GPU via ONNX Runtime CUDA EP).

Generates a printed-text exam-style image, runs detection + recognition,
computes character-level accuracy against ground truth.
"""
import sys, time, json
from pathlib import Path

GT_LINES = [
    "1. 1911年辛亥革命成功，推翻了清王朝",
    "2. 戊戌变法又称百日维新",
    "3. 促进了思想启蒙运动的发展",
]

def make_image(out: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    W, H = 760, 300
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    font = None
    for cand in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc"]:
        try:
            font = ImageFont.truetype(cand, 28)
            break
        except OSError:
            continue
    if font is None:
        print("FAIL: no Chinese font found"); sys.exit(1)
    y = 30
    for line in GT_LINES:
        d.text((40, y), line, fill="black", font=font)
        y += 70
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)

def main() -> int:
    img_path = Path(__file__).parent / "ocr_sample.png"
    make_image(img_path)

    from rapidocr_onnxruntime import RapidOCR
    import onnxruntime as _ort
    # NOTE: rapidocr 1.2.3 requires per-module keys (det_/cls_/rec_use_cuda);
    # a bare top-level use_cuda lands in Global and is ignored.
    use_cuda = "CUDAExecutionProvider" in _ort.get_available_providers()
    # rapidocr 1.2.3 quirk: passing any det_/cls_/rec_ kwarg requires
    # model_path=None alongside, else UpdateParameters raises KeyError.
    ocr = RapidOCR(det_use_cuda=use_cuda, det_model_path=None,
                   cls_use_cuda=use_cuda, cls_model_path=None,
                   rec_use_cuda=use_cuda, rec_model_path=None,
                   intra_op_num_threads=4, inter_op_num_threads=4)
    print("EP:", ocr.text_detector.infer.session.get_providers(), "(use_cuda=%s)" % use_cuda)
    t0 = time.time()
    result, elapse = ocr(str(img_path))
    dt = time.time() - t0

    if not result:
        print("FAIL: no text detected"); return 1
    print(f"detected {len(result)} lines, wall={dt*1000:.0f}ms (engine={elapse})")

    gt = "".join(GT_LINES).replace(" ", "")
    pred = "".join(r[1] for r in result).replace(" ", "")
    correct = sum(a == b for a, b in zip(gt, pred))
    acc = correct / max(len(gt), len(pred))
    for item in result:
        text = str(item[1])
        score = float(item[2]) if len(item) > 2 else 0.0
        print(f"  [{score:.2f}] {text}")
    print(f"char_accuracy={acc:.2%} (gt_len={len(gt)}, pred_len={len(pred)})")
    ok = acc > 0.95
    print("PASS: RapidOCR smoke test" if ok else "WARN: accuracy below 95%, check fonts/EP")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
