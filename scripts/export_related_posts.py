"""記事ベクトルから各記事の関連記事3本を選び、src/data/related-posts.json に書き出す。"""
import json
import os

from google.cloud import bigquery

PROJECT = "tough-cipher-472109-v5"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "data", "related-posts.json")
TOP_N = 3

SQL = """
SELECT query.slug AS slug, base.slug AS related_slug
FROM VECTOR_SEARCH(
  TABLE learning.blog_vectors, 'embedding',
  TABLE learning.blog_vectors, 'embedding',
  top_k => 4, distance_type => 'COSINE')
WHERE base.slug <> query.slug
ORDER BY slug, distance
"""


def main():
    client = bigquery.Client(project=PROJECT)

    related = {}
    for row in client.query(SQL).result():
        related.setdefault(row["slug"], []).append(row["related_slug"])
    related = {slug: slugs[:TOP_N] for slug, slugs in sorted(related.items())}

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(related, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{len(related)}記事ぶんの関連記事を書き出しました")


if __name__ == "__main__":
    main()
