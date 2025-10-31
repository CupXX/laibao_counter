"""
数据管理模块 - 支持多用户会话隔离
负责处理积分记录的JSON存储和读取，每个用户拥有独立的数据空间
"""
import json
import os
import uuid
import time
from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta


class DataManager:
    def __init__(self, session_id: Optional[str] = None, data_dir: str = "data"):
        """
        初始化数据管理器
        
        Args:
            session_id: 用户会话ID，如果为None则生成新的session ID
            data_dir: 数据目录路径
        """
        self.data_dir = data_dir
        self.session_id = session_id or self._generate_session_id()
        self.data_file = os.path.join(data_dir, f"records_{self.session_id}.json")
        self.ensure_data_file_exists()
    
    def _generate_session_id(self) -> str:
        """生成唯一的会话ID"""
        return str(uuid.uuid4())[:8] + "_" + str(int(time.time()))
    
    def get_session_id(self) -> str:
        """获取当前会话ID"""
        return self.session_id
    
    def ensure_data_file_exists(self):
        """确保数据文件和目录存在"""
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        if not os.path.exists(self.data_file):
            self.save_data({
                "records": {},
                "processed_files": {},  # 新增：记录已处理的文件
                "last_updated": datetime.now().isoformat(),
                "total_files_processed": 0
            })
    
    def load_data(self) -> Dict:
        """
        加载积分记录数据
        
        Returns:
            包含积分记录的字典
        """
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 确保数据结构包含所有必要字段（向后兼容）
            if "processed_files" not in data:
                data["processed_files"] = {}
                
            return data
        except (FileNotFoundError, json.JSONDecodeError):
            # 如果文件不存在或损坏，返回默认结构
            return {
                "records": {},
                "processed_files": {},  # 新增：记录已处理的文件
                "last_updated": datetime.now().isoformat(),
                "total_files_processed": 0
            }
    
    def save_data(self, data: Dict):
        """
        保存积分记录数据
        
        Args:
            data: 要保存的数据字典
        """
        data["last_updated"] = datetime.now().isoformat()
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def is_file_processed(self, file_name: str) -> bool:
        """
        检查文件是否已经处理过
        
        Args:
            file_name: 文件名
            
        Returns:
            是否已处理过
        """
        data = self.load_data()
        processed_files = data.get("processed_files", {})
        return file_name in processed_files
    
    def update_scores_with_rewards(self, nicknames: List[str], times: List[str], file_name: str = "", 
                                 weight: Union[int, List[int]] = 1, base_score: float = 1.0, 
                                 reward_count: int = 0, reward_multiplier: float = 1.5):
        """
        更新昵称积分（支持基于时间的奖励机制和每个昵称不同的码数）
        
        Args:
            nicknames: 昵称列表
            times: 对应的提交时间列表
            file_name: 文件名（用于记录）
            weight: 积分权重/码数，可以是int（统一码数）或List[int]（每个昵称不同的码数）
            base_score: 基础积分（默认为1.0）
            reward_count: 奖励人数（默认为0，不启用奖励）
            reward_multiplier: 奖励倍数（默认为1.5）
        """
        data = self.load_data()
        
        # 确保processed_files字段存在
        if "processed_files" not in data:
            data["processed_files"] = {}
        
        # 处理weight参数：可以是int或List[int]
        if isinstance(weight, int):
            # 统一码数：所有昵称使用相同的weight
            weights = [weight] * len(nicknames)
        else:
            # 每个昵称不同的码数
            weights = weight
            # 确保长度匹配
            if len(weights) != len(nicknames):
                raise ValueError(f"weights长度({len(weights)})与nicknames长度({len(nicknames)})不匹配")
        
        # 计算基础积分（暂时用平均weight计算，后面会用实际的weight）
        avg_weight = sum(weights) / len(weights) if weights else 1
        basic_points = base_score * avg_weight
        
        # 如果有奖励机制且提供了时间数据
        reward_users = set()
        if reward_count > 0 and times and any(t for t in times):
            # 创建昵称-时间对，过滤掉空时间
            time_pairs = [(nickname, time_str) for nickname, time_str in zip(nicknames, times) 
                         if time_str and str(time_str).strip() and str(time_str) != 'nan']
            
            if time_pairs:
                # 按时间排序（假设时间格式能够直接排序）
                try:
                    time_pairs.sort(key=lambda x: str(x[1]))
                    # 取前N名
                    reward_users = set([pair[0] for pair in time_pairs[:reward_count]])
                except:
                    # 如果排序失败，不给奖励
                    reward_users = set()
        
        # 计算总积分
        total_points = sum(base_score * w for w in weights)
        total_points += len(reward_users) * avg_weight * base_score * (reward_multiplier - 1)
        
        # 记录已处理的文件（使用列表形式保存weights）
        data["processed_files"][file_name] = {
            "processed_date": datetime.now().isoformat(),
            "nicknames_count": len(nicknames),
            "weight": weight if isinstance(weight, int) else avg_weight,  # 向后兼容：保存int或平均值
            "weights": weights,  # 新字段：保存每个昵称的码数列表
            "base_score": base_score,
            "total_points": total_points,
            "reward_count": reward_count,
            "reward_multiplier": reward_multiplier,
            "rewarded_users": list(reward_users)
        }
        
        # 为每个昵称增加积分
        for idx, nickname in enumerate(nicknames):
            if nickname.strip():
                nickname = nickname.strip()
                
                # 获取该昵称的实际码数
                user_weight = weights[idx]
                user_basic_points = base_score * user_weight
                
                # 计算该用户获得的积分
                user_points = user_basic_points
                is_rewarded = nickname in reward_users
                if is_rewarded:
                    user_points = reward_multiplier * user_basic_points
                
                if nickname in data["records"]:
                    data["records"][nickname]["score"] += user_points
                    data["records"][nickname]["files"].append({
                        "file_name": file_name,
                        "date": datetime.now().isoformat(),
                        "weight": user_weight,  # 使用该昵称的实际码数
                        "base_score": base_score,
                        "points": user_points,
                        "is_rewarded": is_rewarded
                    })
                else:
                    data["records"][nickname] = {
                        "score": user_points,
                        "files": [{
                            "file_name": file_name,
                            "date": datetime.now().isoformat(),
                            "weight": user_weight,  # 使用该昵称的实际码数
                            "base_score": base_score,
                            "points": user_points,
                            "is_rewarded": is_rewarded
                        }]
                    }
        
        data["total_files_processed"] += 1
        self.save_data(data)
        
        return len(reward_users)  # 返回获得奖励的人数
    
    def update_scores(self, nicknames: List[str], file_name: str = "", weight: int = 1):
        """
        更新昵称积分（保持向后兼容）
        
        Args:
            nicknames: 昵称列表
            file_name: 文件名（用于记录）
            weight: 积分权重/码数（默认为1）
        """
        return self.update_scores_with_rewards(nicknames, [], file_name, weight)
    
    def update_existing_file_scores(self, nicknames: List[str], file_name: str, new_weight: int):
        """
        更新已处理文件的积分（当码数发生变化时）
        
        Args:
            nicknames: 昵称列表
            file_name: 文件名
            new_weight: 新的权重/码数
        """
        data = self.load_data()
        
        # 获取旧的权重
        old_weight = 1
        if file_name in data.get("processed_files", {}):
            old_weight = data["processed_files"][file_name].get("weight", 1)
        
        # 计算权重差异
        weight_diff = new_weight - old_weight
        
        # 更新文件记录
        data["processed_files"][file_name] = {
            "processed_date": datetime.now().isoformat(),
            "nicknames_count": len(nicknames),
            "weight": new_weight,
            "total_points": len(nicknames) * new_weight
        }
        
        # 更新每个昵称的积分
        for nickname in nicknames:
            if nickname.strip():
                nickname = nickname.strip()
                if nickname in data["records"]:
                    # 更新总积分
                    data["records"][nickname]["score"] += weight_diff
                    
                    # 查找并更新这个文件的记录
                    for file_record in data["records"][nickname]["files"]:
                        if file_record["file_name"] == file_name:
                            file_record["weight"] = new_weight
                            file_record["points"] = new_weight
                            file_record["date"] = datetime.now().isoformat()
                            break
                    else:
                        # 如果没有找到对应文件记录，添加新记录
                        data["records"][nickname]["files"].append({
                            "file_name": file_name,
                            "date": datetime.now().isoformat(),
                            "weight": new_weight,
                            "points": new_weight
                        })
                else:
                    # 如果昵称不存在（理论上不应该发生），创建新记录
                    data["records"][nickname] = {
                        "score": new_weight,
                        "files": [{
                            "file_name": file_name,
                            "date": datetime.now().isoformat(),
                            "weight": new_weight,
                            "points": new_weight
                        }]
                    }
        
        self.save_data(data)
    
    def get_leaderboard(self) -> List[Dict]:
        """
        获取积分排行榜
        
        Returns:
            按积分降序排列的昵称列表
        """
        data = self.load_data()
        leaderboard = []
        
        for nickname, info in data["records"].items():
            leaderboard.append({
                "nickname": nickname,
                "score": info["score"],
                "participation_count": len(info["files"])  # 参与接龙次数：参与的文件数量
            })
        
        # 按积分降序排列
        leaderboard.sort(key=lambda x: x["score"], reverse=True)
        return leaderboard
    
    def get_statistics(self) -> Dict:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        data = self.load_data()
        return {
            "total_participants": len(data["records"]),
            "total_files_processed": data["total_files_processed"],
            "last_updated": data["last_updated"],
            "total_checkins": sum(info["score"] for info in data["records"].values())
        }
    
    def backup_data(self) -> str:
        """
        创建数据备份
        
        Returns:
            备份文件路径
        """
        data = self.load_data()
        backup_file = os.path.join(self.data_dir, f"backup_{self.session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return backup_file
    
    def export_user_data(self) -> bytes:
        """
        导出用户数据为JSON字节流（用于下载）
        
        Returns:
            JSON数据的字节流
        """
        data = self.load_data()
        data['exported_at'] = datetime.now().isoformat()
        data['session_id'] = self.session_id
        
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        return json_str.encode('utf-8')
    
    @staticmethod
    def cleanup_old_sessions(data_dir: str = "data", max_age_hours: int = 24):
        """
        清理过期的会话数据文件
        
        Args:
            data_dir: 数据目录
            max_age_hours: 最大保留小时数
        """
        if not os.path.exists(data_dir):
            return
            
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        for filename in os.listdir(data_dir):
            if filename.startswith('records_') and filename.endswith('.json'):
                file_path = os.path.join(data_dir, filename)
                
                try:
                    # 获取文件修改时间
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    # 如果文件过期，删除它
                    if file_mtime < cutoff_time:
                        os.remove(file_path)
                        print(f"已清理过期会话文件: {filename}")
                        
                except Exception as e:
                    print(f"清理文件 {filename} 时出错: {str(e)}")
    
    @staticmethod
    def get_active_sessions(data_dir: str = "data") -> List[Dict]:
        """
        获取活跃的会话信息
        
        Args:
            data_dir: 数据目录
            
        Returns:
            会话信息列表
        """
        sessions = []
        
        if not os.path.exists(data_dir):
            return sessions
            
        for filename in os.listdir(data_dir):
            if filename.startswith('records_') and filename.endswith('.json'):
                file_path = os.path.join(data_dir, filename)
                
                try:
                    # 从文件名提取session ID
                    session_id = filename[8:-5]  # 去掉 'records_' 前缀和 '.json' 后缀
                    
                    # 获取文件信息
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    file_size = os.path.getsize(file_path)
                    
                    sessions.append({
                        'session_id': session_id,
                        'last_modified': file_mtime.isoformat(),
                        'file_size': file_size,
                        'file_path': file_path
                    })
                    
                except Exception as e:
                    print(f"读取会话信息 {filename} 时出错: {str(e)}")
        
        # 按最后修改时间降序排序
        sessions.sort(key=lambda x: x['last_modified'], reverse=True)
        return sessions
    
    def import_data(self, import_file_path: str) -> bool:
        """
        从备份文件导入数据
        
        Args:
            import_file_path: 要导入的备份文件路径
            
        Returns:
            导入是否成功
        """
        try:
            # 读取导入文件
            with open(import_file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # 验证数据结构
            required_fields = ["records", "processed_files", "last_updated", "total_files_processed"]
            for field in required_fields:
                if field not in import_data:
                    raise ValueError(f"导入文件缺少必要字段: {field}")
            
            # 确保processed_files字段存在（向后兼容）
            if "processed_files" not in import_data:
                import_data["processed_files"] = {}
            
            # 保存导入的数据
            self.save_data(import_data)
            
            return True
            
        except Exception as e:
            print(f"导入数据时出错: {str(e)}")
            return False
    
    def validate_backup_file(self, file_path: str) -> tuple[bool, str]:
        """
        验证备份文件是否有效
        
        Args:
            file_path: 备份文件路径
            
        Returns:
            (是否有效, 错误信息)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查必要字段
            required_fields = ["records", "last_updated", "total_files_processed"]
            for field in required_fields:
                if field not in data:
                    return False, f"缺少必要字段: {field}"
            
            # 检查数据类型
            if not isinstance(data["records"], dict):
                return False, "records字段格式错误"
            
            if not isinstance(data["total_files_processed"], int):
                return False, "total_files_processed字段格式错误"
            
            return True, "文件格式正确"
            
        except json.JSONDecodeError:
            return False, "文件不是有效的JSON格式"
        except FileNotFoundError:
            return False, "文件不存在"
        except Exception as e:
            return False, f"验证文件时出错: {str(e)}"
    
    def get_processed_files(self) -> List[Dict]:
        """
        获取所有已处理的文件列表
        
        Returns:
            已处理文件列表，按处理时间降序排列
        """
        data = self.load_data()
        processed_files = data.get("processed_files", {})
        
        files_list = []
        for file_name, info in processed_files.items():
            files_list.append({
                "file_name": file_name,
                "processed_date": info["processed_date"],
                "nicknames_count": info["nicknames_count"],
                "weight": info.get("weight", 1),  # 向后兼容，默认为1
                "base_score": info.get("base_score", 1.0),  # 向后兼容，默认为1.0
                "total_points": info.get("total_points", info["nicknames_count"]),  # 向后兼容
                "reward_count": info.get("reward_count", 0),  # 向后兼容，默认为0
                "reward_multiplier": info.get("reward_multiplier", 1.0),  # 向后兼容，默认为1.0
                "rewarded_users": info.get("rewarded_users", [])  # 向后兼容，默认为空列表
            })
        
        # 按处理时间降序排列（最新的在前面）
        files_list.sort(key=lambda x: x["processed_date"], reverse=True)
        return files_list
