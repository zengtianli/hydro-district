#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
浙东河区调度模型 - Streamlit Web 界面

启动方式：streamlit run app.py
"""
import streamlit as st
import pandas as pd
import io
import sys
import tempfile
import shutil
import zipfile
from pathlib import Path

# 项目目录
REPO_ROOT = Path(__file__).resolve().parent
DATA_SAMPLE_DIR = REPO_ROOT / 'data' / 'sample'
DATA_OUTPUT_DIR = REPO_ROOT / 'data' / 'output'

from src.district.scheduler import DistrictScheduler, DISTRICT_NAME_MAPPING, SLUICE_NAME_MAPPING
from src.common.st_utils import page_config, footer

# 页面配置
page_config("河区调度 - Hydro Toolkit")

# 自定义样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1e88e5;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
    }
    .stProgress > div > div > div > div {
        background-color: #1e88e5;
    }
</style>
""", unsafe_allow_html=True)


def main():
    # 标题
    st.title("🗺️ 河区调度")
    st.caption("19个河区 · 6个分水枢纽 · 水资源科学调度")

    # 侧边栏
    with st.sidebar:
        st.header("📋 模型说明")
        st.markdown("""
        **覆盖范围**
        - 19个河区（余姚、慈溪、绍虞等）
        - 6个分水枢纽

        **核心功能**
        - 水平衡计算
        - 分水枢纽调度
        - 缺水评估

        **数据单位**
        - 万立方米(万m³)
        - 立方米每秒(m³/s)
        """)

        st.divider()

        # 下载示例数据
        st.subheader("📥 示例数据")
        if DATA_SAMPLE_DIR.exists():
            # 创建示例数据 ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in DATA_SAMPLE_DIR.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(DATA_SAMPLE_DIR)
                        zf.write(file_path, arcname)
            zip_buffer.seek(0)

            st.download_button(
                label="下载示例文件",
                data=zip_buffer,
                file_name="河区调度模型_示例数据.zip",
                mime="application/zip",
                use_container_width=True
            )

    # 主内容区
    # 数据源选择
    st.subheader("📂 数据源")

    data_source = st.radio(
        "选择数据来源",
        options=["sample", "upload"],
        format_func=lambda x: "使用示例数据" if x == "sample" else "上传自己的数据",
        horizontal=True
    )

    data_path = None
    temp_dir = None

    if data_source == "upload":
        uploaded_zip = st.file_uploader(
            "上传包含输入文件的ZIP压缩包",
            type="zip",
            help="ZIP包应包含所有 input_*.txt 和 static_*.txt 文件"
        )

        if uploaded_zip:
            # 解压到临时目录
            temp_dir = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # 查找实际数据目录（可能有嵌套）
            data_path = temp_dir
            for sub in temp_dir.iterdir():
                if sub.is_dir() and any(sub.glob('input_*.txt')):
                    data_path = sub
                    break

            st.success(f"✅ 已解压 {len(list(data_path.glob('*.txt')))} 个文件")
        else:
            st.info("👆 请上传包含输入文件的ZIP压缩包")
    else:
        data_path = DATA_SAMPLE_DIR
        if data_path.exists():
            file_count = len(list(data_path.glob('*.txt')))
            st.info(f"使用示例数据目录: {file_count} 个文件")
        else:
            st.error("示例数据目录不存在，请上传数据")
            data_path = None

    # 数据预览
    if data_path and data_path.exists():
        with st.expander("📊 数据预览", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**输入文件**")
                input_files = list(data_path.glob('input_*.txt'))
                for f in input_files[:5]:
                    st.text(f"📄 {f.name}")
                if len(input_files) > 5:
                    st.text(f"... 共 {len(input_files)} 个")

            with col2:
                st.markdown("**静态配置**")
                static_files = list(data_path.glob('static_*.txt'))
                for f in static_files:
                    st.text(f"📋 {f.name}")

            # 预览选中文件
            all_files = list(data_path.glob('*.txt'))
            if all_files:
                selected_file = st.selectbox(
                    "选择文件预览",
                    options=[f.name for f in all_files]
                )
                if selected_file:
                    file_path = data_path / selected_file
                    try:
                        df = pd.read_csv(file_path, sep='\t', nrows=10)
                        st.dataframe(df, use_container_width=True)
                    except Exception as e:
                        st.error(f"读取文件失败: {e}")

    st.divider()

    # 计算按钮
    st.subheader("🚀 运行计算")

    if data_path and data_path.exists():
        if st.button("开始计算", type="primary", use_container_width=True):
            # 确保输出目录存在
            DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            # 进度显示
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(step, total, message):
                progress_bar.progress(step / total)
                status_text.text(f"[{step}/{total}] {message}")

            with st.spinner("计算中..."):
                try:
                    # 创建调度器
                    scheduler = DistrictScheduler(
                        data_path=data_path,
                        output_path=DATA_OUTPUT_DIR
                    )

                    # 运行计算
                    results = scheduler.run(progress_callback=update_progress)

                    # 保存结果到 session
                    st.session_state['results'] = results
                    st.session_state['output_path'] = DATA_OUTPUT_DIR

                    if results.get('status') == 'success':
                        st.success("✅ 计算完成！")
                        st.balloons()
                    else:
                        st.error(f"❌ 计算失败: {results.get('message')}")

                except Exception as e:
                    st.error(f"❌ 计算出错: {str(e)}")

            progress_bar.progress(1.0)
    else:
        st.warning("请先选择或上传数据")

    # 结果展示
    if 'results' in st.session_state and st.session_state['results'].get('status') == 'success':
        st.divider()
        st.subheader("📈 计算结果")

        results = st.session_state['results']
        output_path = st.session_state.get('output_path', DATA_OUTPUT_DIR)

        # 结果概览
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("处理河区数", f"{results.get('districts_processed', 0)}")
        with col2:
            demand = results.get('total_water_demand', 0)
            st.metric("总需水量", f"{demand/10000:.1f} 亿m³")
        with col3:
            supply = results.get('total_water_supply', 0)
            st.metric("总供水量", f"{supply/10000:.1f} 亿m³")
        with col4:
            shortage = results.get('total_shortage', 0)
            st.metric("缺水量", f"{shortage/10000:.1f} 亿m³")

        # 结果文件列表
        with st.expander("📁 输出文件列表", expanded=True):
            if output_path.exists():
                # 定义目录结构
                result_dirs = {
                    "01_来水数据": output_path / "01_inflow",
                    "02_需水数据": output_path / "02_demand",
                    "03_水平衡计算": output_path / "03_calculated",
                    "04_最终合并": output_path / "04_final",
                    "05_河区汇总": output_path,  # 根目录的 output_hq_*.txt
                }

                tabs = st.tabs(list(result_dirs.keys()))

                for i, (tab_name, dir_path) in enumerate(result_dirs.items()):
                    with tabs[i]:
                        if tab_name == "05_河区汇总":
                            # 根目录的汇总文件
                            hq_files = list(dir_path.glob('output_hq_*.txt'))
                            if hq_files:
                                selected = st.selectbox(
                                    "选择文件",
                                    options=[f.name for f in hq_files],
                                    key=f"select_{i}"
                                )
                                if selected:
                                    file_path = dir_path / selected
                                    df = pd.read_csv(file_path, sep='\t')
                                    st.dataframe(df.head(30), use_container_width=True)
                            else:
                                st.info("暂无汇总文件")
                        elif dir_path.exists():
                            txt_files = list(dir_path.glob('*.txt'))
                            if txt_files:
                                selected = st.selectbox(
                                    "选择河区",
                                    options=[f.name for f in txt_files],
                                    key=f"select_{i}"
                                )
                                if selected:
                                    file_path = dir_path / selected
                                    df = pd.read_csv(file_path, sep='\t')
                                    st.dataframe(df.head(30), use_container_width=True)
                            else:
                                st.info(f"暂无数据")
                        else:
                            st.info(f"目录不存在: {dir_path.name}")

        # 下载结果
        st.subheader("📥 下载结果")

        if output_path.exists() and any(output_path.glob('**/*.txt')):
            # 打包所有结果
            result_buffer = io.BytesIO()
            with zipfile.ZipFile(result_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in output_path.rglob('*.txt'):
                    arcname = file_path.relative_to(output_path)
                    zf.write(file_path, arcname)
            result_buffer.seek(0)

            st.download_button(
                label="📦 下载全部结果 (ZIP)",
                data=result_buffer,
                file_name="河区调度结果.zip",
                mime="application/zip",
                use_container_width=True
            )

    # 页脚
    footer("河区调度", repo_url="https://github.com/zengtianli/hydro-district")


if __name__ == "__main__":
    main()
