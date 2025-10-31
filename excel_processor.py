"""
Excel文件处理模块
负责读取Excel文件并提取昵称数据
"""
import pandas as pd
from typing import List, Tuple, Optional, Dict
import re
from openpyxl import load_workbook
import io


class ExcelProcessor:
    # 常见的昵称列名关键词
    NICKNAME_KEYWORDS = [
        '昵称'
    ]
    
    # 常见的姓名列名关键词
    NAME_KEYWORDS = [
        '姓名', '真实姓名', '名字', '用户名'
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
    
    def find_name_column(self, df: pd.DataFrame) -> Optional[str]:
        """
        自动查找姓名列
        
        Args:
            df: pandas DataFrame
            
        Returns:
            姓名列名，如果找不到返回None
        """
        columns = df.columns.tolist()
        
        # 精确匹配
        for keyword in self.NAME_KEYWORDS:
            for col in columns:
                if keyword == str(col).strip():
                    return col
        
        # 模糊匹配
        for keyword in self.NAME_KEYWORDS:
            for col in columns:
                if keyword in str(col):
                    return col
        
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
    
    def count_images_in_excel(self, file_content, file_name: str, header_row: int = 0) -> Dict[int, int]:
        """
        统计Excel文件中每一行的图片数量（码数）
        
        Args:
            file_content: 文件内容（bytes或file-like对象）
            file_name: 文件名
            header_row: 列名所在行（0-based索引）
            
        Returns:
            字典 {行号: 图片数量}（行号是pandas DataFrame的索引，0-based）
        """
        try:
            # 重置文件指针
            if hasattr(file_content, 'seek'):
                file_content.seek(0)
            
            # 如果是file-like对象，需要读取到BytesIO
            if hasattr(file_content, 'read'):
                content = file_content.read()
                if hasattr(file_content, 'seek'):
                    file_content.seek(0)  # 重置，供后续使用
                file_obj = io.BytesIO(content)
            else:
                file_obj = io.BytesIO(file_content)
            
            # 使用openpyxl读取（支持超链接）
            wb = load_workbook(file_obj, data_only=False)
            ws = wb.active
            
            # 获取列名（header_row是0-based，但openpyxl使用1-based）
            openpyxl_header_row = header_row + 1
            headers = []
            for col_idx in range(1, ws.max_column + 1):
                cell = ws.cell(row=openpyxl_header_row, column=col_idx)
                headers.append(cell.value)
            
            # 找到昵称列索引
            nickname_col = None
            for idx, header in enumerate(headers, 1):
                if header:
                    for keyword in self.NICKNAME_KEYWORDS:
                        if keyword in str(header):
                            nickname_col = idx
                            break
                if nickname_col:
                    break
            
            if nickname_col is None:
                wb.close()
                return {}
            
            # 找到所有图片相关的列索引（排除"订正图片"）
            image_cols = []
            for idx, header in enumerate(headers, 1):
                if header and '图片' in str(header):
                    # 排除订正图片，只统计上传的截图
                    if '订正' not in str(header):
                        # 检查是否是编号的图片列（图片1, 图片2...）
                        header_str = str(header).strip()
                        if re.search(r'图片\d+', header_str):
                            image_cols.append(idx)
            
            # 统计每行的图片数量（不按昵称累加，保留每行的原始数据）
            row_image_count = {}
            
            for row_idx in range(openpyxl_header_row + 1, ws.max_row + 1):
                # 统计该行的图片数量（只统计有超链接的）
                image_count = 0
                for col_idx in image_cols:
                    cell = ws.cell(row=row_idx, column=col_idx)
                    # 只有当单元格有超链接时，才算作有效图片
                    if cell.hyperlink is not None:
                        image_count += 1
                
                # 保存该行的图片数（row_idx是openpyxl的行号，需要转换为DataFrame的索引）
                # openpyxl行号从1开始，减去header_row+1得到DataFrame的0-based索引
                df_row_idx = row_idx - openpyxl_header_row - 1
                row_image_count[df_row_idx] = image_count
            
            wb.close()
            return row_image_count
            
        except Exception as e:
            # 如果统计失败，返回空字典（后续会使用默认码数1）
            return {}
    
    def extract_nicknames_and_times_from_file(self, file_content, file_name: str) -> Tuple[List[str], List[str], List[str], List[int], str]:
        """
        从Excel文件内容中提取昵称、姓名、提交时间和图片数量（码数）
        
        Args:
            file_content: 文件内容（bytes或file-like对象）
            file_name: 文件名
            
        Returns:
            (昵称列表, 姓名列表, 提交时间列表, 图片数量列表, 错误信息)
        """
        try:
            # 重置文件指针（如果是file-like对象）
            if hasattr(file_content, 'seek'):
                file_content.seek(0)
            
            # 先尝试第1行为列名（header=0）
            header_row = 0
            if file_name.endswith('.xlsx'):
                df = pd.read_excel(file_content, engine='openpyxl', header=0)
            elif file_name.endswith('.xls'):
                df = pd.read_excel(file_content, engine='xlrd', header=0)
            else:
                return [], [], [], [], f"不支持的文件格式: {file_name}"
            
            if df.empty:
                return [], [], [], [], f"文件为空: {file_name}"
            
            # 查找昵称列
            nickname_column = self.find_nickname_column(df)
            
            # 如果第1行作为列名找不到昵称列，尝试第2行作为列名（header=1）
            if nickname_column is None:
                try:
                    # 重置文件指针再次读取
                    if hasattr(file_content, 'seek'):
                        file_content.seek(0)
                    
                    header_row = 1
                    if file_name.endswith('.xlsx'):
                        df = pd.read_excel(file_content, engine='openpyxl', header=1)
                    elif file_name.endswith('.xls'):
                        df = pd.read_excel(file_content, engine='xlrd', header=1)
                    
                    if not df.empty:
                        nickname_column = self.find_nickname_column(df)
                except Exception as e:
                    pass
            
            # 如果还是找不到昵称列，返回错误
            if nickname_column is None:
                # 返回可用列名供用户参考
                available_columns = ", ".join(df.columns.tolist())
                return [], [], [], [], f"未找到昵称列，可用列名: {available_columns}"
            
            # 查找姓名列（可选）
            name_column = self.find_name_column(df)
            
            # 查找时间列
            time_column = self.find_time_column(df)
            
            # 提取昵称、姓名和时间数据
            nicknames_raw = df[nickname_column].tolist()
            names_raw = df[name_column].tolist() if name_column else [""] * len(nicknames_raw)
            times_raw = df[time_column].tolist() if time_column else [None] * len(nicknames_raw)
            
            # 统计每行的图片数量（码数）
            row_image_count = self.count_images_in_excel(file_content, file_name, header_row)
            
            # 清理数据，保持昵称、姓名、时间和图片数量的对应关系
            # 注意：这里不去重，保留所有原始记录，让app.py根据需要决定如何分组
            nicknames_clean = []
            names_clean = []
            times_clean = []
            image_counts = []
            
            for row_idx, (nickname, name, time_val) in enumerate(zip(nicknames_raw, names_raw, times_raw)):
                clean_nickname = self.clean_nickname(nickname)
                if clean_nickname and len(clean_nickname) > 0:
                    clean_name = self.clean_nickname(name) if name and str(name) != 'nan' else ""
                    
                    nicknames_clean.append(clean_nickname)
                    names_clean.append(clean_name)
                    times_clean.append(str(time_val) if time_val is not None else "")
                    # 获取该行的图片数量（每一行独立统计）
                    image_count = row_image_count.get(row_idx, 1)
                    image_counts.append(image_count)
            
            return nicknames_clean, names_clean, times_clean, image_counts, ""
            
        except Exception as e:
            return [], [], [], [], f"处理文件 {file_name} 时出错: {str(e)}"
    
    def extract_nicknames_from_file(self, file_content, file_name: str) -> Tuple[List[str], str]:
        """
        从Excel文件内容中提取昵称（保持向后兼容）
        
        Args:
            file_content: 文件内容（bytes）
            file_name: 文件名
            
        Returns:
            (昵称列表, 错误信息)
        """
        nicknames, _, _, _, error = self.extract_nicknames_and_times_from_file(file_content, file_name)
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
            file_content: 文件内容（bytes或file-like对象）
            file_name: 文件名
            
        Returns:
            文件信息字典
        """
        try:
            # 重置文件指针（如果是file-like对象）
            if hasattr(file_content, 'seek'):
                file_content.seek(0)
            
            # 先尝试第1行为列名（header=0）
            if file_name.endswith('.xlsx'):
                df = pd.read_excel(file_content, engine='openpyxl', header=0)
            elif file_name.endswith('.xls'):
                df = pd.read_excel(file_content, engine='xlrd', header=0)
            else:
                return {"error": "不支持的文件格式"}
            
            nickname_column = self.find_nickname_column(df)
            
            # 如果第1行找不到昵称列，尝试第2行作为列名（header=1）
            if nickname_column is None:
                try:
                    # 重置文件指针再次读取
                    if hasattr(file_content, 'seek'):
                        file_content.seek(0)
                    
                    if file_name.endswith('.xlsx'):
                        df = pd.read_excel(file_content, engine='openpyxl', header=1)
                    elif file_name.endswith('.xls'):
                        df = pd.read_excel(file_content, engine='xlrd', header=1)
                    nickname_column = self.find_nickname_column(df)
                except:
                    pass
            
            return {
                "file_name": file_name,
                "total_rows": len(df),
                "total_columns": len(df.columns),
                "columns": df.columns.tolist(),
                "nickname_column": nickname_column
            }
            
        except Exception as e:
            return {"error": f"读取文件信息失败: {str(e)}"}
