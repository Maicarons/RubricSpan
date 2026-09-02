#!/usr/bin/env python
"""把 fp32 ONNX 模型转换为 fp16 内部精度（IO 保持 fp32/dynamic，遇不支持 op 自动回落 fp32）。

产物：`{models}/mrc/model.fp16.onnx`、`{models}/similarity/model.fp16.onnx`，
由后端 `RUBRICSPAN_MODEL_PRECISION=fp16` 选择（缺失时回落 fp32）。
fp16 档专为 GPU 部署（较新架构 GPU 有 fp16 Tensor Core，显存减半）；
不是对拍契约目标（fp16 数值与 fp32 金标差 >1e-3，勿用 parity_check 验收）。

用法（仓库根目录）：
    python scripts/export_fp16.py [models_dir=../models]
对应依赖：onnxconverter-common（`pip install onnxconverter-common`）。
"""
import sys
from pathlib import Path

import onnx
import onnx.numpy_helper as np_helper
from onnxconverter_common import float16


def harmonize_fp16(m: onnx.ModelProto) -> int:
    """修复 keep_io_types 导致的混合类型算术：BERT 包装图里 attention mask
    路径经 Cast/缩放后保持 fp32，却与 fp16 隐层进入同一 Add/Mul/Div 节点，
    ORT 加载直接报 Type Error。逐节点追踪张量 dtype（initializer + Constant
    输出 + 前驱传播），对"fp16 节点混入 fp32 输入"统一插 Cast(fp16)。"""

    types: dict[str, int | None] = {}
    for init in m.graph.initializer:
        types[init.name] = init.data_type
    for vi in m.graph.value_info:
        if vi.type.tensor_type.elem_type:
            types[vi.name] = vi.type.tensor_type.elem_type
    for inp in m.graph.input:
        if inp.type.tensor_type.elem_type:
            types[inp.name] = inp.type.tensor_type.elem_type

    out_nodes = []
    cast_nodes = 0
    for node in m.graph.node:
        if node.op_type == "Constant" and len(node.output) == 1:
            t = node.attribute[0]
            if t.type == onnx.AttributeProto.TENSOR:
                payload = np_helper.to_array(t.t)
                types[node.output[0]] = onnx.helper.np_dtype_to_tensor_dtype(payload.dtype)
        if node.op_type in ("Add", "Sub", "Mul", "Div", "Pow", "MatMul"):
            ins = [types.get(i) for i in node.input]
            if onnx.TensorProto.FLOAT16 in ins:
                casts = []
                for k, (name, dt) in enumerate(zip(node.input, ins)):
                    if dt == onnx.TensorProto.FLOAT:
                        cast_out = f"{name}__fp16__{cast_nodes}"
                        casts.append(onnx.helper.make_node(
                            "Cast", inputs=[name], outputs=[cast_out],
                            to=onnx.TensorProto.FLOAT16,
                        ))
                        types[cast_out] = onnx.TensorProto.FLOAT16
                        node.input[k] = cast_out
                        cast_nodes += 1
                out_nodes.extend(casts)
        out_nodes.append(node)
    del m.graph.node[:]
    m.graph.node.extend(out_nodes)
    return cast_nodes


def convert(model_path: Path, out_path: Path) -> bool:
    print(f"[1/3] load {model_path.name} ({model_path.stat().st_size / 1e6:.0f}MB) ...")
    model = onnx.load(str(model_path), load_external_data=False)
    # convert_float_to_float16：不支持的算子自动回落 FP32；IO 保持 fp32 使
    # 后端 tokenizer/池化无需改动。
    model_fp16 = float16.convert_float_to_float16(
        model,
        keep_io_types=True,
        disable_shape_infer=True,
        op_block_list=None,
    )
    # 先做 shape inference 让中间张量进入 value_info，harmonize 才能识别 fp32 混入
    model_fp16 = onnx.shape_inference.infer_shapes(model_fp16)
    n = harmonize_fp16(model_fp16)
    print(f"[2/3] 混合类型修复：插入 {n} 个 Cast(fp32→fp16)")
    onnx.save(model_fp16, str(out_path))
    print(f"[3/3] saved {out_path.name} ({out_path.stat().st_size / 1e6:.0f}MB)")
    return True


def main() -> int:
    models = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../models")
    ok = True
    for sub in ("mrc", "similarity"):
        src = models / sub / "model.onnx"
        if not src.exists():
            print(f"skip {src}: 不存在")
            ok = False
            continue
        ok &= convert(src, models / sub / "model.fp16.onnx")
    if not ok:
        print("部分转换失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())