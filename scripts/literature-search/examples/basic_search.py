"""示例：基础文献搜索

运行方式（在 skills/literature-search/ 目录下）：
    python examples/basic_search.py
"""

import sys
from pathlib import Path

# 把 lib/ 加入路径，使其可直接 import（无需安装）
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.search import papers_to_bibtex, search_papers

# ── 1. 单查询搜索 ──────────────────────────────────────────────────────────
print("=" * 60)
print("示例 1：单查询搜索（3 个数据源，自动去重）")
print("=" * 60)

papers = search_papers(
    "transformer attention mechanism",
    limit=10,       # 每个数据源最多 10 条
    year_min=2020,  # 只要 2020 年以后的
)

print(f"\n共找到 {len(papers)} 篇论文（去重后）：\n")
for i, p in enumerate(papers[:5], 1):
    authors = ", ".join(a.name for a in p.authors[:2])
    if len(p.authors) > 2:
        authors += " et al."
    print(f"{i}. [{p.year}] {p.title}")
    print(f"   作者: {authors}")
    print(f"   引用: {p.citation_count}  来源: {p.source}")
    print(f"   URL:  {p.url}")
    print()

# ── 2. 只搜 arXiv（最新 preprint）─────────────────────────────────────────
print("=" * 60)
print("示例 2：只搜 arXiv")
print("=" * 60)

arxiv_papers = search_papers(
    "large language model reasoning",
    limit=5,
    sources=("arxiv",),
)
print(f"\narXiv 返回 {len(arxiv_papers)} 篇：\n")
for p in arxiv_papers:
    print(f"  [{p.year}] {p.title[:70]}")
    print(f"         arXiv:{p.arxiv_id}")

# ── 3. 导出 BibTeX ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("示例 3：导出 BibTeX")
print("=" * 60)

bib = papers_to_bibtex(papers[:3])
print("\n前 3 篇的 BibTeX：\n")
print(bib)

# 保存到文件
output_path = Path(__file__).parent / "output_references.bib"
output_path.write_text(bib, encoding="utf-8")
print(f"已保存到 {output_path}")
