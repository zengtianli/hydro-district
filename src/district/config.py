#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
河区调度模型 - 配置模块

管理路径、常量、文件映射等配置信息
"""
import os
import sys
import pandas as pd
from pathlib import Path
from functools import lru_cache

# 输入文件映射
INPUT_FILES = {
    'HQ_ZQ': 'static_HQ_ZQ.txt',
    'HQ_SK': 'static_HQ_SK.txt',
    'SK': 'input_SK.txt',
    'SW_CS': 'input_SW_CS.txt',
    'SW_PS': 'static_SW_PS.txt',
    'SW_MB': 'input_SW_MB.txt',
    'FQJL': 'input_FQJL.txt',
    'LS_QT': 'input_LS_QT.txt',
    'XS_FN': 'input_XS_FN.txt',
    'XS_ST': 'input_XS_ST.txt',
    'GPS_GGXS': 'input_GPS_GGXS.txt',
    'GPS_PYCS': 'input_GPS_PYCS.txt',
    'FSSN_RULES': 'static_FSSN_RULES.txt'
}

# 文件分类
FILE_CATEGORIES = {
    'demand': ['XS_FN', 'XS_ST', 'GPS_GGXS'],
    'inflow': ['FQJL', 'LS_QT', 'SK', 'GPS_PYCS'],
    'other': ['HQ_ZQ', 'HQ_SK', 'FSSN_RULES', 'SW_CS', 'SW_PS', 'SW_MB']
}

# 默认库容和水位列
DEFAULT_VOLUME_COLUMNS = ['死库容', '低库容', '中库容', '高库容', '超蓄库容']
DEFAULT_LEVEL_COLUMNS = ['死水位', '低水位', '中水位', '高水位', '超蓄水位']

# 河区名称映射
DISTRICT_NAME_MAPPING = {
    "丰惠平原区": "output_hq_FHPYQ",
    "余姚平原上河区": "output_hq_YYPYSHQ",
    "余姚平原下河区": "output_hq_YYPYXHQ",
    "余姚平原姚江上游区": "output_hq_YYPYYJSYQ",
    "余姚平原姚江下游区": "output_hq_YYPYYJXYQ",
    "余姚平原马渚中河区": "output_hq_YYPYMZZHQ",
    "南沙平原区": "output_hq_NSPYQ",
    "姚江沿线大工业用水区": "output_hq_YJYXDGYYSQ",
    "慈溪平原东河区": "output_hq_CXPYDHQ",
    "慈溪平原中河区": "output_hq_CXPYZHQ",
    "慈溪平原西河区": "output_hq_CXPYXHQ",
    "江北镇海平原区": "output_hq_JBZHPYQ",
    "海曙平原区": "output_hq_HSPYQ",
    "绍虞平原区": "output_hq_SYPYQ",
    "舟山大陆用水区": "output_hq_ZSDLYSQ",
    "虞北平原上河区": "output_hq_YBPYSHQ",
    "虞北平原中河区": "output_hq_YBPYZHQ",
    "蜀山平原区": "output_hq_SSPYQ",
    "鄞州调水区": "output_hq_YZTSQ"
}

# 分水枢纽名称映射
SLUICE_NAME_MAPPING = {
    "三兴闸.txt": "output_sn_SXZ.txt",
    "上虞枢纽.txt": "output_sn_SYSN.txt",
    "四塘闸_七塘闸.txt": "output_sn_STZQTZ.txt",
    "浦前闸.txt": "output_sn_PQZ.txt",
    "牟山闸.txt": "output_sn_MOUSZ.txt",
    "萧山枢纽.txt": "output_sn_XSSN.txt"
}

# 汇总字段列表
SUMMARY_COLUMNS = [
    '平原产水', '其他外供', '河网供水', '水库供水', '合计来水',
    '农业需水', '其他生态需水', '非农需水', '需水量', '净流量',
    '目标容积', '日初容积', '日中容积', '日末容积', '排末容积', '水位生态需水',
    '初河蓄水', '蓄水消后', '缺水(浙东需供)', '末河蓄水', '排河蓄水',
    '排水容积', '河区排水', '容积变化', '排后变化', '纳蓄能力', '低水位以上蓄水量', '总蓄水量', 
    '生态需水', '总需水量', '本地可供水量', '展示本地可供水量'
]

# 动态平衡河区（净流量=0）
BALANCED_DISTRICTS = ['南沙平原区', '海曙平原区', '绍虞平原区', '蜀山平原区']


class Config:
    """全局配置类"""
    
    def __init__(self, base_dir: Path = None):
        """初始化配置
        
        Args:
            base_dir: 数据基础目录，默认使用 data/sample
        """
        if base_dir is None:
            # 默认使用 webapp 目录下的 data/sample
            base_dir = Path(__file__).parent.parent / 'data' / 'sample'
        
        self.BASE_DIR = Path(base_dir)
        self.INPUT_DIR = self.BASE_DIR
        self.DATA_DIR = self.BASE_DIR / 'data'
        self.INFLOW_OUT_DIR = self.DATA_DIR / '01_inflow'
        self.DEMAND_OUT_DIR = self.DATA_DIR / '02_demand'
        self.CALCULATED_OUT_DIR = self.DATA_DIR / '03_calculated'
        self.FINAL_OUT_DIR = self.DATA_DIR / '04_final'
        
        self.FILE_SEPARATOR = '\t'
        self.DATE_COLUMN = '日期'
        self.INPUT_FILES = INPUT_FILES
        self.FILE_CATEGORIES = FILE_CATEGORIES
        self.VOLUME_COLUMNS = DEFAULT_VOLUME_COLUMNS.copy()
        self.LEVEL_COLUMNS = DEFAULT_LEVEL_COLUMNS.copy()
        
        self.FSSN_RULES = {}
        self.INITIAL_LEVEL_DF = None
        self.DRAINAGE_LEVEL_DF = None
        self.TARGET_LEVEL_DF = None
    
    def get_input_path(self, file_key: str) -> Path:
        """获取输入文件路径"""
        return self.INPUT_DIR / self.INPUT_FILES[file_key]
    
    def get_output_path(self, output_dir: Path, filename: str) -> Path:
        """获取输出文件路径"""
        return output_dir / filename
    
    def initialize(self):
        """初始化配置，读取库容和水位列"""
        hq_zq_path = self.get_input_path('HQ_ZQ')
        try:
            if os.path.exists(hq_zq_path):
                with open(hq_zq_path, 'r', encoding='utf-8') as f:
                    header = f.readline().strip().split(self.FILE_SEPARATOR)
                self.VOLUME_COLUMNS = [col for col in header if '库容' in col]
                self.LEVEL_COLUMNS = [col for col in header if '水位' in col]
                print(f"从文件中读取的库容列: {self.VOLUME_COLUMNS}")
                print(f"从文件中读取的水位列: {self.LEVEL_COLUMNS}")
            else:
                print(f"警告: 文件 {hq_zq_path} 不存在，使用默认的库容和水位列")
        except Exception as e:
            print(f"初始化配置时出错: {e}，使用默认的库容和水位列")
    
    def ensure_directories(self):
        """确保输出目录存在"""
        dirs = [self.DATA_DIR, self.INFLOW_OUT_DIR, self.DEMAND_OUT_DIR, 
                self.CALCULATED_OUT_DIR, self.FINAL_OUT_DIR]
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)
    
    def load_fssn_rules(self, data_loader):
        """加载分水枢纽规则"""
        try:
            fssn_rules_path = self.get_input_path('FSSN_RULES')
            if os.path.exists(fssn_rules_path):
                fssn_df = data_loader.read_data(fssn_rules_path)
                self.FSSN_RULES = {}
                for _, row in fssn_df.iterrows():
                    sluice_name = row['分水枢纽名称']
                    count = int(row['包含区域数量'])
                    if count <= 0:
                        continue
                    districts = []
                    for i in range(count):
                        column_name = f'区域{i+1}'
                        if column_name in row and pd.notna(row[column_name]):
                            districts.append(row[column_name])
                    if districts:
                        self.FSSN_RULES[sluice_name] = districts
                print(f"已成功加载分水枢纽规则: {len(self.FSSN_RULES)}个枢纽")
            else:
                print(f"警告: 分水枢纽规则文件 {fssn_rules_path} 不存在")
        except Exception as e:
            print(f"加载分水枢纽规则时出错: {str(e)}")
    
    def load_level_data(self, data_loader):
        """加载水位数据"""
        self.INITIAL_LEVEL_DF = data_loader.read_data(self.get_input_path('SW_CS'))
        self.DRAINAGE_LEVEL_DF = data_loader.read_data(self.get_input_path('SW_PS'))
        self.TARGET_LEVEL_DF = data_loader.read_data(self.get_input_path('SW_MB'))

