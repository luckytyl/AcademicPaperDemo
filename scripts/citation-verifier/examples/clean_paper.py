"""示例：验证引用并同时清理论文正文中的 \\cite{} 标记

运行方式（在 skills/citation-verifier/ 目录下）：
    python examples/clean_paper.py paper.tex references.bib
    python examples/clean_paper.py paper.md  references.bib
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.verify import annotate_paper_hallucinations, filter_verified_bibtex, verify_citations

# ── 示例 LaTeX 论文片段 ────────────────────────────────────────────────────
SAMPLE_PAPER = r"""
\section{Related Work}

Transformer architectures \cite{attention2017} have become the dominant
paradigm in NLP. BERT \cite{bert2019} demonstrated the power of
bidirectional pretraining. Some researchers also claim that quantum
neural networks achieve infinite intelligence \cite{fake2024}, though
this remains controversial.
"""

SAMPLE_BIB = """
@article{attention2017,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish and Shazeer, Noam},
  year = {2017},
  eprint = {1706.03762},
}

@article{bert2019,
  title = {BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding},
  author = {Devlin, Jacob and Chang, Ming-Wei},
  year = {2019},
  doi = {10.18653/v1/N19-1423},
}

@article{fake2024,
  title = {Quantum Neural Networks for Infinite Intelligence: A Complete Survey},
  author = {Smith, John},
  year = {2024},
}
"""

# ── 读取文件（或使用示例）────────────────────────────────────────────────────
if len(sys.argv) >= 3:
    paper_text = Path(sys.argv[1]).read_text(encoding="utf-8")
    bib_text = Path(sys.argv[2]).read_text(encoding="utf-8")
    print(f"论文: {sys.argv[1]}")
    print(f"引用: {sys.argv[2]}")
else:
    paper_text = SAMPLE_PAPER
    bib_text = SAMPLE_BIB
    print("使用内置示例")

print("\n" + "=" * 60)
print("原始论文片段：")
print("=" * 60)
print(paper_text)

# ── 验证引用 ──────────────────────────────────────────────────────────────
print("正在验证引用...\n")
report = verify_citations(bib_text)

print(f"结果: {report.verified} 通过 / {report.suspicious} 可疑 / {report.hallucinated} 幻觉\n")

# ── 清理论文正文 ──────────────────────────────────────────────────────────
clean_paper = annotate_paper_hallucinations(paper_text, report)
clean_bib = filter_verified_bibtex(bib_text, report)

print("=" * 60)
print("清理后的论文片段：")
print("=" * 60)
print(clean_paper)

if report.hallucinated > 0:
    hallucinated = [r.cite_key for r in report.results if r.status.value == "hallucinated"]
    print(f"已移除幻觉引用: {hallucinated}")

# 保存结果
out_dir = Path(__file__).parent
(out_dir / "paper_clean.tex").write_text(clean_paper, encoding="utf-8")
(out_dir / "references_clean.bib").write_text(clean_bib, encoding="utf-8")
print(f"\n已保存到 {out_dir}/paper_clean.tex 和 references_clean.bib")
