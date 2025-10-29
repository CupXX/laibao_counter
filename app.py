"""
来豹接龙打卡记录统计工具 - Streamlit主应用
"""
import streamlit as st
import pandas as pd
from data_manager import DataManager
from excel_processor import ExcelProcessor
from datetime import datetime
import io


def init_session_state():
    """初始化会话状态"""
    # 为每个用户会话生成唯一ID
    if 'user_session_id' not in st.session_state:
        st.session_state.user_session_id = None
    
    # 创建基于会话ID的数据管理器
    if 'data_manager' not in st.session_state:
        st.session_state.data_manager = DataManager(session_id=st.session_state.user_session_id)
        st.session_state.user_session_id = st.session_state.data_manager.get_session_id()
        
    if 'excel_processor' not in st.session_state:
        st.session_state.excel_processor = ExcelProcessor()
    
    # 在页面加载时清理过期会话（24小时后过期）
    if 'cleanup_done' not in st.session_state:
        DataManager.cleanup_old_sessions(max_age_hours=24)
        st.session_state.cleanup_done = True


def display_statistics():
    """显示统计信息"""
    stats = st.session_state.data_manager.get_statistics()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("总参与人数", stats['total_participants'])
    
    with col2:
        st.metric("处理文件数", stats['total_files_processed'])
    
    with col3:
        if stats['last_updated']:
            last_update = datetime.fromisoformat(stats['last_updated'])
            st.metric("最后更新", last_update.strftime("%m-%d %H:%M"))


def display_leaderboard():
    """显示积分排行榜"""
    
    leaderboard = st.session_state.data_manager.get_leaderboard()
    
    if not leaderboard:
        st.info("还没有积分记录，请先上传Excel文件。")
        return
    
    # 创建排行榜DataFrame
    df = pd.DataFrame(leaderboard)
    df.index = range(1, len(df) + 1)  # 从1开始的排名
    
    # 添加参与接龙次数（纯计数，不考虑权重和奖励）
    if 'participation_count' in df.columns:
        df = df[['nickname', 'score', 'participation_count']]
        df.columns = ['昵称', '积分', '参与接龙次数']
    else:
        df = df[['nickname', 'score']]
        df.columns = ['昵称', '积分']
    
    # 使用列布局：左侧排行榜，右侧预留空间
    col1, col2 = st.columns([1, 1])  # 1:1的比例，各占50%宽度
    
    with col1:
        st.subheader("📊 积分排行榜")
        # 显示排行榜（左侧）
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=False,
        height=600
    )

    with col2:
        st.subheader("📊 已处理文件列表")
        # 右侧区域：已处理文件列表
        processed_files = st.session_state.data_manager.get_processed_files()
        
        if processed_files:
            # 创建已处理文件的DataFrame
            processed_df_data = []
            for file_info in processed_files:
                processed_date = datetime.fromisoformat(file_info["processed_date"])
                weight = file_info.get("weight", 1)
                base_score = file_info.get("base_score", 1.0)
                total_points = file_info.get("total_points", file_info["nicknames_count"])
                reward_count = file_info.get("reward_count", 0)
                reward_multiplier = file_info.get("reward_multiplier", 1.0)
                rewarded_users = file_info.get("rewarded_users", [])
                
                # 构建奖励信息
                reward_info = ""
                if reward_count > 0 and len(rewarded_users) > 0:
                    reward_info = f"前{len(rewarded_users)}名×{reward_multiplier}"
                
                processed_df_data.append({
                    "已处理文件": file_info["file_name"],
                    "处理时间": processed_date.strftime("%m-%d %H:%M"),
                    "昵称数": file_info["nicknames_count"],
                    "码数": weight,
                    "奖励": reward_info if reward_info else "-",
                    "总积分": total_points
                })
            
            if processed_df_data:
                processed_df = pd.DataFrame(processed_df_data)
                # 使用与左侧相同的高度，让两个表格对齐
                st.dataframe(
                    processed_df,
                    use_container_width=True,
                    hide_index=True,
                    height=600
                )
        else:
            # 如果没有文件，显示一个占位的dataframe来保持对齐
            empty_df = pd.DataFrame({
                "文件名": ["暂无文件"],
                "处理时间": [""],
                "昵称数": [""],
                "码数": [""],
                "奖励": [""],
                "总积分": [""]
            })
            st.dataframe(
                empty_df,
                use_container_width=True,
                hide_index=True,
                height=600
            )

