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

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

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


def _run_district(zip_bytes: bytes) -> tuple[bytes, dict]:
    """Port of app.py's "开始计算" button handler without Streamlit coupling.

    Input: ZIP bytes containing `input_*.txt` + `static_*.txt`.
    Output: (result_zip_bytes, summary_dict).
    """
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

        # Bundle every file produced under output_dir into a new ZIP.
        result_zip = io.BytesIO()
        file_count = 0
        with zipfile.ZipFile(result_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(output_dir.rglob("*")):
                if f.is_file():
                    z.write(f, arcname=f.relative_to(output_dir))
                    file_count += 1
        if file_count == 0:
            raise HTTPException(500, "计算未产生任何输出文件")

        summary = {
            "file_count": file_count,
            "districts_processed": (results or {}).get("districts_processed", 0),
            "total_water_demand": (results or {}).get("total_water_demand", 0),
            "total_water_supply": (results or {}).get("total_water_supply", 0),
            "total_shortage": (results or {}).get("total_shortage", 0),
        }
        return result_zip.getvalue(), summary


@app.post("/api/compute")
async def compute(file: UploadFile = File(..., description="ZIP: input_*.txt + static_*.txt")) -> Response:
    content = await file.read()
    if not content:
        raise HTTPException(400, "上传文件为空")
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
