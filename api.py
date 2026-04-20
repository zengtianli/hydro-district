"""FastAPI wrapper for hydro-district — unchanged Python core, no Streamlit.

Run:
    uv run uvicorn api:app --host 127.0.0.1 --port 8616 --reload
"""
from __future__ import annotations

import base64
import io
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.district.scheduler import DistrictScheduler  # noqa: E402

app = FastAPI(title="hydro-district-api", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3116",
        "http://127.0.0.1:3116",
        "https://hydro-district.tianlizeng.cloud",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta")
def meta_info() -> dict:
    return {
        "name": "district",
        "title": "河区调度",
        "icon": "🗺️",
        "description": "19河区逐日水资源供需平衡调度",
        "version": "1.0.0",
    }


def _preview_input_zip(zip_bytes: bytes) -> dict:
    """Parse the uploaded ZIP's file listing for the Step 2 preview card.

    Groups entries into `input` / `static` / `other` based on filename prefix.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            infos = [i for i in z.infolist() if not i.is_dir()]
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, f"上传文件不是有效 ZIP: {exc}")

    files = []
    total_size = 0
    for info in infos:
        name = Path(info.filename).name
        if name.startswith("input_"):
            group = "input"
        elif name.startswith("static_"):
            group = "static"
        else:
            group = "other"
        files.append(
            {
                "name": info.filename,
                "basename": name,
                "size": info.file_size,
                "group": group,
            }
        )
        total_size += info.file_size

    files.sort(key=lambda f: (f["group"] != "input", f["group"] != "static", f["name"]))
    return {
        "inputFiles": files,
        "fileCount": len(files),
        "totalSize": total_size,
    }


def _read_text_head(path: Path, limit: int = 50) -> dict:
    """Read a whitespace-delimited text file and return head rows (columns inferred)."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover — best-effort preview
        return {"columns": ["error"], "rows": [[str(exc)]], "totalRows": 0}

    lines = [ln for ln in raw.splitlines() if ln.strip()]
    total = len(lines)
    if total == 0:
        return {"columns": [], "rows": [], "totalRows": 0}

    # 首行做 header（若全是数字/日期样式则合成 col1..colN）
    first_cells = lines[0].split()
    header_is_text = any(
        (not c.replace(".", "").replace("-", "").replace(":", "").isdigit())
        and not c.replace("/", "").isdigit()
        for c in first_cells
    )
    if header_is_text and len(first_cells) >= 2:
        columns = first_cells
        body = lines[1:]
        total_rows = total - 1
    else:
        columns = [f"col{i + 1}" for i in range(len(first_cells))]
        body = lines
        total_rows = total

    sliced = body[:limit]
    rows: list[list[str]] = []
    width = len(columns)
    for ln in sliced:
        cells = ln.split()
        if len(cells) < width:
            cells = cells + [""] * (width - len(cells))
        elif len(cells) > width:
            # 合并溢出列到最后一格
            cells = cells[: width - 1] + [" ".join(cells[width - 1 :])]
        rows.append(cells)
    return {"columns": columns, "rows": rows, "totalRows": total_rows}


def _run_district(zip_bytes: bytes) -> tuple[bytes, dict]:
    """Port of app.py's "开始计算" button handler without Streamlit coupling.

    Input: ZIP bytes containing `input_*.txt` + `static_*.txt`.
    Output: (result_zip_bytes, summary_dict).
    """
    payload = _run_district_full(zip_bytes, with_previews=False)
    return payload["_zip_bytes"], payload["_summary"]


def _run_district_full(zip_bytes: bytes, with_previews: bool = True) -> dict:
    """Full pipeline that also exposes output-file previews and metadata.

    Returns a dict with `preview` / `meta` / `results` / `outputFiles` / `zipBase64`
    when `with_previews=True`, plus `_zip_bytes` / `_summary` for internal reuse.
    """
    started = time.perf_counter()
    preview_payload = _preview_input_zip(zip_bytes)

    with tempfile.TemporaryDirectory() as tmpdir_raw:
        tmpdir = Path(tmpdir_raw)
        data_dir = tmpdir / "input"
        output_dir = tmpdir / "output"
        data_dir.mkdir()
        output_dir.mkdir()

        # Extract the uploaded ZIP.
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                z.extractall(data_dir)
        except zipfile.BadZipFile as exc:
            raise HTTPException(400, f"上传文件不是有效 ZIP: {exc}")

        # Mirror app.py's nested-folder detection: sometimes users zip a folder
        # that contains the txt files instead of zipping files directly.
        resolved_data_dir = data_dir
        if not any(data_dir.glob("input_*.txt")):
            for sub in data_dir.iterdir():
                if sub.is_dir() and any(sub.glob("input_*.txt")):
                    resolved_data_dir = sub
                    break
        if not any(resolved_data_dir.glob("input_*.txt")):
            raise HTTPException(400, "ZIP 内未找到 input_*.txt 文件")

        scheduler = DistrictScheduler(
            data_path=resolved_data_dir,
            output_path=output_dir,
        )
        try:
            results = scheduler.run()
        except Exception as exc:
            import traceback
            raise HTTPException(
                500,
                f"计算失败: {type(exc).__name__}: {exc}\n{traceback.format_exc()[-800:]}",
            )

        if isinstance(results, dict) and results.get("status") not in (None, "success"):
            raise HTTPException(500, f"计算失败: {results.get('message', '未知错误')}")

        # Collect all output files, then bundle into a ZIP.
        output_files_meta: list[dict] = []
        all_output_paths: list[Path] = []
        for f in sorted(output_dir.rglob("*")):
            if f.is_file():
                all_output_paths.append(f)
                rel = f.relative_to(output_dir)
                output_files_meta.append(
                    {
                        "name": rel.as_posix(),
                        "basename": f.name,
                        "size": f.stat().st_size,
                        "subdir": rel.parent.as_posix() if rel.parent.as_posix() != "." else "",
                    }
                )

        if not all_output_paths:
            raise HTTPException(500, "计算未产生任何输出文件")

        result_zip = io.BytesIO()
        with zipfile.ZipFile(result_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for f in all_output_paths:
                z.write(f, arcname=f.relative_to(output_dir))
        zip_bytes_out = result_zip.getvalue()

        summary = {
            "file_count": len(all_output_paths),
            "districts_processed": (results or {}).get("districts_processed", 0),
            "total_water_demand": (results or {}).get("total_water_demand", 0),
            "total_water_supply": (results or {}).get("total_water_supply", 0),
            "total_shortage": (results or {}).get("total_shortage", 0),
        }

        # Build per-file previews for the "main" hq output txts (top-level).
        results_payload: dict[str, dict] = {}
        if with_previews:
            PREVIEW_LIMIT = 50
            # 主要 output — 顶层的 output_hq_*.txt / output_sn_*.txt
            for f in all_output_paths:
                rel = f.relative_to(output_dir)
                if rel.parent.as_posix() != ".":
                    continue
                name = rel.name
                if not (name.startswith("output_hq_") or name.startswith("output_sn_")):
                    continue
                if not name.endswith(".txt"):
                    continue
                key = name[: -len(".txt")]
                results_payload[key] = _read_text_head(f, limit=PREVIEW_LIMIT)

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if not with_previews:
            # Internal reuse path for the binary endpoint.
            return {"_zip_bytes": zip_bytes_out, "_summary": summary}

        return {
            "preview": preview_payload,
            "meta": {
                "districtsProcessed": summary["districts_processed"],
                "totalDemand": summary["total_water_demand"],
                "totalSupply": summary["total_water_supply"],
                "totalShortage": summary["total_shortage"],
                "fileCount": summary["file_count"],
                "elapsedMs": elapsed_ms,
                "zipBytes": len(zip_bytes_out),
            },
            "results": results_payload,
            "outputFiles": output_files_meta,
            "zipBase64": base64.b64encode(zip_bytes_out).decode("ascii"),
        }


@app.post("/api/compute")
async def compute(
    file: UploadFile = File(..., description="ZIP: input_*.txt + static_*.txt"),
    format: str = Form("zip", description="zip (binary) | json (preview+meta+results+base64)"),
) -> Response:
    content = await file.read()
    if not content:
        raise HTTPException(400, "上传文件为空")
    if format == "json":
        payload = _run_district_full(content, with_previews=True)
        return JSONResponse(content=payload)
    t0 = time.perf_counter()
    zip_bytes, summary = _run_district(content)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    # HTTP headers must be latin-1; summary values are numeric but wrap through
    # quote() for consistency with other hydro-* APIs (and to avoid surprises
    # if any value ever carries CJK metadata in the future).
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="district_result.zip"',
            "X-File-Count": str(summary["file_count"]),
            "X-Districts-Processed": str(summary["districts_processed"]),
            "X-Total-Demand": quote(str(summary["total_water_demand"])),
            "X-Total-Supply": quote(str(summary["total_water_supply"])),
            "X-Total-Shortage": quote(str(summary["total_shortage"])),
            "X-Elapsed-Ms": str(elapsed_ms),
            "Access-Control-Expose-Headers": (
                "X-File-Count, X-Districts-Processed, X-Total-Demand, "
                "X-Total-Supply, X-Total-Shortage, X-Elapsed-Ms, Content-Disposition"
            ),
        },
    )


@app.get("/api/sample")
def sample_zip() -> Response:
    """Return the bundled sample inputs zipped, for one-click demo from the web UI."""
    sample_dir = PROJECT_ROOT / "data" / "sample"
    if not sample_dir.exists():
        raise HTTPException(404, "示例输入目录不存在")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(sample_dir.glob("input_*.txt")):
            z.write(f, arcname=f.name)
        for f in sorted(sample_dir.glob("static_*.txt")):
            z.write(f, arcname=f.name)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="sample_input.zip"'},
    )
