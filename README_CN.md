# 🗺️ 河区调度

[![GitHub stars](https://img.shields.io/github/stars/zengtianli/hydro-district)](https://github.com/zengtianli/hydro-district)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.36+-FF4B4B.svg)](https://streamlit.io)
[![在线演示](https://img.shields.io/badge/%E5%9C%A8%E7%BA%BF%E6%BC%94%E7%A4%BA-hydro--district.tianlizeng.cloud-brightgreen)](https://hydro-district.tianlizeng.cloud)

19 河区逐日水资源供需平衡调度模型。

![screenshot](docs/screenshot.png)

## 功能特点

- **19 河区模型** — 覆盖所有河区，各区独立参数
- **逐日调度** — 水库和闸门操作的逐日供需平衡
- **ZIP 输入输出** — 打包上传输入数据，打包下载调度结果
- **结果浏览器** — 在页面中查看各河区输出文件
- **内置示例数据** — 可下载的示例数据集

## 快速开始

```bash
git clone https://github.com/zengtianli/hydro-district.git
cd hydro-district
pip install -r requirements.txt
streamlit run app.py
```

## 部署（VPS）

```bash
git clone https://github.com/zengtianli/hydro-district.git
cd hydro-district
pip install -r requirements.txt
nohup streamlit run app.py --server.port 8506 --server.headless true &
```

## Hydro Toolkit 插件

本项目是 [Hydro Toolkit](https://github.com/zengtianli/hydro-toolkit) 的插件，也可独立运行。在 Toolkit 的插件管理页面粘贴本仓库 URL 即可安装。也可以直接**[在线体验](https://hydro-district.tianlizeng.cloud)**，无需安装。

## 许可证

MIT
