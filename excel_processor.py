"""
Excel文件处理模块
负责读取Excel文件并提取昵称数据
"""
import pandas as pd
from typing import List, Tuple, Optional
import re


class ExcelProcessor:
    # 常见的昵称/姓名列名关键词
    NICKNAME_KEYWORDS = [
        '昵称', '姓名', '用户名', '名字', '用户', 'name', 'nickname', 
        '微信昵称', '群昵称', '参与者', '打卡人', '用户昵称'
    ]
    
    # 常见的时间列名关键词
    TIME_KEYWORDS = [
        '提交时间', '时间', '打卡时间', '参与时间', '上传时间', 
        'time', 'submit_time', 'timestamp', '日期时间'
    ]
    
    def __init__(self):
        pass
    
    def find_nickname_column(self, df: pd.DataFrame) -> Optional[str]:
        """
        自动查找昵称列
        
        Args:
            df: pandas DataFrame
            
        Returns:
            昵称列名，如果找不到返回None
        """
        columns = df.columns.tolist()
        
        # 精确匹配
        for keyword in self.NICKNAME_KEYWORDS:
            for col in columns:
                if keyword == str(col).strip():
                    return col
        
        # 模糊匹配
        for keyword in self.NICKNAME_KEYWORDS:
            for col in columns:
                if keyword in str(col):
                    return col
        
        # 如果没有找到，检查第一列是否包含文本数据
        if len(columns) > 0:
            first_col = columns[0]
            # 检查第一列前几行是否主要是文本
            sample_data = df[first_col].dropna().head(10)
            if len(sample_data) > 0:
                text_count = sum(1 for x in sample_data if isinstance(x, str) and len(str(x).strip()) > 0)
                if text_count / len(sample_data) > 0.7:  # 70%以上是文本
                    return first_col
        
        return None
    
    def find_time_column(self, df: pd.DataFrame) -> Optional[str]:
        """
        自动查找时间列
        
        Args:
            df: pandas DataFrame
            
        Returns:
            时间列名，如果找不到返回None
        """
        columns = df.columns.tolist()
        
        # 精确匹配
        for keyword in self.TIME_KEYWORDS:
            for col in columns:
                if keyword == str(col).strip():
                    return col
        
        # 模糊匹配
        for keyword in self.TIME_KEYWORDS:
            for col in columns:
                if keyword in str(col):
                    return col
        
        return None
    
    def clean_nickname(self, nickname: str) -> str:
        """
        清理昵称数据
        
        Args:
            nickname: 原始昵称
            
        Returns:
            清理后的昵称
        """
        if pd.isna(nickname) or nickname is None:
            return ""
        
        nickname = str(nickname).strip()
        
        # 移除常见的无效字符和标记
        # 移除emoji（简单处理）
        nickname = re.sub(r'[^\w\u4e00-\u9fff\u3400-\u4dbf\s]', '', nickname)
        
        # 移除多余空格
        nickname = re.sub(r'\s+', ' ', nickname).strip()
        
        return nickname
    
    def extract_nicknames_and_times_from_file(self, file_content, file_name: str) -> Tuple[List[str], List[str], str]:
        """
        从Excel文件内容中提取昵称和提交时间
        
        Args:
            file_content: 文件内容（bytes）
            file_name: 文件名
            
        Returns:
            (昵称列表, 提交时间列表, 错误信息)
        """
        try:
            # 尝试读取Excel文件，指定第2行为列名（header=1，因为索引从0开始）
            if file_name.endswith('.xlsx'):
                df = pd.read_excel(file_content, engine='openpyxl', header=1)
            elif file_name.endswith('.xls'):
                df = pd.read_excel(file_content, engine='xlrd', header=1)
            else:
                return [], f"不支持的文件格式: {file_name}"
            
            if df.empty:
                return [], f"文件为空: {file_name}"
            
            # 查找昵称列
            nickname_column = self.find_nickname_column(df)
            if nickname_column is None:
                # 如果找不到昵称列，返回可用列名供用户参考
                available_columns = ", ".join(df.columns.tolist())
                return [], [], f"未找到昵称列，可用列名: {available_columns}"
            
            # 查找时间列
            time_column = self.find_time_column(df)
            
            # 提取昵称和时间数据
            nicknames_raw = df[nickname_column].tolist()
            times_raw = df[time_column].tolist() if time_column else [None] * len(nicknames_raw)
            
            # 清理和去重，同时保持昵称和时间的对应关系
            nicknames_clean = []
            times_clean = []
            seen = set()
            
            for nickname, time_val in zip(nicknames_raw, times_raw):
                clean_name = self.clean_nickname(nickname)
                if clean_name and clean_name not in seen and len(clean_name) > 0:
                    nicknames_clean.append(clean_name)
                    times_clean.append(str(time_val) if time_val is not None else "")
                    seen.add(clean_name)
            
            return nicknames_clean, times_clean, ""
            
        except Exception as e:
            return [], [], f"处理文件 {file_name} 时出错: {str(e)}"
    
    def extract_nicknames_from_file(self, file_content, file_name: str) -> Tuple[List[str], str]:
        """
        从Excel文件内容中提取昵称（保持向后兼容）
        
        Args:
            file_content: 文件内容（bytes）
            file_name: 文件名
            
        Returns:
            (昵称列表, 错误信息)
        """
        nicknames, _, error = self.extract_nicknames_and_times_from_file(file_content, file_name)
        return nicknames, error
    
    def batch_process_files(self, uploaded_files) -> Tuple[List[Tuple[str, List[str]]], List[str]]:
        """
        批量处理上传的文件
        
        Args:
            uploaded_files: Streamlit上传的文件列表
            
        Returns:
            (成功处理的文件结果列表, 错误信息列表)
        """
        successful_results = []
        error_messages = []
        
        for uploaded_file in uploaded_files:
            nicknames, error_msg = self.extract_nicknames_from_file(
                uploaded_file, uploaded_file.name
            )
            
            if error_msg:
                error_messages.append(f"{uploaded_file.name}: {error_msg}")
            else:
                successful_results.append((uploaded_file.name, nicknames))
        
        return successful_results, error_messages
    
    def validate_file_format(self, file_name: str) -> bool:
        """
        验证文件格式是否支持
        
        Args:
            file_name: 文件名
            
        Returns:
            是否支持该格式
        """
        supported_extensions = ['.xlsx', '.xls']
        return any(file_name.lower().endswith(ext) for ext in supported_extensions)
    
    def get_file_info(self, file_content, file_name: str) -> dict:
        """
        获取Excel文件基本信息
        
        Args:
            file_content: 文件内容
            file_name: 文件名
            
        Returns:
            文件信息字典
        """
        try:
            # 指定第2行为列名（header=1）
            if file_name.endswith('.xlsx'):
                df = pd.read_excel(file_content, engine='openpyxl', header=1)
            elif file_name.endswith('.xls'):
                df = pd.read_excel(file_content, engine='xlrd', header=1)
            else:
                return {"error": "不支持的文件格式"}
            
            return {
                "file_name": file_name,
                "total_rows": len(df),
                "total_columns": len(df.columns),
                "columns": df.columns.tolist(),
                "nickname_column": self.find_nickname_column(df)
            }
            
        except Exception as e:
            return {"error": f"读取文件信息失败: {str(e)}"}
