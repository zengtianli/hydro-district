"""FastAPI wrapper for hydro-district — unchanged Python core, no Streamlit.

Run:
    uv run uvicorn api:app --host 127.0.0.1 --port 8616 --reload
"""
from __future__ import annotations

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

# --- shared helpers (see ~/Dev/devtools/lib/hydro_api_helpers.py) ---
for _p in [Path.home() / "Dev/devtools/lib", Path("/var/www/devtools/lib")]:
    if _p.exists():
        sys.path.insert(0, str(_p))
        break
from hydro_api_helpers import (  # noqa: E402
    build_json_response,
    cors_origins,
    preview_zip_files,
    read_text_head,
)

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.district.scheduler import DistrictScheduler  # noqa: E402

app = FastAPI(title="hydro-district-api", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins("hydro-district", 3116),
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


def _run_district_full(zip_bytes: bytes, with_previews: bool = True) -> dict:
    """Full pipeline that also exposes output-file previews and metadata.

    Returns a dict with `preview` / `meta` / `results` / `outputFiles` / `zipBase64`
    when `with_previews=True`, plus `_zip_bytes` / `_summary` for internal reuse.
    """
    started = time.perf_counter()
    try:
        preview_payload = preview_zip_files(zip_bytes)
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, f"上传文件不是有效 ZIP: {exc}")

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
                results_payload[key] = read_text_head(f, lines=PREVIEW_LIMIT)

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if not with_previews:
            # Internal reuse path for the binary endpoint.
            return {"_zip_bytes": zip_bytes_out, "_summary": summary}

        return build_json_response(
            preview=preview_payload,
            meta={
                "districtsProcessed": summary["districts_processed"],
                "totalDemand": summary["total_water_demand"],
                "totalSupply": summary["total_water_supply"],
                "totalShortage": summary["total_shortage"],
                "fileCount": summary["file_count"],
                "elapsedMs": elapsed_ms,
            },
            results=results_payload,
            zip_bytes=zip_bytes_out,
            extras={"outputFiles": output_files_meta},
        )


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
    payload = _run_district_full(content, with_previews=False)
    zip_bytes = payload["_zip_bytes"]
    summary = payload["_summary"]
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
