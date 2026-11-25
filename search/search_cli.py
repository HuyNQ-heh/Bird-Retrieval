"""Local HTML search results, evidence export and held-out evaluation."""

import base64
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
import io
import json
from pathlib import Path
import random
import sys
from uuid import uuid4

from PIL import Image

from indexing.image_io import load_rgb
from sql.database import ROOT, read_gallery
from search.service import build_index, search_query


def output_folder(command):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = ROOT / "runs" / f"{command}-{stamp}-{uuid4().hex[:6]}"
    folder.mkdir(parents=True)
    return folder


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def describe(records, rejected, index, excluded):
    counts = index.group_counts()
    return dict(registered=len(records) + len(rejected), invalid_count=len(rejected),
                invalid_rows=rejected, excluded_ids=sorted(excluded), candidates=len(index.ids),
                active_dimensions=sum(counts),
                active_by_group=dict(zip(("color", "texture", "shape"), counts)))


def image_tag(image, alt, size):
    image = image.copy()
    image.thumbnail((size, size), Image.Resampling.LANCZOS if image.mode == "RGB" else Image.Resampling.NEAREST)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f'<img alt="{escape(alt, quote=True)}" src="data:image/png;base64,{data}">'


def write_html(path, query, report):
    panels = []
    for title, pixels in (("Ảnh đầu vào", query.original), ("Mặt nạ trên ảnh gốc", query.mask),
                          ("Ảnh chuẩn hóa · 224 × 224", query.normalized)):
        panels.append(f'<figure>{image_tag(Image.fromarray(pixels), title, 480)}<figcaption>{title}</figcaption></figure>')
    cards, table_rows = [], []
    for row in report["results"]:
        rank, distance = row["rank"], row["distance"]
        filename = escape(row["filename"])
        try:
            thumbnail = image_tag(load_rgb(ROOT / row["image_path"]), row["species"], 224)
        except OSError:
            thumbnail = '<span>Thiếu tệp ảnh hiển thị</span>'
        cards.append(f'<figure>{thumbnail}<figcaption><b>{rank}. {escape(row["species"])}</b>'
                     f'<br>ID {row["image_id"]} · d = {distance:.6f}</figcaption></figure>')
        fields = [str(rank), str(row["image_id"]), filename, escape(row["species"]),
                  "Gốc" if row["orientation"] == "original" else "Lật ngang",
                  *(f'{row[k]:.9f}' for k in ("S_mau", "S_ket_cau", "S_hinh_dang", "distance"))]
        table_rows.append("<tr>" + "".join(f"<td>{field}</td>" for field in fields) + "</tr>")
    example = "Kho so sánh không có ứng viên hợp lệ."
    if report["results"]:
        first = report["results"][0]
        terms = " + ".join(repr(first[k]) for k in ("S_mau", "S_ket_cau", "S_hinh_dang"))
        example = f'Hạng 1 · <code>d = √({terms}) ≈ {first["distance"]!r}</code>'
    audit = report["gallery"]
    details = (f'{audit["candidates"]} ảnh kho · {audit["active_dimensions"]}/678 chiều dùng để so sánh'
               f' · {audit["invalid_count"]} bản ghi lỗi')
    if audit["excluded_ids"]:
        details += " · ID giữ ngoài kho: " + ", ".join(map(str, audit["excluded_ids"]))
    metrics = ""
    if "precision_at_5" in report:
        metrics = (f'<p>Loài truy vấn: {escape(report["query_species"])}. '
                   f'{report["same_species"]}/5 ảnh cùng loài · Precision@5 = {report["precision_at_5"]:.2f}.</p>')
    path.write_text(f"""<!doctype html><html lang="vi"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Kết quả tìm kiếm ảnh chim</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f6f6ef;color:#19291d;font:16px/1.5 system-ui,sans-serif}}
main{{max-width:1160px;margin:auto;padding:32px 20px}}h1,h2{{font-family:Georgia,serif;line-height:1.18}}
h1{{font-size:clamp(28px,4vw,48px);overflow-wrap:anywhere}}h2{{margin-top:32px}}
section{{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px}}
figure{{margin:0;background:white;border:1px solid #ced7cc;border-radius:8px;overflow:hidden}}
img{{display:block;width:100%;height:180px;object-fit:contain;background:#e8ede7}}figcaption{{padding:10px 12px}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:8px;text-align:left;border-bottom:1px solid #ced7cc}}
th{{background:#e0e8da}}code{{overflow-wrap:anywhere}}p{{margin:10px 0}}</style>
<main><h1>{escape(Path(report["query"]).name)}</h1><p>{details}</p><section>{''.join(panels)}</section>
<h2>Ảnh gần nhất</h2><section>{''.join(cards)}</section>{metrics}
<h2>Khoảng cách theo từng ảnh</h2><div class="scroll"><table><thead><tr><th>Hạng</th><th>ID</th><th>Tệp</th><th>Loài</th>
<th>Hướng truy vấn</th><th>S màu</th><th>S kết cấu</th><th>S hình dạng</th><th>Euclid</th></tr></thead>
<tbody>{''.join(table_rows)}</tbody></table></div><p>{example}</p>
</main></html>""", encoding="utf-8")


