import streamlit as st
import requests
import json
import time # 用于模拟微小的延迟感，提升真实度
import os  # 新增：用于读取系统环境变量
from dotenv import load_dotenv
load_dotenv() # 自动加载同目录下的 .env 文件

# 尝试读取环境变量中的 API Key
# 如果读不到，就返回空字符串
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")

# --- 页面配置 ---
st.set_page_config(page_title="京东健康·智能问诊", layout="wide")
st.title("🏥 京东健康 · AI 智能分诊与问诊台")

# --- 初始化会话状态 (提前初始化，方便全局调用) ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = ""
if "profile_submitted" not in st.session_state:
    st.session_state.profile_submitted = False
if "profile_text" not in st.session_state:
    st.session_state.profile_text = ""
if "last_processed_index" not in st.session_state:
    st.session_state.last_processed_index = -1

# --- 侧边栏：配置与审核模式 ---
with st.sidebar:
    st.header("⚙️ 系统状态")

    # 优雅的演示交互：不显示明文 Key，只显示连接状态
    if DIFY_API_KEY:
        st.success("🟢 AI 问诊引擎已连接")
    else:
        st.error("🔴 AI 引擎未连接 (缺少 API Key)")
        st.caption("请在本地 .env 文件或 Render 环境变量中配置 DIFY_API_KEY")
    api_url = st.text_input("API Endpoint", value="https://api.dify.ai/v1/chat-messages")

    st.divider()
    st.header("🩺 医生协同")
    review_mode = st.checkbox("开启医生审核模式", value=True)
    st.info("开启后，AI 回复需经医生确认才发送给患者。")

    st.divider()
    # 【新增】为演示场景准备的重置按钮
    if st.button("🔄 重置当前对话与档案", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_id = ""
        st.session_state.profile_submitted = False
        st.session_state.profile_text = ""
        st.session_state.last_processed_index = -1
        st.rerun()

# --- 上部：结构化健康档案 (专业版分诊表单) ---
st.subheader("📋 预问诊分诊台")
st.markdown("<span style='color:gray; font-size:14px;'>请尽可能详细填写，AI 医生将根据这些信息为您提供更精准的建议。带 ⚠️ 为重要医疗安全项。</span>", unsafe_allow_html=True)

with st.form("profile_form", border=True):
    # 模块 1：人口统计学
    st.markdown("**👤 1. 基础信息**")
    col1, col2, col3 = st.columns(3)
    with col1:
        name = st.text_input("患者姓名", "张先生")
    with col2:
        gender = st.selectbox("性别", ["男", "女"])
    with col3:
        age = st.number_input("年龄", 1, 120, 55)

    st.divider() # 添加分割线让视觉更清爽

    # 模块 2：既往史与过敏史 (高优安全项)
    st.markdown("**🏥 2. 既往史与过敏史**")
    diseases = st.multiselect(
        "确诊慢性病 (可多选)", 
        ["无", "高血压", "2型糖尿病", "高脂血症", "冠心病", "脑卒中", "骨关节炎", "哮喘"],
        default=["无"]
    )
    
    # 过敏史采用：半结构化设计 (常见多选 + 兜底手填)
    col_alg1, col_alg2 = st.columns([1, 1])
    with col_alg1:
        allergies_common = st.multiselect(
            "常见过敏源 ⚠️", 
            ["无已知过敏", "青霉素类", "头孢类", "磺胺类药物", "花粉", "尘螨", "海鲜"], 
            default=["无已知过敏"],
            help="选择已知的过敏源，这关系到 AI 的用药和治疗建议安全。"
        )
    with col_alg2:
        allergies_other = st.text_input("其他过敏源补充", placeholder="若左侧未包含，请在此手填填写，例如：芒果")

    st.divider()

    # 模块 3：体征指标 (弱化强制性，增加引导)
    st.markdown("**📊 3. 近期体征指标 (选填)**")
    st.caption("💡 提示：如果不清楚具体数值，可以直接留空，不影响问诊。")
    col_bp, col_bs = st.columns(2)
    with col_bp:
        # 使用 help 增加提示，placeholder 提供占位符示例
        bp = st.text_input("血压数值 (mmHg)", placeholder="例: 120/80，不清楚可留空", help="正常成年人参考：收缩压 90-139，舒张压 60-89")
    with col_bs:
        sugar = st.text_input("空腹血糖 (mmol/L)", placeholder="例: 5.5，不清楚可留空", help="正常参考：3.9 - 6.1 mmol/L")

    st.divider()

    # 模块 4：主诉
    st.markdown("**🗣️ 4. 本次就诊诉求**")
    symptoms = st.text_area(
        "详细症状描述", 
        value="近期经常头晕，伴随后颈部僵硬，持续约一周。想咨询日常饮食和运动建议。",
        help="请尽量描述：哪里不舒服？持续了多久？有没有什么诱因？",
        height=100
    )
    
    # 按钮居中处理并增加视觉重要性
    submit_col1, submit_col2, submit_col3 = st.columns([1, 2, 1])
    with submit_col2:
        submitted = st.form_submit_button("🚀 生成结构化档案并呼叫 AI 医生", use_container_width=True)

# --- 处理表单提交的文本拼接逻辑更新 ---
if submitted:
    st.session_state.profile_submitted = True
    
    # 处理过敏史的文本拼接
    alg_list = [a for a in allergies_common if a != "无已知过敏"]
    if allergies_other.strip():
        alg_list.append(allergies_other.strip())
    final_allergy = "、".join(alg_list) if alg_list else "无已知药物及食物过敏"

    # 构建更符合医学语境的档案摘要
    profile_text = f"【基本信息】{name}，{gender}，{age}岁。\n"
    profile_text += f"【既往史】{', '.join(diseases) if diseases and '无' not in diseases else '体健，无特殊'}。\n"
    profile_text += f"【过敏史】{final_allergy}。\n"
    
    if bp.strip():
        profile_text += f"【近期血压】{bp} mmHg；"
    else:
        profile_text += f"【近期血压】患者表示不清楚；"
        
    if sugar.strip():
        profile_text += f"【空腹血糖】{sugar} mmol/L；"
        
    profile_text += f"\n【本次主诉】{symptoms}"

    st.session_state.profile_text = profile_text

    # 第一条隐式指令
    first_msg = f"医生你好，这是我的健康档案：\n{profile_text}\n请帮我分析目前的健康风险，并给出第一步建议。"
    if len(st.session_state.messages) == 0 or st.session_state.messages[-1].get("type") != "profile_init":
        st.session_state.messages.append({"role": "user", "content": first_msg, "type": "profile_init"})
        st.session_state.last_processed_index = len(st.session_state.messages) - 2
        st.rerun()

# --- 显示档案摘要 ---
if st.session_state.profile_submitted:
    with st.expander("📄 展开查看当前结构化档案", expanded=False):
        st.markdown(st.session_state.profile_text)
    st.divider()

# --- 下部：聊天窗口 ---
for i, message in enumerate(st.session_state.messages):
    if message.get("type") == "profile_init":
        with st.chat_message("user"):
            st.markdown(f"**📥 系统已向 AI 医生投递您的健康档案。**")
        continue

    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 核心逻辑：发送消息与调用 API ---
current_len = len(st.session_state.messages)

if current_len > st.session_state.last_processed_index and current_len > 0:
    new_msg = st.session_state.messages[-1]

    if new_msg["role"] == "user":
        user_input = new_msg["content"]
        is_first_interaction = new_msg.get("type") == "profile_init"

        with st.chat_message("assistant"):
            placeholder = st.empty()

            # 【交互优化】：根据是否是首次问诊，展示不同的动态提示
            if is_first_interaction:
                placeholder.markdown("📊 **主治医生正在研读您的健康档案，并检索最新临床指南...**")
            else:
                placeholder.markdown("💬 **医生正在结合您的情况思考回复...**")

            headers = {"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"}

            # 【核心修复区】：正确分离 inputs 和 conversation_id
            inputs_data = {
                "initial_profile": st.session_state.profile_text if st.session_state.profile_submitted else ""
            }

            payload = {
                "inputs": inputs_data,
                "query": user_input,
                "response_mode": "blocking",
                "user": "patient-001"
            }

            # 只有当 conversation_id 存在时才传入，告知 Dify 这是一个多轮对话
            if st.session_state.conversation_id:
                payload["conversation_id"] = st.session_state.conversation_id

            try:
                resp = requests.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                resp.raise_for_status()
                data = resp.json()

                ai_answer = data.get('answer', '抱歉，我暂时无法回答。')

                # 保存 Dify 返回的 conversation_id
                if data.get('conversation_id'):
                    st.session_state.conversation_id = data['conversation_id']

                # 【优化体验】：使用 st.form 包装医生审核逻辑
                if review_mode:
                    placeholder.markdown("⏳ **AI 已生成草稿，等待主治医生审核...**")
                    with st.form(key=f"review_form_{current_len}"):
                        st.write("👨‍⚕️ **医生审核台**")
                        edited_answer = st.text_area("修改 AI 建议（确认无误可直接批准）", value=ai_answer, height=150)

                        col_approve, col_edit = st.columns(2)
                        with col_approve:
                            approve_btn = st.form_submit_button("✅ 批准发送 (原内容)")
                        with col_edit:
                            edit_btn = st.form_submit_button("✏️ 修改后发送")

                        if approve_btn:
                            final_answer = ai_answer + "\n\n*(✅ 已由主治医生审核)*"
                            placeholder.markdown(final_answer)
                            st.session_state.messages.append({"role": "assistant", "content": final_answer})
                            st.session_state.last_processed_index = current_len
                            st.rerun()
                        elif edit_btn:
                            final_answer = edited_answer + "\n\n*(✏️ 已由主治医生修改)*"
                            placeholder.markdown(final_answer)
                            st.session_state.messages.append({"role": "assistant", "content": final_answer})
                            st.session_state.last_processed_index = current_len
                            st.rerun()
                else:
                    placeholder.markdown(ai_answer)
                    st.session_state.messages.append({"role": "assistant", "content": ai_answer})
                    st.session_state.last_processed_index = current_len

            except Exception as e:
                placeholder.error(f"❌ 请求失败，请检查 API 配置或网络。错误信息：{e}")
                st.session_state.last_processed_index = current_len

# --- 用户输入框 ---
if st.session_state.profile_submitted:
    if prompt := st.chat_input("请输入您想进一步咨询的问题..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()
else:
    st.info("👈 请先填写上方健康档案，开始问诊。")
