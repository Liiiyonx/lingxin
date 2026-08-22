# -*- coding: utf-8 -*-
import os
import sys

import fitz


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def render_pdf(pdf_path, out_dir, dpi=120):
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    scale = dpi / 72.0
    paths = []
    for page_num, page in enumerate(doc, 1):
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        out = os.path.join(out_dir, f"page-{page_num}.png")
        pix.save(out)
        paths.append(out)
    print(f"Rendered {len(paths)} pages to {out_dir}")


if __name__ == "__main__":
    jobs = [
        (os.path.join(ROOT, ".qa_render", "pdf", "聆心平台项目概要介绍.pdf"),
         os.path.join(ROOT, ".qa_render", "overview")),
        (os.path.join(ROOT, ".qa_render", "pdf", "聆心平台设计方案书.pdf"),
         os.path.join(ROOT, ".qa_render", "design")),
    ]
    for pdf, out in jobs:
        render_pdf(pdf, out)
