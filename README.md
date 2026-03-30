        # hydro-district

        **English** | [中文](README_CN.md)

        Daily water supply-demand scheduling across 19 river districts with reservoir and sluice gate management.

        [![Live Demo](https://img.shields.io/badge/Live_Demo-hydro--district.tianlizeng.cloud-blue?style=for-the-badge)](https://hydro-district.tianlizeng.cloud)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-yellow?style=for-the-badge)](https://python.org)
        [![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

        ---

### Try it now — no install needed

**https://hydro-district.tianlizeng.cloud**

---

![hydro-district demo](docs/screenshots/demo.png)

        ---

        ## What can hydro-district do?

        | Feature | Description |
        |---------|-------------|
        | **19-district model** | Individual parameters per district for accurate local scheduling |
| **Daily scheduling** | Day-by-day supply-demand balance with operations log |
| **Reservoir & sluice control** | Manage inflow, outflow, gate operations per timestep |
| **Batch import/export** | ZIP-based multi-district data workflow |
| **Result browser** | Built-in viewer for district-specific outputs |

        ## Install

        ```bash
        git clone https://github.com/zengtianli/hydro-district.git
cd hydro-district
pip install -r requirements.txt
        ```

        ## Quick Start

        ```bash
        streamlit run app.py
        ```

        ## Self-host

```bash
git clone https://github.com/zengtianli/hydro-district.git
cd hydro-district
pip install -r requirements.txt
streamlit run app.py
```

Or use the hosted version: **https://hydro-district.tianlizeng.cloud**

## Requirements

        - Python 3.9+
        - Streamlit 1.36+

        ## License

        MIT
