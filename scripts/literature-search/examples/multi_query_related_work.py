"""示例：多查询搜索 — 用于生成 Related Work 章节

运行方式（在 skills/literature-search/ 目录下）：
    python examples/multi_query_related_work.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.search import papers_to_bibtex, search_papers_multi_query

# ── 为 "RLHF 论文" 搜索相关工作 ────────────────────────────────────────────
queries = [
    "reinforcement learning from human feedback language model",
    "reward model preference learning",
    "constitutional AI alignment",
    "direct preference optimization DPO",
]

print("正在搜索多个查询（自动去重合并）...")
print(f"查询数: {len(queries)}\n")

papers = search_papers_multi_query(
    queries,
    limit_per_query=10,
    year_min=2022,
    inter_query_delay=2.0,  # 查询间等待 2 秒
)

print(f"\n去重后共 {len(papers)} 篇相关论文：\n")

# 按引用数排序（已自动排序）
for i, p in enumerate(papers[:10], 1):
    authors = ", ".join(a.name for a in p.authors[:2])
    if len(p.authors) > 2:
        authors += " et al."
    print(f"{i:2d}. [{p.year}] {p.title[:65]}")
    print(f"     {authors}  |  引用: {p.citation_count}  来源: {p.source}")

# 导出 BibTeX
bib = papers_to_bibtex(papers)
output_path = Path(__file__).parent / "rlhf_related_work.bib"
output_path.write_text(bib, encoding="utf-8")
print(f"\n完整 BibTeX 已保存到 {output_path}")
print(f"共 {len(papers)} 条引用")
