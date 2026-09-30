"""ブログ記事をBigQueryに同期し、記事と段落のベクトルを必要な分だけ更新する。"""
import glob
import os
import re

from google.cloud import bigquery

PROJECT = "tough-cipher-472109-v5"
BLOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "data", "blog")

# リンクが並ぶだけの見出しは、中身の情報が無いので段落にしない
SKIP_HEADINGS = {"前の記事", "次の記事", "次に読む記事"}
MIN_CHUNK_CHARS = 20
HEADING = re.compile(r"^(#{2,3})\s+(.+)$", re.M)

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

# 背番号・記事名・見出し・本文のどれかが最新の段落と違うベクトルは、古いので消す
DELETE_STALE_CHUNK_VECTORS_SQL = """
DELETE FROM learning.blog_chunk_vectors v
WHERE NOT EXISTS (
  SELECT 1 FROM learning.blog_chunks c
  WHERE c.chunk_id = v.chunk_id
    AND c.title = v.title
    AND c.heading = v.heading
    AND c.content = v.chunk_text
)
"""

# ベクトルが無い段落だけベクトル化する（失敗した行は入れず、次回また試す）
VECTORIZE_NEW_CHUNKS_SQL = """
INSERT INTO learning.blog_chunk_vectors (chunk_id, slug, title, url, heading, chunk_text, embedding)
SELECT chunk_id, slug, title, url, heading, chunk_text, ml_generate_embedding_result
FROM ML.GENERATE_EMBEDDING(
  MODEL learning.embedder,
  (
    SELECT chunk_id, slug, title, url, heading,
           content AS chunk_text,
           text_for_embedding AS content
    FROM learning.blog_chunks
    WHERE chunk_id NOT IN (SELECT chunk_id FROM learning.blog_chunk_vectors)
  ),
  STRUCT(TRUE AS flatten_json_output)
)
WHERE ml_generate_embedding_status = ''
"""


def clean(v):
    return v.strip().strip('"').strip("'") if v else ""


def read_articles():
    """記事(.md)を読み、フロントマターと本文に分ける。下書きは除く。"""
    articles = []
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

        if fm.get("draft") == "true":
            continue
        articles.append({"slug": slug, "fm": fm, "body": body.strip()})
    return articles


def to_article_rows(articles):
    """【2】記事1本=1行のデータにする。"""
    rows = []
    for a in articles:
        title = clean(a["fm"].get("title", ""))
        desc = clean(a["fm"].get("description", ""))
        tags_str = ", ".join(re.findall(r'"([^"]+)"', a["fm"].get("tags", "")))
        rows.append({
            "slug": a["slug"],
            "title": title,
            "description": desc,
            "tags": tags_str,
            "body": a["body"],
            "url": f"https://my-trip-note.com/posts/{a['slug']}/",
            "text_for_embedding": f"タイトル: {title}\n説明: {desc}\nタグ: {tags_str}\n本文:\n{a['body']}",
        })
    return rows


def split_sections(body):
    """本文を (見出し, 中身) のリストに分ける。最初の見出しより前は「導入」とする。"""
    matches = list(HEADING.finditer(body))
    first = matches[0].start() if matches else len(body)
    sections = [("導入", body[:first])]
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections.append((m.group(2).strip(), body[m.end():end]))
    return sections


def to_chunk_rows(articles):
    """【5】記事を見出しごとの段落に分け、段落1つ=1行のデータにする。"""
    rows = []
    for a in articles:
        title = clean(a["fm"].get("title", ""))
        no = 0
        for heading, content in split_sections(a["body"]):
            content = content.strip()
            if heading in SKIP_HEADINGS or len(content) < MIN_CHUNK_CHARS:
                continue
            no += 1
            rows.append({
                "chunk_id": f"{a['slug']}#{no:02d}",
                "slug": a["slug"],
                "title": title,
                "url": f"https://my-trip-note.com/posts/{a['slug']}/",
                "heading": heading,
                "content": content,
                "text_for_embedding": f"記事: {title}\n見出し: {heading}\n{content}",
            })
    return rows


def replace_table(client, rows, table):
    """テーブルの中身を丸ごと入れ替える（bq load --replace と同じ）。"""
    config = bigquery.LoadJobConfig(
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    client.load_table_from_json(rows, f"{PROJECT}.learning.{table}", job_config=config).result()


def run_dml(client, sql):
    job = client.query(sql)
    job.result()
    return job.num_dml_affected_rows or 0


def main():
    client = bigquery.Client(project=PROJECT)
    articles = read_articles()

    # --- 記事まるごと（類似記事・記事探し用） ---
    article_rows = to_article_rows(articles)
    print(f"【2】記事の変換: {len(article_rows)}本")
    replace_table(client, article_rows, "blog_articles")
    print("【3】blog_articles を入れ替えました")
    print(f"【4】記事ベクトル追加: {run_dml(client, VECTORIZE_NEW_ARTICLES_SQL)}本")

    # --- 段落（記事の中身を探す用） ---
    chunk_rows = to_chunk_rows(articles)
    print(f"【5】段落の変換: {len(chunk_rows)}個")
    replace_table(client, chunk_rows, "blog_chunks")
    print("【6】blog_chunks を入れ替えました")
    print(f"【7】古くなった段落ベクトルを削除: {run_dml(client, DELETE_STALE_CHUNK_VECTORS_SQL)}個")
    print(f"【8】段落ベクトル追加: {run_dml(client, VECTORIZE_NEW_CHUNKS_SQL)}個")


if __name__ == "__main__":
    main()