def search(args):
    records, rejected = read_gallery()
    paths = [p.resolve() for p in args.image]
    if args.species and len(args.species) != len(paths):
        raise ValueError("Supply one --species per image, or omit all labels")
    query_paths = set(paths)
    excluded = {i for i, (path, _, _) in records.items() if (ROOT / path).resolve() in query_paths}
    for i in args.exclude_id:
        if i not in records:
            raise ValueError(f"Unknown or invalid --exclude-id {i}")
        excluded.add(i)
    index = build_index(records, excluded)
    audit = describe(records, rejected, index, excluded)
    folder = output_folder("search")
    save_json(folder / "gallery.json", audit)
    print(f'Gallery: {len(index.ids)} candidates, {len(rejected)} invalid. Audit: {folder / "gallery.json"}')
    failures = 0
    for n, path in enumerate(paths, 1):
        try:
            query, hits = search_query(path, records, index)
        except (ValueError, OSError, RuntimeError) as exc:
            failures += 1
            print(f"{path}: {exc}", file=sys.stderr)
            continue
        report = dict(query=str(path), gallery=audit, results=hits)
        if args.species:
            species = args.species[n-1]
            same = sum(hit["species"] == species for hit in hits)
            report.update(query_species=species, same_species=same, precision_at_5=same / 5)
        result = folder / f"query-{n}.html"
        write_html(result, query, report)
        if args.evidence:
            save_json(result.with_suffix(".json"), report)
        print(result)
    return int(failures > 0)


def _select_queries(records, per_species, seed):
    groups = defaultdict(list)
    for i, (_, species, _) in records.items():
        groups[species].append(i)
    pools = [sorted(groups[s]) for s in sorted(groups) if len(groups[s]) >= 2]
    rng = random.Random(seed)
    held = []
    # Sampling in rounds preserves the original one-query-per-species split.
    for _ in range(min(per_species, max(map(len, pools), default=1) - 1)):
        for pool in pools:
            if len(pool) > 1:
                held.append(pool.pop(rng.randrange(len(pool))))
    return held


def _write_evaluation_table(path, stats, audit, rows):
    n = len(rows)
    def fraction(count, total):
        return f"{count}/{total} ({count / total:.2%})".replace(".", ",")

    lines = [
        "# Đánh giá tìm kiếm ảnh chim",
        "",
        f"Seed {stats['seed']}. Tập truy vấn gồm {n} ảnh thuộc {len(set(r['species'] for r in rows))} loài. "
        f"Kho gồm {audit['candidates']} ảnh sau khi loại toàn bộ ID truy vấn, trước khi tính min/max.",
        "",
        "| Truy vấn | Xử lý thành công | Đúng loài ở hạng 1 | Có ảnh đúng loài trong top 5 | Precision@5 trung bình |",
        "|---:|---:|---:|---:|---:|",
        f"| {n} | {stats['successful']}/{n} | {fraction(stats['top1_correct'], n)} | "
        f"{fraction(stats['queries_with_hit'], n)} | {fraction(stats['same_species_hits'], 5 * n)} |",
        "",
        "Precision@5 của mỗi truy vấn bằng số ảnh cùng loài trong năm kết quả đầu chia cho 5. "
        "Truy vấn lỗi nhận 0 và vẫn tính vào mẫu số.",
        "",
        "## Kết quả từng ảnh",
        "",
        "| ID truy vấn | Tệp | Loài | Hạng đúng loài | Số ảnh đúng / 5 | Precision@5 |",
        "|---:|---|---|---|---:|---:|",
    ]
    for row in rows:
        ranks = [str(hit["rank"]) for hit in row.get("results", []) if hit["species"] == row["species"]]
        detail = "Lỗi xử lý" if "error" in row else ", ".join(ranks) or "—"
        lines.append(f"| {row['image_id']} | {Path(row['image_path']).name} | {row['species']} | "
                     f"{detail} | {row['same_species']}/5 | {row['precision_at_5']:.0%} |")
    lines.extend(["", "[Top 5, khoảng cách và chi tiết lỗi của từng ảnh](evaluation.json)"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate(args):
    records, rejected = read_gallery()
    held = _select_queries(records, args.per_species, args.seed)
    if not held:
        raise ValueError("Evaluation needs a species with at least two images")
    index = build_index(records, set(held))
    audit = describe(records, rejected, index, held)
    folder = output_folder("evaluate")
    rows, hits_total = [], 0
    for i in held:
        source, species, _ = records[i]
        row = dict(image_id=i, image_path=source, species=species)
        try:
            _, hits = search_query(ROOT / source, records, index)
            same = sum(hit["species"] == species for hit in hits)
            hits_total += same
            row.update(results=hits, same_species=same, precision_at_5=same / 5)
        except (ValueError, OSError, RuntimeError) as exc:
            row.update(error=str(exc), same_species=0, precision_at_5=0.)
        rows.append(row)
    errors = sum("error" in row for row in rows)
    top1 = sum(1 for r in rows if r.get("results") and r["results"][0]["species"] == r["species"])
    stats = dict(seed=args.seed, per_species=args.per_species, queries=len(held), successful=len(held)-errors, errors=errors,
                 top1_correct=top1, queries_with_hit=sum(r["same_species"] > 0 for r in rows),
                 same_species_hits=hits_total, mean_precision_at_5=hits_total/(5*len(held)),
                 hits_distribution=dict(sorted(Counter(r["same_species"] for r in rows).items())))
    result = folder / "evaluation.json"
    save_json(result, dict(summary=stats, gallery=audit, queries=rows))
    table = folder / "summary.md"
    _write_evaluation_table(table, stats, audit, rows)
    print(json.dumps(stats), result, table, sep="\n")
    return int(errors > 0)
