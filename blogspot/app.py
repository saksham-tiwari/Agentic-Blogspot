# Forced Reboot Trigger
import streamlit as st
import os
from datetime import datetime
import threading
import time
from queue import Queue
from dotenv import load_dotenv
load_dotenv() # Force reload environment variables on hot reload!
from blogspot.crew import Blogspot
from streamlit.runtime.scriptrunner import add_script_run_ctx

st.set_page_config(page_title="BlogSpot AI Platform", page_icon="✨", layout="wide")

# ==========================================
# UI Polish & Modern Styling
# ==========================================
st.markdown("""
<style>
    /* Dark mode gradient background */
    .stApp {
        background: radial-gradient(circle at 10% 20%, rgb(20, 20, 28) 0%, rgb(10, 10, 15) 100%);
        color: #e2e8f0;
    }
    
    /* Elegant Title */
    .main-title {
        font-size: 3.5rem;
        font-weight: 900;
        background: linear-gradient(to right, #60a5fa, #c084fc, #f472b6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
        padding-bottom: 10px;
    }
    
    .subtitle {
        font-size: 1.25rem;
        color: #94a3b8;
        margin-bottom: 2rem;
        font-weight: 300;
        letter-spacing: 0.5px;
    }
    
    /* Input Styling */
    .stTextInput input {
        background-color: rgba(255,255,255,0.03) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #fff !important;
        font-size: 1.1rem;
        padding: 15px 20px;
        border-radius: 12px;
        transition: all 0.3s ease;
    }
    
    .stTextInput input:focus {
        border-color: #c084fc !important;
        box-shadow: 0 0 15px rgba(192, 132, 252, 0.2) !important;
    }
    
    /* Primary Gradient Button */
    .stButton button {
        background: linear-gradient(135deg, #4f46e5, #9333ea) !important;
        border: none !important;
        color: white !important;
        font-weight: bold !important;
        border-radius: 12px !important;
        padding: 12px 24px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important;
    }
    
    .stButton button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 10px 20px rgba(147, 51, 234, 0.3) !important;
    }
    
    /* Telemetry Log Box */
    .log-box {
        background-color: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(148, 163, 184, 0.1);
        border-radius: 12px;
        padding: 20px;
        height: 400px;
        overflow-y: auto;
        font-family: 'Courier New', monospace;
        font-size: 0.85rem;
        color: #a78bfa;
        backdrop-filter: blur(10px);
        box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.06);
    }
    
    /* Artifact Container Box */
    .artifact-box {
        background-color: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 30px;
    }
    
    hr {
        border-color: rgba(255,255,255,0.1);
    }
</style>
""", unsafe_allow_html=True)

# ====== Initialization & State ======
if "logs" not in st.session_state:
    st.session_state.logs = []
if "generating" not in st.session_state:
    st.session_state.generating = False
if "complete" not in st.session_state:
    st.session_state.complete = False
if "output" not in st.session_state:
    st.session_state.output = ""

# ========= Core Functions =========
def run_crew_thread(topic_input, q):
    try:
        blog = Blogspot()
        
        # We manually track the sequence since we enforce Process.sequential
        task_tracker = {"count": 0}
        agent_sequence = ["🕵️ Senior Data Researcher", "📊 Reporting Analyst", "✍️ Senior Content Editor"]
        
        def step_callback(step):
            try:
                # Identify which agent is currently acting
                idx = min(task_tracker['count'], len(agent_sequence)-1)
                active_agent = agent_sequence[idx]
                
                tool_name = ""
                tool_query = ""
                thought = ""
                
                # Parse the complex LiteLLM / CrewAI Action Tuple
                if isinstance(step, tuple) and len(step) > 0:
                    action = step[0]
                    tool_name = getattr(action, 'tool', '')
                    tool_query = getattr(action, 'tool_input', '')
                    thought = getattr(action, 'log', '')
                else:
                    tool_name = getattr(step, 'tool', '')
                    tool_query = getattr(step, 'tool_input', '')
                    thought = getattr(step, 'log', '')
                
                # Dynamic Logic Parser to feed the UI
                if tool_name and ("Search" in str(tool_name) or "Serper" in str(tool_name)):
                    q.put(f"🌐 **[ {active_agent} ] accessing LIVE INTERNET:** Executing Google Search for `{tool_query}`...")
                elif thought:
                    clean_thought = thought.replace('`', '').strip()[:250]
                    q.put(f"🧠 **[ {active_agent} ] Internal Thought:**\n_{clean_thought}_...")
                else:
                    q.put(f"⚙️ **[ {active_agent} ]** synthesizing data arrays...")
            except Exception:
                pass # Silently drop parser errors to not interrupt the flow

        def task_callback(task_output):
            idx = min(task_tracker['count'], len(agent_sequence)-1)
            active_agent = agent_sequence[idx]
            
            q.put(f"✅ **MILESTONE COMPLETED:** {active_agent} has successfully finalized their assignment!")
            task_tracker["count"] += 1
            
            # Don't sleep on the very last task!
            if task_tracker["count"] < len(agent_sequence):
                next_agent = agent_sequence[task_tracker['count']]
                q.put(f"⏳ *Handing off memory context to {next_agent}. Throttling API flow for 20 seconds to bypass TPM limit...*")
                time.sleep(20)

        blog.step_callback = step_callback
        blog.task_callback = task_callback
        
        inputs = {'topic': topic_input, 'current_year': str(datetime.now().year)}
        q.put("🚀 **Crew Assembled. Handing prompt to the Senior Data Researcher...**")
        
        # This is a blocking process, which is why it's in a background thread
        res = blog.crew().kickoff(inputs=inputs)
        
        # Read the file if generating one
        if os.path.exists("report.md"):
            with open("report.md", "r") as f:
                content = f.read()
        else:
            content = str(res)
            
        q.put(f"FINISH|||{content}")
    except Exception as e:
        q.put(f"ERROR|||{str(e)}")

