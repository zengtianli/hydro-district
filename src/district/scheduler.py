#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
河区调度模型 - 核心调度器

封装完整的水资源调度计算流程
"""
import os
import shutil
import pandas as pd
from pathlib import Path
from scipy import interpolate
from functools import lru_cache

from .config import (
    Config, DISTRICT_NAME_MAPPING, SLUICE_NAME_MAPPING,
    SUMMARY_COLUMNS, BALANCED_DISTRICTS
)


class DataLoader:
    """数据加载器"""
    
    def __init__(self, config: Config):
        self.config = config
    
    def read_data(self, filename) -> pd.DataFrame:
        """读取制表符分隔的数据文件"""
        return pd.read_csv(filename, sep=self.config.FILE_SEPARATOR)
    
    def load_storage_curves(self) -> dict:
        """加载库容曲线，生成插值函数"""
        file_path = self.config.get_input_path('HQ_ZQ')
        storage_curves = {}
        try:
            df = self.read_data(file_path)
            for _, row in df.iterrows():
                district = row['分区名称']
                volumes = [row[col] for col in self.config.VOLUME_COLUMNS]
                levels = [row[col] for col in self.config.LEVEL_COLUMNS]
                storage_curves[district] = {
                    'level_to_volume': interpolate.interp1d(
                        levels, volumes, kind='linear',
                        bounds_error=False, fill_value=(volumes[0], volumes[-1])
                    ),
                    'volume_to_level': interpolate.interp1d(
                        volumes, levels, kind='linear',
                        bounds_error=False, fill_value=(levels[0], levels[-1])
                    )
                }
            return storage_curves
        except Exception as e:
            print(f'加载蓄水曲线时出错: {e}')
            return {}


class ReservoirInflowGenerator:
    """水库来水生成器"""
    
    def __init__(self, config: Config, data_loader: DataLoader):
        self.config = config
        self.data_loader = data_loader
    
    def generate(self) -> dict:
        """生成各分区的水库来水数据"""
        self.config.ensure_directories()
        hq_sk_df = self.data_loader.read_data(self.config.get_input_path('HQ_SK'))
        sk_df = self.data_loader.read_data(self.config.get_input_path('SK'))
        
        district_reservoir_inflow = {}
        for _, row in hq_sk_df.iterrows():
            district = row['分区名称']
            count = int(row['包含水库数量'])
            if count <= 0:
                continue
            print(f"处理河区: {district}, 水库数量: {count}")
            reservoirs = []
            for i in range(count):
                col_name = f'Unnamed: {i+2}'
                if col_name in row and pd.notna(row[col_name]):
                    reservoirs.append(row[col_name])
            if not reservoirs:
                continue
            if district not in district_reservoir_inflow:
                district_reservoir_inflow[district] = pd.Series(0.0, index=range(len(sk_df)))
            for reservoir in reservoirs:
                if reservoir in sk_df.columns:
                    district_reservoir_inflow[district] += sk_df[reservoir].fillna(0)
        
        print(f"已生成各分区水库来水数据")
        return district_reservoir_inflow


class WaterBalanceCalculator:
    """水平衡计算器"""
    
    def __init__(self, config: Config, data_loader: DataLoader):
        self.config = config
        self.data_loader = data_loader
    
    def calculate(self, district, dates, df_dict, storage_curves):
        """主计算方法"""
        balance_df = pd.DataFrame({self.config.DATE_COLUMN: dates})
        balance_df["合计来水"] = df_dict['inflow']["合计来水"]
        balance_df["需水量"] = df_dict['demand']["需水量"]
        
        # 生态需水计算
        balance_df["其他生态需水"] = df_dict['demand']["其他生态需水"]
        balance_df["水位生态需水"] = 0.0
        balance_df["生态需水"] = balance_df["其他生态需水"] + balance_df["水位生态需水"]
        balance_df["总需水量"] = balance_df["需水量"] + balance_df["生态需水"]
        
        # 净流量计算
        balance_df["净流量"] = balance_df["合计来水"] - balance_df["总需水量"]
        
        # 初始化所有字段
        for col in ["目标容积", "日初容积", "日中容积", "日末容积", "排末容积", 
                    "水位生态需水", "初河蓄水", "蓄水消后", "缺水(浙东需供)", 
                    "末河蓄水", "排河蓄水", "排水容积", "河区排水", 
                    "容积变化", "排后变化", "纳蓄能力", "低水位以上蓄水量", "总蓄水量"]:
            balance_df[col] = 0.0
        
        # 获取基础参数
        first_date = pd.to_datetime(dates.iloc[0])
        last_date = pd.to_datetime(dates.iloc[-1])
        total_days = (last_date - first_date).days
        
        first_day_level = self.config.INITIAL_LEVEL_DF.loc[0, district]
        target_level = self.config.TARGET_LEVEL_DF.loc[0, district]
        drainage_level = self.config.DRAINAGE_LEVEL_DF.loc[0, district]
        
        first_day_storage = float(storage_curves[district]['level_to_volume'](first_day_level))
        target_storage = float(storage_curves[district]['level_to_volume'](target_level))
        drain_storage = float(storage_curves[district]['level_to_volume'](drainage_level))
        
        # 获取高低水位容积
        hq_zq_df = self.data_loader.read_data(self.config.get_input_path('HQ_ZQ'))
        district_info = hq_zq_df[hq_zq_df['分区名称'] == district].iloc[0]
        high_level = district_info['高水位']
        low_level = district_info['低水位']
        high_level_volume = float(storage_curves[district]['level_to_volume'](high_level))
        low_level_volume = float(storage_curves[district]['level_to_volume'](low_level))
        
        # 逐日计算
        for i in balance_df.index:
            self._calculate_daily(balance_df, i, first_day_storage, target_storage, 
                                  drain_storage, high_level_volume, low_level_volume)
        
        # 保存结果
        balance_df.to_csv(
            self.config.get_output_path(self.config.CALCULATED_OUT_DIR, f"{district}.txt"),
            sep=self.config.FILE_SEPARATOR, index=False
        )
        print(f"保存水平衡结果: {district}")
    
    def _calculate_daily(self, df, i, first_day_storage, target_storage, 
                         drain_storage, high_level_volume, low_level_volume):
        """逐日水平衡计算"""
        net_flow = df.loc[i, "净流量"]
        
        # 日初容积
        if i == 0:
            day_initial = first_day_storage
        else:
            day_initial = df.loc[i-1, "排末容积"]
        
        # 日中容积
        day_middle = day_initial + net_flow
        
        # 缺水计算
        total_demand = df.loc[i, "总需水量"]
        total_inflow = df.loc[i, "合计来水"]
        external_supply = max(total_demand - total_inflow, 0)
        
        # 日末容积
        day_end = day_middle + external_supply
        
        # 排水
        drainage = max(0, day_end - drain_storage)
        end_after_drain = day_end - drainage
        
        # 更新 DataFrame
        df.loc[i, "目标容积"] = target_storage
        df.loc[i, "日初容积"] = day_initial
        df.loc[i, "日中容积"] = day_middle
        df.loc[i, "日末容积"] = day_end
        df.loc[i, "排末容积"] = end_after_drain
        df.loc[i, "排水容积"] = drain_storage
        df.loc[i, "缺水(浙东需供)"] = external_supply
        df.loc[i, "河区排水"] = drainage
        df.loc[i, "容积变化"] = net_flow
        df.loc[i, "排后变化"] = net_flow - drainage
        df.loc[i, "纳蓄能力"] = high_level_volume - end_after_drain
        df.loc[i, "低水位以上蓄水量"] = max(0, end_after_drain - low_level_volume)
        df.loc[i, "总蓄水量"] = end_after_drain


class DistrictDataProcessor:
    """分区数据处理器"""
    
    def __init__(self, config: Config, data_loader: DataLoader, 
                 water_calculator: WaterBalanceCalculator):
        self.config = config
        self.data_loader = data_loader
        self.water_calculator = water_calculator
    
    def collect_district_data(self, file_category: str, district: str) -> dict:
        """收集分区数据"""
        result = {}
        for file_key in self.config.FILE_CATEGORIES.get(file_category, []):
            try:
                file_path = self.config.get_input_path(file_key)
                df = self.data_loader.read_data(file_path)
                if district in df.columns:
                    file_name = self.config.INPUT_FILES[file_key].split('.')[0]
                    file_name = file_name.replace('static_', '').replace('input_', '')
                    result[file_name] = df[district]
            except Exception as e:
                print(f"从 {file_key} 中获取 {district} 数据时出错: {e}")
        return result
    
    def process_district_data(self, district, dates, storage_curves, reservoir_inflow=None):
        """处理单个分区数据"""
        demand_data = self.collect_district_data('demand', district)
        inflow_data = self.collect_district_data('inflow', district)
        
        demand_df = pd.DataFrame({self.config.DATE_COLUMN: dates})
        inflow_df = pd.DataFrame({self.config.DATE_COLUMN: dates})
        
        # 需水映射
        demand_mapping = {
            'GPS_GGXS': '农业需水',
            'XS_ST': '其他生态需水',
            'XS_FN': '非农需水'
        }
        for source_key, target_col in demand_mapping.items():
            demand_df[target_col] = demand_data.get(source_key, 0.0)
        demand_df['需水量'] = demand_df['农业需水'] + demand_df['非农需水']
        
        # 来水映射
        inflow_mapping = {
            'GPS_PYCS': '平原产水',
            'LS_QT': '其他外供',
            'FQJL': '河网供水',
            'SK': '水库供水'
        }
        for source_key, target_col in inflow_mapping.items():
            if source_key == 'SK' and reservoir_inflow and district in reservoir_inflow:
                inflow_df[target_col] = reservoir_inflow[district].values
            else:
                inflow_df[target_col] = inflow_data.get(source_key, 0.0)
        
        # 动态平衡河区处理
        if district in BALANCED_DISTRICTS:
            total_demand = demand_df['需水量'] + demand_df['其他生态需水']
            inflow_df['其他外供'] = total_demand - inflow_df['河网供水'] - inflow_df['水库供水']
            print(f"河区 {district} 启用动态平衡模式")
        
        inflow_df['合计来水'] = inflow_df[['其他外供', '河网供水', '水库供水']].sum(axis=1)
        
        # 保存中间结果
        inflow_df.to_csv(
            self.config.get_output_path(self.config.INFLOW_OUT_DIR, f"{district}.txt"),
            sep=self.config.FILE_SEPARATOR, index=False
        )
        demand_df.to_csv(
            self.config.get_output_path(self.config.DEMAND_OUT_DIR, f"{district}.txt"),
            sep=self.config.FILE_SEPARATOR, index=False
        )
        
        # 计算水平衡
        df_dict = {'inflow': inflow_df, 'demand': demand_df}
        self.water_calculator.calculate(district, dates, df_dict, storage_curves)
    
    def generate_categorized_data(self, reservoir_inflow=None):
        """生成分类数据"""
        self.config.ensure_directories()
        storage_curves = self.data_loader.load_storage_curves()
        
        df_demand = self.data_loader.read_data(self.config.get_input_path('XS_ST'))
        dates = df_demand[self.config.DATE_COLUMN]
        
        df_level = self.data_loader.read_data(self.config.get_input_path('SW_CS'))
        districts = [col for col in df_level.columns if col != self.config.DATE_COLUMN]
        
        for district in districts:
            self.process_district_data(district, dates, storage_curves, reservoir_inflow)


class DistrictScheduler:
    """河区调度主控制器"""
    
    def __init__(self, data_path: Path = None, output_path: Path = None):
        """初始化调度器
        
        Args:
            data_path: 输入数据目录
            output_path: 输出目录（可选，默认与输入相同）
        """
        self.config = Config(data_path)
        self.output_base = output_path if output_path else self.config.BASE_DIR
        
        if output_path:
            # 直接使用 output_path，不再嵌套 'data'
            self.config.DATA_DIR = output_path
            self.config.INFLOW_OUT_DIR = output_path / '01_inflow'
            self.config.DEMAND_OUT_DIR = output_path / '02_demand'
            self.config.CALCULATED_OUT_DIR = output_path / '03_calculated'
            self.config.FINAL_OUT_DIR = output_path / '04_final'
        
        self.data_loader = DataLoader(self.config)
        self.water_calculator = WaterBalanceCalculator(self.config, self.data_loader)
        self.district_processor = DistrictDataProcessor(
            self.config, self.data_loader, self.water_calculator
        )
        self.reservoir_generator = ReservoirInflowGenerator(self.config, self.data_loader)
        
        self.results = {}
    
    def run(self, progress_callback=None) -> dict:
        """运行完整调度计算
        
        Args:
            progress_callback: 进度回调函数 (step, total, message)
        
        Returns:
            计算结果摘要
        """
        total_steps = 7
        
        def update_progress(step, message):
            if progress_callback:
                progress_callback(step, total_steps, message)
            print(f"[{step}/{total_steps}] {message}")
        
        try:
            # Step 1: 初始化
            update_progress(1, "初始化配置...")
            self.config.initialize()
            self.config.ensure_directories()
            
            # Step 2: 加载规则
            update_progress(2, "加载分水枢纽规则...")
            self.config.load_fssn_rules(self.data_loader)
            self.config.load_level_data(self.data_loader)
            
            # Step 3: 生成水库来水
            update_progress(3, "生成水库来水数据...")
            reservoir_inflow = self.reservoir_generator.generate()
            
            # Step 4: 处理分区数据
            update_progress(4, "处理各分区数据...")
            self.district_processor.generate_categorized_data(reservoir_inflow)
            
            # Step 5: 合并输出
            update_progress(5, "合并输出数据...")
            self._merge_and_output()
            
            # Step 6: 复制重命名
            update_progress(6, "复制并重命名文件...")
            self._copy_and_rename()
            
            # Step 7: 生成汇总
            update_progress(7, "生成汇总报表...")
            self._generate_summary()
            
            self.results['status'] = 'success'
            self.results['message'] = '处理完成！'
            
        except Exception as e:
            self.results['status'] = 'error'
            self.results['message'] = str(e)
        
        return self.results
    
    def _merge_and_output(self):
        """合并并输出最终数据"""
        calculated_files = os.listdir(self.config.CALCULATED_OUT_DIR)
        district_files = [f for f in calculated_files if f.endswith('.txt')]
        
        for file in district_files:
            district = os.path.splitext(file)[0]
            try:
                calc_file = self.config.get_output_path(self.config.CALCULATED_OUT_DIR, file)
                inflow_file = self.config.get_output_path(self.config.INFLOW_OUT_DIR, file)
                demand_file = self.config.get_output_path(self.config.DEMAND_OUT_DIR, file)
                
                if not all(os.path.exists(f) for f in [calc_file, inflow_file, demand_file]):
                    continue
                
                calc_df = pd.read_csv(calc_file, sep=self.config.FILE_SEPARATOR)
                inflow_df = pd.read_csv(inflow_file, sep=self.config.FILE_SEPARATOR)
                demand_df = pd.read_csv(demand_file, sep=self.config.FILE_SEPARATOR)
                
                # 合并数据
                result_df = pd.DataFrame()
                result_df[self.config.DATE_COLUMN] = calc_df[self.config.DATE_COLUMN]
                
                for col in inflow_df.columns:
                    if col != self.config.DATE_COLUMN:
                        result_df[col] = inflow_df[col]
                
                for col in demand_df.columns:
                    if col != self.config.DATE_COLUMN:
                        result_df[col] = demand_df[col]
                
                for col in calc_df.columns:
                    if col not in result_df.columns:
                        result_df[col] = calc_df[col]
                
                # 计算额外字段
                if '其他生态需水' not in result_df.columns:
                    result_df['其他生态需水'] = 0
                result_df['生态需水'] = result_df.get('其他生态需水', 0) + result_df.get('水位生态需水', 0)
                result_df['总需水量'] = result_df['需水量'] + result_df['生态需水']
                result_df['本地可供水量'] = result_df['合计来水'] + result_df['初河蓄水'].apply(lambda x: max(x, 0))
                
                output_file = self.config.get_output_path(self.config.FINAL_OUT_DIR, file)
                result_df.to_csv(output_file, sep=self.config.FILE_SEPARATOR, index=False)
                
            except Exception as e:
                print(f"处理分区 {district} 时出错: {e}")
    
    def _copy_and_rename(self):
        """复制并重命名文件到输出根目录"""
        src_dir = self.config.FINAL_OUT_DIR
        dst_dir = Path(self.output_base)  # 使用输出目录
        
        for chinese_name, code_name in DISTRICT_NAME_MAPPING.items():
            src_file = src_dir / f"{chinese_name}.txt"
            dst_file = dst_dir / f"{code_name}.txt"
            if src_file.exists():
                shutil.copy2(src_file, dst_file)
    
    def _generate_summary(self):
        """生成汇总文件"""
        output_dir = str(self.output_base)  # 使用输出目录
        
        # 查找所有河区文件
        hq_files = [f for f in os.listdir(output_dir)
                   if f.startswith('output_hq_') and f.endswith('.txt')
                   and 'all' not in f]
        
        if not hq_files:
            return
        
        first_file = os.path.join(output_dir, hq_files[0])
        first_df = pd.read_csv(first_file, sep=self.config.FILE_SEPARATOR)
        
        summary_df = pd.DataFrame()
        summary_df[self.config.DATE_COLUMN] = first_df[self.config.DATE_COLUMN]
        
        for col in SUMMARY_COLUMNS:
            summary_df[col] = 0.0
        
        for hq_file in hq_files:
            file_path = os.path.join(output_dir, hq_file)
            try:
                df = pd.read_csv(file_path, sep=self.config.FILE_SEPARATOR)
                for col in SUMMARY_COLUMNS:
                    if col in df.columns:
                        summary_df[col] += df[col].fillna(0).values
            except Exception as e:
                print(f"处理 {hq_file} 时出错: {e}")
        
        # 保存汇总到输出目录
        output_file = os.path.join(output_dir, 'output_hq_all.txt')
        summary_df.to_csv(output_file, sep=self.config.FILE_SEPARATOR, index=False)
        
        # 保存计算结果摘要
        self.results['districts_processed'] = len(hq_files)
        self.results['total_water_demand'] = summary_df['总需水量'].sum() if '总需水量' in summary_df.columns else 0
        self.results['total_water_supply'] = summary_df['合计来水'].sum() if '合计来水' in summary_df.columns else 0
        self.results['total_shortage'] = summary_df['缺水(浙东需供)'].sum() if '缺水(浙东需供)' in summary_df.columns else 0
    
    def get_district_list(self) -> list:
        """获取河区列表"""
        return list(DISTRICT_NAME_MAPPING.keys())
    
    def get_sluice_list(self) -> list:
        """获取分水枢纽列表"""
        return list(SLUICE_NAME_MAPPING.keys())

