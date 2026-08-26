"""生成 OCR e2e 测试用的合成试卷图（一次性测试资产生成，非运行时依赖）。

用法：python scripts/make_ocr_test_image.py [out.png]
输出：白底黑字的模拟试卷作答图像（标题 + 题干 + 手写风格作答行）。
依赖：PIL（仅本生成脚本需要，服务端推理链路不需要 Python）。
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",   # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",  # 黑体
    "C:/Windows/Fonts/simsun.ttc",  # 宋体
]


def load_font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise FileNotFoundError("未找到可用中文字体（msyh/simhei/simsun）")


def main(out: str = "backend/target/ocr-test/q.png") -> None:
    W, H = 900, 1240
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title = load_font(34)
    f_body = load_font(30)
    f_answer = load_font(30)

    y = 60
    d.text((60, y), "三、简答题（本题 5 分）", font=f_title, fill="black")
    y += 90
    d.text((60, y), "简述戊戌变法的主要影响。", font=f_body, fill="black")
    y += 80
    # 作答区：横线 + 学生手写文本
    answers = [
        "戊戌变法发生在1898年，历史上又称百日维新。",
        "它推动了中国的近代化进程，是一次资产阶级改良运动。",
    ]
    for line in answers:
        d.text((70, y), line, font=f_answer, fill="black")
        y += 66
    # 作答区底纹横线（模拟试卷答题线）
    y += 30
    for i in range(4):
        d.line([(70, y + i * 60), (W - 70, y + i * 60)], fill=(210, 210, 210), width=2)

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"已生成：{out_path.resolve()}（{W}x{H}）")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "backend/target/ocr-test/q.png")