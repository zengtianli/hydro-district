# 🗺️ Hydro District — District Water Scheduling

[![GitHub stars](https://img.shields.io/github/stars/zengtianli/hydro-district)](https://github.com/zengtianli/hydro-district)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.36+-FF4B4B.svg)](https://streamlit.io)

Daily water supply-demand balance scheduling model for 19 river districts.

![screenshot](docs/screenshot.png)

## Features

- **19 district model** — covers all river districts with individual parameters
- **Daily scheduling** — day-by-day supply-demand balance with reservoir and sluice operations
- **ZIP I/O** — upload input data as ZIP, download results as ZIP
- **Result browser** — inspect per-district output files in the UI
- **Built-in sample data** — downloadable example dataset for quick testing

## Quick Start

```bash
git clone https://github.com/zengtianli/hydro-district.git
cd hydro-district
pip install -r requirements.txt
streamlit run app.py
```

## Deploy (VPS)

```bash
git clone https://github.com/zengtianli/hydro-district.git
cd hydro-district
pip install -r requirements.txt
nohup streamlit run app.py --server.port 8506 --server.headless true &
```

## Hydro Toolkit Plugin

This project is a plugin for [Hydro Toolkit](https://github.com/zengtianli/hydro-toolkit) and can also run standalone. Install it in the Toolkit by pasting this repo URL in the Plugin Manager.

## License

MIT
