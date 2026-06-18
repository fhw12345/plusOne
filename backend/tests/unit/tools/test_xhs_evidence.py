"""Unit tests for importing crawled XHS facts into structured evidence rows."""

from __future__ import annotations

from plus_one.scripts.xhs_evidence_import import build_evidence_rows, load_local_cache_rows


def test_build_evidence_rows_extracts_posts_images_and_matches() -> None:
    rows = [
        {
            "query": "东京 AFURI 美食推荐",
            "candidate": "Afuri",
            "payload": [
                {
                    "id": "note-1",
                    "url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=abc",
                    "title": "AFURI 阿夫利柚子拉面",
                    "body": "东京本地朋友推荐。",
                    "author": "alice",
                    "images": ["/media/xhs/a.webp", "/media/xhs/b.webp"],
                    "source_images": ["https://sns-webpic-qc.xhscdn.com/a!webp"],
                    "cached_images": [
                        {
                            "source_url": "https://sns-webpic-qc.xhscdn.com/a!webp",
                            "url": "/media/xhs/a.webp",
                            "bytes": 123,
                            "content_type": "image/webp",
                        }
                    ],
                    "xhs_relevance_score": 0.75,
                    "xhs_relevance_terms": ["AFURI", "阿夫利"],
                    "xhs_quality_version": 4,
                    "xhs_candidate": "Afuri",
                    "xhs_query": "东京 AFURI 美食推荐",
                    "xhs_authenticity_score": 0.9,
                    "xhs_authenticity_reasons": ["grounded"],
                }
            ],
        }
    ]

    evidence = build_evidence_rows(rows)

    assert [post.note_id for post in evidence.posts] == ["note-1"]
    assert evidence.posts[0].canonical_url == "https://www.xiaohongshu.com/explore/note-1"
    assert evidence.posts[0].raw_payload["title"] == "AFURI 阿夫利柚子拉面"
    assert [(image.note_id, image.local_url, image.byte_count) for image in evidence.images] == [
        ("note-1", "/media/xhs/a.webp", 123),
        ("note-1", "/media/xhs/b.webp", None),
    ]
    assert evidence.matches[0].candidate == "Afuri"
    assert evidence.matches[0].query == "东京 AFURI 美食推荐"
    assert evidence.matches[0].relevance_score == 0.75


def test_build_evidence_rows_dedupes_same_note_across_queries() -> None:
    rows = [
        {
            "query": "东京 AFURI 美食推荐",
            "candidate": "Afuri",
            "payload": [
                {
                    "id": "note-1",
                    "url": "https://www.xiaohongshu.com/search_result/note-1?xsec_token=abc",
                    "title": "AFURI",
                    "images": ["/media/xhs/a.webp"],
                    "xhs_relevance_score": 0.75,
                    "xhs_relevance_terms": ["AFURI"],
                    "xhs_quality_version": 4,
                    "xhs_candidate": "Afuri",
                    "xhs_query": "东京 AFURI 美食推荐",
                }
            ],
        },
        {
            "query": "东京 阿夫利 真实体验",
            "candidate": "Afuri",
            "payload": [
                {
                    "id": "note-1",
                    "url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=abc",
                    "title": "AFURI updated",
                    "images": ["/media/xhs/a.webp"],
                    "xhs_relevance_score": 1.0,
                    "xhs_relevance_terms": ["阿夫利"],
                    "xhs_quality_version": 4,
                    "xhs_candidate": "Afuri",
                    "xhs_query": "东京 阿夫利 真实体验",
                }
            ],
        },
    ]

    evidence = build_evidence_rows(rows)

    assert len(evidence.posts) == 1
    assert evidence.posts[0].canonical_url == "https://www.xiaohongshu.com/explore/note-1"
    assert len(evidence.images) == 1
    assert {(match.candidate, match.query, match.note_id) for match in evidence.matches} == {
        ("Afuri", "东京 AFURI 美食推荐", "note-1"),
        ("Afuri", "东京 阿夫利 真实体验", "note-1"),
    }


def test_build_evidence_rows_skips_unchecked_candidate_matches() -> None:
    rows = [
        {
            "query": "广州 宝华园 美食推荐",
            "candidate": "Baohuayuan Sampan Congee (宝华园)",
            "payload": [
                {
                    "id": "weak-note",
                    "url": "https://www.xiaohongshu.com/explore/weak-note?xsec_token=abc",
                    "title": "广州泛化早茶推荐",
                    "images": ["/media/xhs/a.webp"],
                }
            ],
        }
    ]

    evidence = build_evidence_rows(rows)

    assert [post.note_id for post in evidence.posts] == ["weak-note"]
    assert [(image.note_id, image.local_url) for image in evidence.images] == [
        ("weak-note", "/media/xhs/a.webp")
    ]
    assert evidence.matches == []


def test_build_evidence_rows_skips_stale_quality_fields_from_other_candidate() -> None:
    rows = [
        {
            "query": "广州 永记牛杂 美食推荐",
            "candidate": "Yong Qi Beef Offal (永记牛杂)",
            "payload": [
                {
                    "id": "afuri-note",
                    "url": "https://www.xiaohongshu.com/explore/afuri-note?xsec_token=abc",
                    "title": "东京 AFURI 拉面真实体验",
                    "images": ["/media/xhs/a.webp"],
                    "xhs_candidate": "Afuri Ebisu",
                    "xhs_query": "东京 AFURI 美食推荐",
                    "xhs_relevance_score": 0.75,
                    "xhs_relevance_terms": ["AFURI"],
                    "xhs_quality_version": 4,
                }
            ],
        }
    ]

    evidence = build_evidence_rows(rows)

    assert [post.note_id for post in evidence.posts] == ["afuri-note"]
    assert [(image.note_id, image.local_url) for image in evidence.images] == [
        ("afuri-note", "/media/xhs/a.webp")
    ]
    assert evidence.matches == []


def test_load_local_cache_rows_skips_malformed_jsonl(tmp_path) -> None:
    cache_file = tmp_path / "xhs.jsonl"
    cache_file.write_text(
        '{"query":"ok","candidate":"Afuri","payload":[]}\n'
        '{"query":"bad","candidate":"Afuri","payload":[{"body":"broken\x01text"}]}\n'
        '{"query":"ok2","candidate":"Afuri","payload":[]}\n',
        encoding="utf-8",
    )

    rows = load_local_cache_rows(cache_file)

    assert [row["query"] for row in rows] == ["ok", "ok2"]
