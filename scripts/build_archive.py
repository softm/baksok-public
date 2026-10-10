#!/usr/bin/env python3
"""Rebuild the public archive exclusively from the checked-in zip/ inbox."""

from __future__ import annotations

import hashlib
import html
import json
import shutil
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "zip"
OUTPUT = ROOT / "records"
IGNORED = {".DS_Store", "Thumbs.db", "__MACOSX"}

RECORDS = {
    "2025_서해박속낙지_전면유리_박배경_디자인자료": {
        "slug": "2025-front-window-design",
        "date": "2025",
        "title": "서해박속낙지 전면 유리 박 배경 디자인 자료",
        "category": "디자인",
    },
    "20260809_서해박속낙지_여름휴업_안내문_채팅정리": {
        "slug": "20260809-summer-closure-notice",
        "date": "2026-08-09",
        "title": "서해박속낙지 여름 휴업 안내문",
        "category": "운영 안내",
    },
    "20260909_서해박속낙지_이가구_가스설비_사진포함": {
        "slug": "20260909-furniture-gas-equipment",
        "date": "2026-09-09",
        "title": "서해박속낙지 이가구·가스 설비 자료",
        "category": "시설·인테리어",
    },
    "20260911_서해박속낙지_RIR4000S_배송_배포_통합정리_모든이미지": {
        "slug": "20260911-rir4000s-delivery",
        "date": "2026-09-11",
        "title": "서해박속낙지 RIR4000S 배송 통합 기록",
        "category": "시설·인테리어",
    },
    "20260918_서해박속낙지_가스렌지_식탁설치_가스재연결": {
        "slug": "20260918-gas-stove-table-installation",
        "date": "2026-09-18",
        "title": "서해박속낙지 가스레인지·식탁 설치 및 가스 재연결",
        "category": "시설·인테리어",
    },
    "20260929_서해박속낙지_광진소파_스툴_제작완료": {
        "slug": "20260929-gwangjin-sofa-stool",
        "date": "2026-09-29",
        "title": "서해박속낙지 광진소파 스툴 제작 완료",
        "category": "시설·인테리어",
    },
    "20261005_서해박속낙지_명함디자인_정리_모든이미지포함": {
        "slug": "20261005-business-card-design",
        "date": "2026-10-05",
        "title": "서해박속낙지 명함 디자인 정리",
        "category": "디자인",
    },
}


def normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def source_files(root: Path):
    for path in sorted(root.rglob("*"), key=lambda item: normalized(item.as_posix())):
        relative = path.relative_to(root)
        if any(part in IGNORED or part.startswith("._") for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed: {relative}")
        if path.is_file():
            yield path


def tree_digest(root: Path) -> str:
    result = hashlib.sha256()
    for path in source_files(root):
        relative = normalized(path.relative_to(root).as_posix())
        result.update(relative.encode("utf-8"))
        result.update(b"\0")
        result.update(digest(path).encode("ascii"))
        result.update(b"\n")
    return result.hexdigest()


def copy_source(source: Path, target: Path) -> None:
    target.mkdir(parents=True)
    for path in source_files(source):
        relative = path.relative_to(source)
        if relative.as_posix() == "archive-manifest.json":
            relative = Path("source-archive-manifest.json")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def choose_entry(source: Path) -> Path:
    direct = source / "index.html"
    if direct.is_file():
        return direct
    candidates = [path for path in source_files(source) if path.suffix.lower() in {".html", ".htm"}]
    if not candidates:
        raise ValueError(f"HTML entry is missing: {source.name}")
    return max(candidates, key=lambda path: path.stat().st_size)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_record(source: Path, metadata: dict[str, str]) -> dict[str, object]:
    target = OUTPUT / metadata["slug"]
    entry = choose_entry(source)
    copy_source(source, target)
    entry_relative = entry.relative_to(source)
    if entry_relative.as_posix() != "index.html":
        shutil.copy2(entry, target / "index.html")

    if digest(entry) != digest(target / "index.html"):
        raise ValueError(f"entry HTML changed while copying: {source.name}")

    files = [
        {
            "path": path.relative_to(target).as_posix(),
            "size": path.stat().st_size,
            "sha256": digest(path),
        }
        for path in source_files(target)
        if path.name != "archive-manifest.json"
    ]
    manifest = {
        "schemaVersion": 3,
        "visibility": "public",
        "id": metadata["slug"],
        "slug": metadata["slug"],
        "date": metadata["date"],
        "title": metadata["title"],
        "category": metadata["category"],
        "input": source.name,
        "inputKind": "folder",
        "inputTreeSha256": tree_digest(source),
        "entrySource": entry_relative.as_posix(),
        "entrySha256": digest(entry),
        "files": files,
    }
    write_json(target / "archive-manifest.json", manifest)
    return manifest


def build_home(records: list[dict[str, object]]) -> None:
    cards = "".join(
        '<a class="card" href="records/{slug}/"><span class="date">{date} · {category}</span>'
        "<h2>{title}</h2><div class=\"meta\">원본 자료 {count}개</div></a>".format(
            slug=html.escape(str(record["slug"]), quote=True),
            date=html.escape(str(record["date"])),
            category=html.escape(str(record["category"])),
            title=html.escape(str(record["title"])),
            count=len(record["files"]),
        )
        for record in reversed(records)
    )
    document = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="서해박속낙지 공개 기록 아카이브"><link rel="canonical" href="https://softm.github.io/baksok-public/"><title>서해박속낙지 아카이브</title><style>body{{margin:0;background:#f4f1ed;color:#251f1b;font-family:Pretendard,"Noto Sans KR","Malgun Gothic",sans-serif}}.wrap{{width:min(980px,calc(100% - 28px));margin:auto;padding:42px 0}}h1{{font-size:clamp(2.2rem,6vw,4.8rem);letter-spacing:-.05em;margin:0 0 12px}}.lead,.meta{{color:#756b64}}.card{{display:block;margin-top:20px;padding:24px;border:1px solid #ded7d0;border-radius:20px;background:#fffdf9;color:inherit;text-decoration:none}}.card:hover{{border-color:#99735c}}.date{{font-size:.84rem;font-weight:800;color:#925f3b}}.card h2{{margin:8px 0 10px;font-size:1.35rem}}.links{{margin-top:24px}}a{{color:#4b382d;text-underline-offset:3px}}</style></head><body><main class="wrap"><p class="date">SOFTM / PUBLIC ARCHIVE</p><h1>서해박속낙지</h1><p class="lead">공개 프로젝트의 <code>zip/</code> 자료만으로 다시 구성한 기록입니다.</p>{cards}<p class="links"><a href="https://softm.github.io/projects/baksok/">SOFTM 프로젝트 홈</a> · <a href="https://github.com/softm/baksok-public">GitHub 저장소</a></p></main></body></html>'''
    (ROOT / "index.html").write_text(document, encoding="utf-8")


def main() -> None:
    available = {
        normalized(path.name): path
        for path in INBOX.iterdir()
        if path.is_dir() and path.name not in IGNORED
    }
    expected = set(RECORDS)
    if set(available) != expected:
        missing = sorted(expected - set(available))
        unexpected = sorted(set(available) - expected)
        raise SystemExit(f"zip/ inputs do not match configuration; missing={missing}, unexpected={unexpected}")

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()

    records = [build_record(available[name], RECORDS[name]) for name in RECORDS]
    build_home(records)
    write_json(OUTPUT / "index.json", {"schemaVersion": 1, "records": records})
    print(json.dumps({"visibility": "public", "records": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
