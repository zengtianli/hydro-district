        # hydro-district

        [English](README.md) | **中文**

        面向 19 个河湖分区的逐日供需调度模型，支持水库与闸门精细化管理。

        [![在线演示](https://img.shields.io/badge/在线演示-hydro--district.tianlizeng.cloud-blue?style=for-the-badge)](https://hydro-district.tianlizeng.cloud)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-yellow?style=for-the-badge)](https://python.org)
        [![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

        ---

        ---

### 无需安装，立即体验

**https://hydro-district.tianlizeng.cloud**

---

![hydro-district demo](docs/screenshots/demo.png)

        ---

        ## 功能一览

        | 功能 | 说明 |
        |------|------|
        | **19 分区模型** | 各分区独立参数，精准本地化调度 |
| **逐日调度** | 逐日供需平衡，含操作日志 |
| **水库与闸门控制** | 管理每个时步的入流、出流和闸门操作 |
| **批量导入/导出** | 基于 ZIP 的多分区数据工作流 |
| **结果浏览器** | 内置分区专属输出查看器 |

        ## 安装

        ```bash
        git clone https://github.com/zengtianli/hydro-district.git
cd hydro-district
pip install -r requirements.txt
        ```

        ## 快速开始

        ```bash
        streamlit run app.py
        ```

        ## 自托管

```bash
git clone https://github.com/zengtianli/hydro-district.git
cd hydro-district
pip install -r requirements.txt
streamlit run app.py
```

或直接使用托管版本：**https://hydro-district.tianlizeng.cloud**

## 环境要求

        - Python 3.9+
        - Streamlit 1.36+

        ## License

        MIT
