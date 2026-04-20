"""示例：验证 .bib 文件中的所有引用

运行方式（在 skills/citation-verifier/ 目录下）：
    python examples/verify_bib_file.py path/to/references.bib

或使用内置示例：
    python examples/verify_bib_file.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.verify import (
    VerifyStatus,
    annotate_paper_hallucinations,
    filter_verified_bibtex,
    verify_citations,
)

# ── 示例 BibTeX（包含一条幻觉引用）──────────────────────────────────────────
SAMPLE_BIB = """
@article{attention2017,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish and Shazeer, Noam and Parmar, Niki},
  year = {2017},
  eprint = {1706.03762},
  archiveprefix = {arXiv},
}

@article{bert2019,
  title = {BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding},
  author = {Devlin, Jacob and Chang, Ming-Wei and Lee, Kenton and Toutanova, Kristina},
  year = {2019},
  doi = {10.18653/v1/N19-1423},
}

@article{fake2024,
  title = {Quantum Neural Networks for Infinite Intelligence: A Complete Survey},
  author = {Smith, John and Doe, Jane},
  year = {2024},
}
"""

# ── 读取 .bib 文件（或使用示例）──────────────────────────────────────────────
if len(sys.argv) > 1:
    bib_path = Path(sys.argv[1])
    if not bib_path.exists():
        print(f"错误：文件不存在 {bib_path}")
        sys.exit(1)
    bib_text = bib_path.read_text(encoding="utf-8")
    print(f"正在验证: {bib_path} ({bib_text.count('@')} 条引用)")
else:
    bib_text = SAMPLE_BIB
    print("使用内置示例（3 条引用，其中 1 条为幻觉引用）")

print("=" * 60)

# ── 运行验证 ──────────────────────────────────────────────────────────────
print("\n正在验证引用（每条约 1-2 秒）...\n")
report = verify_citations(bib_text)

# ── 打印汇总 ──────────────────────────────────────────────────────────────
print("=" * 60)
print("验证结果汇总")
print("=" * 60)
print(f"总计:       {report.total}")
print(f"✅ 验证通过: {report.verified}")
print(f"⚠️  可疑:    {report.suspicious}")
print(f"❌ 幻觉引用: {report.hallucinated}")
print(f"⏭️  跳过:    {report.skipped}")
print(f"完整性分数: {report.integrity_score:.1%}")
print()

# ── 打印每条结果 ──────────────────────────────────────────────────────────
status_emoji = {
    VerifyStatus.VERIFIED: "✅",
    VerifyStatus.SUSPICIOUS: "⚠️ ",
    VerifyStatus.HALLUCINATED: "❌",
    VerifyStatus.SKIPPED: "⏭️ ",
}

for r in report.results:
    emoji = status_emoji[r.status]
    print(f"{emoji} [{r.cite_key}] {r.title[:60]}")
    print(f"   方法: {r.method}  置信度: {r.confidence:.2f}")
    if r.details:
        print(f"   详情: {r.details}")
    print()

# ── 导出清理后的 .bib ────────────────────────────────────────────────────
if report.hallucinated > 0:
    clean_bib = filter_verified_bibtex(bib_text, report, include_suspicious=True)
    output_path = Path(__file__).parent / "references_clean.bib"
    output_path.write_text(clean_bib, encoding="utf-8")
    print(f"清理后的 .bib 已保存到 {output_path}")
    print(f"（已移除 {report.hallucinated} 条幻觉引用）")
else:
    print("所有引用均通过验证，无需清理。")

# ── 导出 JSON 报告 ────────────────────────────────────────────────────────
report_path = Path(__file__).parent / "verification_report.json"
report_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n详细报告已保存到 {report_path}")