def process_uploaded_files(uploaded_files, file_weights=None):
    """处理上传的文件"""
    if not uploaded_files:
        return
    
    if file_weights is None:
        file_weights = {file.name: 1 for file in uploaded_files}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_files = len(uploaded_files)
    new_files_count = 0
    old_files_count = 0
    updated_files_count = 0
    successful_count = 0
    total_new_nicknames = 0
    total_weighted_points = 0
    
    for i, uploaded_file in enumerate(uploaded_files):
        progress = (i + 1) / total_files
        progress_bar.progress(progress)
        status_text.text(f"正在处理: {uploaded_file.name} ({i+1}/{total_files})")
        
        # 检查是否已经处理过，以及码数或奖励机制是否有变化
        is_processed = st.session_state.data_manager.is_file_processed(uploaded_file.name)
        if is_processed:
            # 获取文件的当前码数和历史码数
            current_weight = file_weights.get(uploaded_file.name, 1)
            processed_files = st.session_state.data_manager.get_processed_files()
            historical_weight = 1
            historical_base_score = 1.0
            historical_reward_count = 0
            historical_reward_multiplier = 1.5
            
            for pf in processed_files:
                if pf['file_name'] == uploaded_file.name:
                    historical_weight = pf.get('weight', 1)
                    historical_base_score = pf.get('base_score', 1.0)
                    historical_reward_count = pf.get('reward_count', 0)
                    historical_reward_multiplier = pf.get('reward_multiplier', 1.5)
                    break
            
            # 获取当前奖励设置
            current_base_score = st.session_state.get('base_score', 1.0)
            current_reward_count = st.session_state.get('reward_count', 0)
            current_reward_multiplier = st.session_state.get('reward_multiplier', 1.5)
            
            # 检查是否有变化
            weight_changed = current_weight != historical_weight
            reward_changed = (current_base_score != historical_base_score or 
                            current_reward_count != historical_reward_count or 
                            current_reward_multiplier != historical_reward_multiplier)
            
            # 如果码数和奖励机制都没有变化，跳过处理
            if not weight_changed and not reward_changed:
                old_files_count += 1
                st.info(f"⏭️ {uploaded_file.name} - 已处理过，码数和奖励机制未变化，跳过")
                continue
            else:
                # 有变化，显示变化信息
                changes = []
                if weight_changed:
                    changes.append(f"码数: {historical_weight} → {current_weight}")
                if reward_changed:
                    changes.append(f"奖励机制: {historical_base_score}/{historical_reward_count}/{historical_reward_multiplier} → {current_base_score}/{current_reward_count}/{current_reward_multiplier}")
                st.info(f"🔄 {uploaded_file.name} - 检测到变化: {', '.join(changes)}")
                updated_files_count += 1
        
        # 验证文件格式
        if not st.session_state.excel_processor.validate_file_format(uploaded_file.name):
            st.error(f"不支持的文件格式: {uploaded_file.name}")
            continue
        
        # 处理文件，提取昵称和时间
        nicknames, times, error_msg = st.session_state.excel_processor.extract_nicknames_and_times_from_file(
            uploaded_file, uploaded_file.name
        )
        
        if error_msg:
            st.error(f"处理文件 {uploaded_file.name} 时出错: {error_msg}")
            continue
        
        if nicknames:
            # 获取该文件的码数
            weight = file_weights.get(uploaded_file.name, 1)
            
            # 判断是新文件还是更新文件
            is_update = st.session_state.data_manager.is_file_processed(uploaded_file.name)
            
            # 获取奖励设置
            base_score = st.session_state.get('base_score', 1.0)
            reward_count = st.session_state.get('reward_count', 0)
            reward_multiplier = st.session_state.get('reward_multiplier', 1.5)
            
            if is_update:
                # 更新已处理文件的积分（支持码数和奖励机制更新）
                # 检查是否有奖励机制变化
                processed_files = st.session_state.data_manager.get_processed_files()
                historical_base_score = 1.0
                historical_reward_count = 0
                historical_reward_multiplier = 1.5
                
                for pf in processed_files:
                    if pf['file_name'] == uploaded_file.name:
                        historical_base_score = pf.get('base_score', 1.0)
                        historical_reward_count = pf.get('reward_count', 0)
                        historical_reward_multiplier = pf.get('reward_multiplier', 1.5)
                        break
                
                # 如果奖励机制有变化，使用新的奖励机制重新计算
                if (base_score != historical_base_score or 
                    reward_count != historical_reward_count or 
                    reward_multiplier != historical_reward_multiplier):
                    # 使用新的奖励机制重新计算
                    rewarded_count = st.session_state.data_manager.update_scores_with_rewards(
                        nicknames, times, uploaded_file.name, weight, 
                        base_score, reward_count, reward_multiplier
                    )
                else:
                    # 只有码数变化，使用原有方法
                    st.session_state.data_manager.update_existing_file_scores(nicknames, uploaded_file.name, weight)
                    rewarded_count = 0
                
                updated_files_count += 1
            else:
                # 新文件，使用新的积分计算和奖励机制
                rewarded_count = st.session_state.data_manager.update_scores_with_rewards(
                    nicknames, times, uploaded_file.name, weight, 
                    base_score, reward_count, reward_multiplier
                )
                new_files_count += 1
            
            successful_count += 1
            total_new_nicknames += len(nicknames)
            total_weighted_points += len(nicknames) * weight
            
            # 显示文件处理结果
            weight_info = f" (码数: {weight})" if weight != 1 else ""
            basic_score = base_score * weight
            with st.expander(f"✅ {uploaded_file.name} - 提取了 {len(nicknames)} 个昵称{weight_info}"):
                st.write("提取的昵称:")
                nickname_df = pd.DataFrame({"昵称": nicknames})
                st.dataframe(nickname_df, hide_index=True, height=300)
                
                # 显示积分计算信息
                st.info(f"💰 基础积分: {base_score} × 码数: {weight} = {basic_score} 分/人")
                if rewarded_count > 0:
                    reward_score = reward_multiplier * basic_score
                    st.success(f"🏆 前 {rewarded_count} 名获得奖励: {reward_score} 分/人 (奖励倍数: {reward_multiplier}x)")
                    total_points = (len(nicknames) - rewarded_count) * basic_score + rewarded_count * reward_score
                    st.info(f"📊 本文件总积分: {total_points} 分")
                else:
                    total_points = len(nicknames) * basic_score
                    st.info(f"📊 本文件总积分: {total_points} 分")
        else:
            st.warning(f"文件 {uploaded_file.name} 中没有找到有效的昵称数据")
    
    progress_bar.empty()
    status_text.empty()
    
    # 显示处理结果摘要
    if new_files_count > 0 or old_files_count > 0 or updated_files_count > 0:
        result_msg = []
        if new_files_count > 0:
            result_msg.append(f"✅ 处理了 {new_files_count} 个新文件")
        if updated_files_count > 0:
            result_msg.append(f"🔄 更新了 {updated_files_count} 个文件的码数")
        if old_files_count > 0:
            result_msg.append(f"⏭️ 跳过了 {old_files_count} 个未变化的文件")
        if total_new_nicknames > 0:
            result_msg.append(f"处理了 {total_new_nicknames} 个昵称记录")
        if total_weighted_points > total_new_nicknames:
            result_msg.append(f"加权后共产生 {total_weighted_points} 积分")
        
        if new_files_count > 0 or updated_files_count > 0:
            st.success(" | ".join(result_msg))
            # 不在这里rerun，让main函数控制
        else:
            st.info(" | ".join(result_msg))
    else:
        st.error("没有成功处理任何文件")