# ============ Layout ============
st.markdown('<div class="main-title">✨ BlogSpot AI Platform</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Command autonomous intelligent agents to research, draft, and optimize premium content in real-time.</div>', unsafe_allow_html=True)

topic = st.text_input("", placeholder="Enter your high-level topic... (e.g. 'The future of Quantum Computing in Healthcare')")

# Main columns layout
col1, space, col2 = st.columns([1.2, 0.1, 2])

with col1:
    st.markdown("### 🎛️ Control Panel")
    
    if st.button("🚀 Engage Agents", use_container_width=True):
        if not topic:
            st.error("Please provide a topic descriptor first.")
        else:
            st.session_state.generating = True
            st.session_state.complete = False
            st.session_state.logs = []
            st.session_state.output = ""
            st.rerun()

    if st.session_state.generating:
        st.markdown("---")
        st.markdown("### 📡 Live Telemetry")
        log_placeholder = st.empty()
        
        q = Queue()
        t = threading.Thread(target=run_crew_thread, args=(topic, q))
        # Important for streamlit context sharing in threads
        add_script_run_ctx(t)
        t.start()
        
        while t.is_alive() or not q.empty():
            while not q.empty():
                msg = q.get()
                if msg.startswith("FINISH|||"):
                    st.session_state.output = msg.split("|||", 1)[1]
                    st.session_state.complete = True
                    st.session_state.generating = False
                elif msg.startswith("ERROR|||"):
                    st.session_state.logs.append(f"❌ Error: {msg.split('|||', 1)[1]}")
                    st.session_state.generating = False
                else:
                    st.session_state.logs.append(msg)
            
            # Show formatted logs
            display_logs = "<br><br>".join(st.session_state.logs[-6:]) # Keep last 6 elements strictly
            log_placeholder.markdown(f'<div class="log-box">{display_logs}</div>', unsafe_allow_html=True)
            time.sleep(0.3)
            
        st.rerun()
        
    elif len(st.session_state.logs) > 0:
        st.markdown("---")
        st.markdown("### 📡 Final Telemetry")
        display_logs = "<br><br>".join(st.session_state.logs[-6:])
        st.markdown(f'<div class="log-box">{display_logs}</div>', unsafe_allow_html=True)


with col2:
    if st.session_state.complete and st.session_state.output:
        st.success("🎉 Agents have successfully concluded the drafting protocol.")
        
        with st.container():
            st.markdown('<div class="artifact-box">', unsafe_allow_html=True)
            st.markdown(st.session_state.output)
            st.markdown('</div>', unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            label="Download Markdown Artifact",
            data=st.session_state.output,
            file_name=f"{topic.replace(' ', '_').lower()}_report.md",
            mime="text/markdown",
            use_container_width=True
        )
    elif st.session_state.generating:
        st.info("The agents are currently executing logic loops. The synthesized document will appear here when complete.")
    else:
        st.markdown("""
        ### 🤖 Waiting for Instructions...
        
        The BlogSpot Crew is on standby. Provide a topic to initiate the following sequence:
        1. **Senior Data Researcher**: Scours parameters and aggregates high-level insights.
        2. **Reporting Analyst**: Reviews synthesized data and drafts a premium markdown report.
        """)
