"""ブログ記事をBigQueryに同期し、新しい記事だけベクトル化する。"""
import glob
import os
import re

from google.cloud import bigquery

PROJECT = "tough-cipher-472109-v5"
BLOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "data", "blog")

VECTORIZE_NEW_ARTICLES_SQL = """
INSERT INTO learning.blog_vectors (slug, title, url, tags, embedding)
SELECT slug, title, url, tags, ml_generate_embedding_result
FROM ML.GENERATE_EMBEDDING(
  MODEL learning.embedder,
  (
    SELECT slug, title, url, tags, text_for_embedding AS content
    FROM learning.blog_articles
    WHERE slug NOT IN (SELECT slug FROM learning.blog_vectors)
  ),
  STRUCT(TRUE AS flatten_json_output)
)
"""


def parse_articles():
    """【2】記事(.md)を読み、BigQuery用の行データに変換する。"""
    rows = []
    for path in sorted(glob.glob(os.path.join(BLOG_DIR, "*.md"))):
        slug = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            text = f.read()

        fm, body = {}, text
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
        if m:
            fm_raw, body = m.group(1), m.group(2)
            for line in fm_raw.splitlines():
                km = re.match(r"^(\w+):\s*(.*)$", line)
                if km:
                    fm[km.group(1)] = km.group(2).strip()

        # 下書き記事は公開されていないので対象外
        if fm.get("draft") == "true":
            continue

        def clean(v):
            return v.strip().strip('"').strip("'") if v else ""

        title = clean(fm.get("title", ""))
        desc = clean(fm.get("description", ""))
        tags_str = ", ".join(re.findall(r'"([^"]+)"', fm.get("tags", "")))
        body_clean = body.strip()

        rows.append({
            "slug": slug,
            "title": title,
            "description": desc,
            "tags": tags_str,
            "body": body_clean,
            "url": f"https://my-trip-note.com/posts/{slug}/",
            "text_for_embedding": f"タイトル: {title}\n説明: {desc}\nタグ: {tags_str}\n本文:\n{body_clean}",
        })
    return rows


def main():
    client = bigquery.Client(project=PROJECT)

    rows = parse_articles()
    print(f"【2】変換: {len(rows)}本")

    # 【3】記事テーブルを丸ごと入れ替え（bq load --replace と同じ）
    load_config = bigquery.LoadJobConfig(
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    client.load_table_from_json(rows, f"{PROJECT}.learning.blog_articles", job_config=load_config).result()
    print("【3】blog_articles を入れ替えました")

    # 【4】新しい記事だけベクトル化して追加
    job = client.query(VECTORIZE_NEW_ARTICLES_SQL)
    job.result()
    print(f"【4】ベクトル追加: {job.num_dml_affected_rows}本")


if __name__ == "__main__":
    main()