def main():
    """主函数"""
    st.set_page_config(
        page_title="来豹接龙打卡记录统计工具",
        page_icon="📊",
        layout="wide"
    )
    
    # 添加CSS隐藏默认文件上传组件的文件列表
    st.markdown("""
    <style>
    .uploadedFile {
        display: none !important;
    }
    .uploadedFileName {
        display: none !important;
    }
    div[data-testid="stFileUploaderDropzone"] div[data-testid="stMarkdownContainer"] {
        display: none !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    init_session_state()
    
    # 初始化文件处理状态
    if 'files_processed' not in st.session_state:
        st.session_state.files_processed = False
    if 'uploaded_files_key' not in st.session_state:
        st.session_state.uploaded_files_key = 0
    
    # 页面标题
    st.title("📊 来豹接龙打卡记录统计工具")
    
    # 使用说明
    st.subheader("📖 使用说明")
    
    # 使用列布局：左侧说明，右侧图片
    col1, col2 = st.columns([2, 1])  # 左侧占2/3，右侧占1/3
    
    with col1:
        st.markdown("""
        <div style="font-size: 22px; line-height: 1.8;">
        1. <strong>设置奖励机制</strong>: 在左侧侧边栏，设置基础积分、奖励人数、奖励倍数。<br>
        2. <strong>导出数据</strong>: 在来豹接龙小程序中，导出数据（不要插入图片！！），可以参考右图，时间选择全部。<br>
        3. <strong>上传Excel文件</strong>:将导出的Excel文件拖到下方，上传接龙数据。（支持多个文件同时上传）<br>
        4. <strong>设置码数</strong>: 设置每个接龙的码数，默认为1，可自行修改，设置好后点击开始处理按钮，即可自动计算积分。<br>
        5. <strong>查看排行榜</strong>: 在主页面下方可查看积分排行榜和已处理文件列表。<br>
        6. <strong>下载积分表格</strong>: 点击积分排行榜右上方的下载按钮可以下载当前的排行榜数据。<br>
        7. <strong>备份数据</strong>: 在左侧侧边栏，点击【下载我的数据】，即可备份所有处理历史记录，保存为json文件。<br>
        8. <strong>上传数据</strong>: 再次使用时，把保存的json文件拖到【上传数据】区域，即可上传之前备份的数据，继续编辑。
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        # 导入示意图
        st.image("data/示意图.png", caption="导出数据设置示意图", width=200)
    st.markdown("---")
    
    # 文件上传区域
    st.subheader("📤 上传接龙数据")
    
    # 使用key来控制文件上传器的重置
    uploaded_files = st.file_uploader(
        "选择Excel文件 (支持 .xlsx 和 .xls 格式)",
        accept_multiple_files=True,
        type=['xlsx', 'xls'],
        help="可以同时上传多个Excel文件进行批量处理",
        key=f"file_uploader_{st.session_state.uploaded_files_key}"
    )
    
    # 重置文件处理状态
    if not uploaded_files:
        st.session_state.files_processed = False
    
    # 如果有上传的文件，显示自定义的完整文件列表
    if uploaded_files and not st.session_state.files_processed:
        st.subheader(f"📋 已选择 {len(uploaded_files)} 个文件")
        
        # 创建文件列表的DataFrame来更好地显示
        file_info = []
        new_file_count = 0
        old_file_count = 0
        
        for i, file in enumerate(uploaded_files, 1):
            file_size = len(file.getvalue()) / 1024  # 转换为KB
            is_processed = st.session_state.data_manager.is_file_processed(file.name)
            
            if is_processed:
                old_file_count += 1
                status = "🔄 已处理"
                # 获取已处理文件的历史码数
                processed_files = st.session_state.data_manager.get_processed_files()
                historical_weight = 1
                for pf in processed_files:
                    if pf['file_name'] == file.name:
                        historical_weight = pf.get('weight', 1)
                        break
                default_weight = historical_weight
            else:
                new_file_count += 1
                status = "🆕 新文件"
                default_weight = 1
                
            file_info.append({
                "序号": i,
                "文件名": file.name,
                "大小": f"{file_size:.1f} KB",
                "状态": status,
                "码数": default_weight
            })
        
        file_df = pd.DataFrame(file_info)
        
        # 使用可编辑的数据表格，让用户能修改码数
        st.write("💡 提示：")
        st.write("- 如果上传已处理文件：可重新修改码数或奖励机制，如有变化将重新计算积分")
        
        edited_df = st.data_editor(
            file_df,
            use_container_width=True,
            hide_index=True,
            height=min(400, len(uploaded_files) * 35 + 50),
            column_config={
                "序号": st.column_config.NumberColumn(
                    "序号",
                    disabled=True,
                    width="small"
                ),
                "文件名": st.column_config.TextColumn(
                    "文件名",
                    disabled=True,
                    width="large"
                ),
                "大小": st.column_config.TextColumn(
                    "大小",
                    disabled=True,
                    width="small"
                ),
                "状态": st.column_config.TextColumn(
                    "状态",
                    disabled=True,
                    width="small"
                ),
                "码数": st.column_config.NumberColumn(
                    "码数",
                    help="积分倍数，必须是正整数",
                    min_value=1,
                    max_value=100,
                    step=1,
                    format="%d",
                    width="small"
                )
            },
            disabled=["序号", "文件名", "大小", "状态"]
        )
        
        # 显示统计信息
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("新文件", new_file_count)
        with col2:
            st.metric("已处理", old_file_count)
        with col3:
            st.metric("总计", len(uploaded_files))
        
        if st.button("🚀 开始处理", type="primary"):
            # 创建文件和码数的映射
            file_weights = {}
            for _, row in edited_df.iterrows():
                file_weights[row["文件名"]] = int(row["码数"])
            
            process_uploaded_files(uploaded_files, file_weights)
            st.session_state.files_processed = True
            # 重置文件上传器
            st.session_state.uploaded_files_key += 1
            # 清理导入数据的session state，防止重新显示
            if 'backup_uploader' in st.session_state:
                del st.session_state['backup_uploader']
            st.rerun()
    
    st.markdown("---")
    
    # 显示排行榜
    display_leaderboard()
    
    # 在排行榜下方显示统计信息
    st.markdown("---")
    display_statistics()
    
    # 侧边栏 - 设置和管理功能
    with st.sidebar:
        # 设置奖励机制
        st.header("🏆 设置奖励")
        
        # 初始化奖励设置的session state
        if 'base_score' not in st.session_state:
            st.session_state.base_score = 1
        if 'reward_count' not in st.session_state:
            st.session_state.reward_count = 0  
        if 'reward_multiplier' not in st.session_state:
            st.session_state.reward_multiplier = 1.5
        
        # 基础积分设置
        base_score = st.number_input(
            "基础积分",
            min_value=0.1,
            max_value=100.0,
            value=float(st.session_state.base_score),
            step=0.1,
            format="%.1f",
            help="用于计算积分的基础值"
        )
        st.session_state.base_score = base_score
        
        # 奖励人数设置
        reward_count = st.number_input(
            "奖励人数",
            min_value=0,
            max_value=100,
            value=st.session_state.reward_count,
            step=1,
            help="排行榜前几名获得奖励倍数（0表示不启用奖励）"
        )
        st.session_state.reward_count = reward_count
        
        # 奖励倍数设置
        reward_multiplier = st.number_input(
            "奖励倍数", 
            min_value=1.0,
            max_value=10.0,
            value=st.session_state.reward_multiplier,
            step=0.1,
            format="%.1f",
            help="前N名用户的积分乘以此倍数"
        )
        st.session_state.reward_multiplier = reward_multiplier
        
        # 显示当前奖励设置状态
        if reward_count > 0:
            st.success(f"🎯 奖励已启用：前 {reward_count} 名获得 {reward_multiplier}x 倍数")
        else:
            st.info("💡 奖励未启用（奖励人数为0）")
        
        st.markdown("---")
        
        # 数据管理功能
        st.header("💾 数据管理")
        if st.button("🗑️ 清空所有数据", type="secondary", help="此操作将清空所有积分记录，请谨慎操作"):
            # 显示确认对话框
            if 'show_clear_confirm' not in st.session_state:
                st.session_state.show_clear_confirm = False
            
            st.session_state.show_clear_confirm = True
        
        # 确认对话框
        if st.session_state.get('show_clear_confirm', False):
            st.error("⚠️ 确认要清空所有数据吗？此操作无法恢复！")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 确认清空", type="primary"):
                    try:
                        # 清空数据
                        import os
                        data_file = "data/records.json"
                        if os.path.exists(data_file):
                            # 先备份
                            backup_file = st.session_state.data_manager.backup_data()
                            st.info(f"已自动备份到: {backup_file}")
                            
                            # 清空数据
                            empty_data = {
                                "records": {},
                                "processed_files": {},  # 也清空已处理文件记录
                                "last_updated": datetime.now().isoformat(),
                                "total_files_processed": 0
                            }
                            st.session_state.data_manager.save_data(empty_data)
                            
                            st.success("✅ 所有数据已清空！")
                            st.session_state.show_clear_confirm = False
                            st.rerun()
                        else:
                            st.warning("没有数据需要清空")
                            st.session_state.show_clear_confirm = False
                    except Exception as e:
                        st.error(f"清空数据失败: {str(e)}")
                        st.session_state.show_clear_confirm = False
            
            with col2:
                if st.button("❌ 取消操作"):
                    st.session_state.show_clear_confirm = False
                    st.rerun()
        
        if st.button("📁 下载我的数据", help="下载当前会话的所有积分记录"):
            try:
                # 导出用户数据
                user_data = st.session_state.data_manager.export_user_data()
                
                # 创建下载文件名
                download_filename = f"我的打卡统计_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
                st.download_button(
                    label="📁 点击下载",
                    data=user_data,
                    file_name=download_filename,
                    mime="application/json",
                    help="下载JSON格式的积分数据"
                )
                
            except Exception as e:
                st.error(f"导出数据失败: {str(e)}")

        # 数据上传功能
        st.subheader("📤 上传数据")
        
        # 文件上传器
        uploaded_backup = st.file_uploader(
            "选择备份文件，支持上传之前导出的JSON格式备份文件",
            type=['json'],
            help="请选择JSON格式的备份文件（通常以 .json 结尾）",
            key="backup_uploader"
        )
        if uploaded_backup is not None:
            try:
                # 读取上传的JSON文件
                file_content = uploaded_backup.read()
                import json
                backup_data = json.loads(file_content.decode('utf-8'))
                
                # 验证备份文件格式
                required_fields = ["records", "last_updated", "total_files_processed"]
                missing_fields = [field for field in required_fields if field not in backup_data]
                
                if missing_fields:
                    st.error(f"❌ 备份文件格式错误，缺少字段：{', '.join(missing_fields)}")
                    
                    with st.expander("📊 数据概览", expanded=True):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("参与人数", len(backup_data.get('records', {})))
                        with col2:
                            st.metric("处理文件数", backup_data.get('total_files_processed', 0))
                    
                    # 导入按钮
                    if st.button("📥 导入上传数据", type="primary", key="import_upload"):
                        try:
                            # 导入前先备份当前数据
                            current_backup = st.session_state.data_manager.backup_data()
                            st.info(f"当前数据已备份到: {current_backup}")
                            
                            # 临时保存上传的文件
                            import tempfile
                            import os
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                                json.dump(backup_data, temp_file, ensure_ascii=False, indent=2)
                                temp_path = temp_file.name
                            
                            # 执行导入
                            if st.session_state.data_manager.import_data(temp_path):
                                st.success("🎉 数据导入成功！页面将自动刷新...")
                                # 清理临时文件
                                os.unlink(temp_path)
                                # 清空上传文件状态，重置上传模块
                                if 'backup_uploader' in st.session_state:
                                    del st.session_state['backup_uploader']
                                st.rerun()
                            else:
                                st.error("❌ 数据导入失败")
                                os.unlink(temp_path)
                                
                        except Exception as e:
                            st.error(f"❌ 导入过程出错：{str(e)}")
                    
            except json.JSONDecodeError:
                st.error("❌ 文件格式错误，请确保是有效的JSON格式")
            except Exception as e:
                st.error(f"❌ 读取文件失败：{str(e)}")
        


if __name__ == "__main__":
    main()
