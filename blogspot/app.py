# Forced Reboot Trigger
import streamlit as st
import os
from datetime import datetime
import threading
import time
from queue import Queue
from dotenv import load_dotenv
load_dotenv(override=True) # Force flush and override stale RAM environment variables!
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
        background-color: #0c1117;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 24px;
        height: 500px;
        overflow-y: auto;
        font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
        font-size: 0.85rem;
        color: #00ff41; /* Classic Terminal Green */
        backdrop-filter: blur(15px);
        box-shadow: inset 0 0 20px rgba(0,0,0,0.5), 0 10px 30px rgba(0,0,0,0.3);
        scrollbar-width: thin;
        scrollbar-color: #30363d #0c1117;
    }
    .log-box b, .log-box strong { color: #58a6ff !important; }
    .log-box blockquote { 
        margin: 8px 0; 
        padding-left: 12px; 
        border-left: 2px solid #30363d; 
        color: #8b949e !important; 
        font-style: italic; 
    }
    .log-box code { background-color: #161b22; color: #ff7b72; padding: 2px 4px; border-radius: 4px; }
    
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

# ====== Token Budget & Complexity Logic ======
class TokenBudgetManager:
    def __init__(self, tpm_limit=6000, rpm_limit=15): # Dropped to 6k to match Llama 3.1 8B limits
        self.tpm_limit = tpm_limit
        self.rpm_limit = rpm_limit
        self.tokens_used_this_minute = 0
        self.requests_this_minute = 0
        self.window_start = time.time()

    def reset_if_new_window(self):
        if time.time() - self.window_start >= 60:
            self.tokens_used_this_minute = 0
            self.requests_this_minute = 0
            self.window_start = time.time()

    def can_afford(self, estimated_tokens: int) -> bool:
        self.reset_if_new_window()
        # 85% safety margin for free tier volatility
        tpm_safe = self.tokens_used_this_minute + estimated_tokens < self.tpm_limit * 0.85
        rpm_safe = self.requests_this_minute < self.rpm_limit * 0.85
        return tpm_safe and rpm_safe

    def record_usage(self, tokens_used: int):
        self.reset_if_new_window()
        self.tokens_used_this_minute += tokens_used
        self.requests_this_minute += 1

    def time_until_reset(self) -> float:
        return max(0, 60 - (time.time() - self.window_start))

def estimate_task_complexity(topic_input):
    """
    Predicts if the job is too heavy for Hierarchical Manager based on the target topic.
    """
    # Base tokens for the tasks in tasks.yaml (~400 words total descriptions)
    base_task_tokens = 600 
    
    # Heuristic: More complex topics trigger deeper searches and more manager tokens
    complexity_score = len(topic_input.split())
    estimated_tokens = base_task_tokens + (complexity_score * 50)
    
    # If estimate > 3k, Manager overhead (~1.5x) will likely crash Groq TPM (12k)
    # 3000 * 1.5 = 4500. With 85% safety on 12000, we have ~10k available.
    # But manager calls are recursive. 
    # With Gemini as Manager, we can handle much higher complexity
    # 8,000 tokens is a safe ceiling for the mixture of Gemini and Groq
    if estimated_tokens > 8000:
        return "sequential", estimated_tokens
    return "hierarchical", estimated_tokens

# ====== Global Budget Tracker ======
if "budget" not in st.session_state:
    st.session_state.budget = TokenBudgetManager()

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
                # Dynamic Agent Identification
                agent_name = "Agent"
                if hasattr(step, 'agent'):
                    agent_name = step.agent
                elif hasattr(step, 'action') and hasattr(step.action, 'agent'):
                    agent_name = step.action.agent
                else:
                    # Fallback to current task tracker if agent name isn't explicit
                    idx = min(task_tracker['count'], len(agent_sequence)-1)
                    agent_name = agent_sequence[idx]

                # Extract reasoning and tool use
                thought = ""
                tool = ""
                
                if hasattr(step, 'thought'):
                    thought = step.thought
                    tool = getattr(step, 'tool', '')
                elif isinstance(step, tuple) and len(step) > 0:
                    action = step[0]
                    thought = getattr(action, 'log', '')
                    tool = getattr(action, 'tool', '')

                prefix = f"⚡ **[{agent_name}]**"

                # Detect Delegation (The "To/From" Logic)
                if tool and ("delegate" in tool.lower() or "ask" in tool.lower()):
                    q.put(f"🤝 **[{agent_name}]** is delegating task to another specialized agent... ⌛")
                elif tool:
                    q.put(f"{prefix} 🛠️ Working with tool: `{tool}` ... ⌛")
                
                if thought:
                    clean = thought.replace('`', '').strip()
                    # Logic to highlight "sending to" in thoughts
                    if "delegate" in clean.lower() or "sending" in clean.lower():
                        q.put(f"📡 **[{agent_name}]** *coordinating strategy:*<br><blockquote>{clean[:150]}...</blockquote> ⌛")
                    elif len(clean) > 5:
                        q.put(f"{prefix} *thinking:*<br><blockquote>{clean[:200]}...</blockquote> ⌛")
            except Exception as e:
                print(f"DEBUG: Telemetry Error: {e}")

        def task_callback(task_output):
            idx = min(task_tracker['count'], len(agent_sequence)-1)
            active_agent = agent_sequence[idx]
            
            q.put(f"✅ **MILESTONE COMPLETED:** {active_agent} has successfully finalized their assignment!")
            task_tracker["count"] += 1
            
            if task_tracker["count"] < len(agent_sequence):
                q.put(f"[STATE:WAIT] ⏳ *Handing off memory context to the next agent... Generating 20s API cool-off limit pause...*")
                for i in range(20):
                    if i % 5 == 0:
                        q.put(f"⏳ *Cooling down... {20-i}s remaining...*")
                    time.sleep(1)
                q.put("[STATE:RESUME]")

        blog.step_callback = step_callback
        blog.task_callback = task_callback
        
        inputs = {'topic': topic_input, 'current_year': str(datetime.now().year)}
        q.put("[STATE:RESUME]")
        
        max_retries = 2
        retry_count = 0
        success = False
        res = ""
        
        # --- Predictive Choice Pattern ---
        process_choice, est_tokens = estimate_task_complexity(topic_input)
        manager_token_cost = est_tokens * 1.6 # 1.6x multiplier for Hierarchical loops
        
        # Check budget before even trying Manager
        if process_choice == "hierarchical" and st.session_state.budget.can_afford(manager_token_cost):
            os.environ['CREW_PROCESS'] = 'hierarchical'
            q.put(f"🧙 **[PREDICTION]** Complexity safe ({int(manager_token_cost)} tokens estimated). Triggering Hierarchical Manager...")
        else:
            os.environ['CREW_PROCESS'] = 'sequential'
            q.put(f"⚙️ **[PREDICTION]** High complexity/Low budget ({int(manager_token_cost)} tokens). Using Sequential pacing for safety...")

        while retry_count <= max_retries and not success:
            try:
                # If we fail twice on Hierarchical, force safe fallback
                if retry_count >= 2:
                    q.put("⚠️ **[SYSTEM] Hierarchical loop triggered persistent limits. Switching to Safe-Sequential...**")
                    os.environ['CREW_PROCESS'] = 'sequential'
                    
                # Execute the crew
                res = blog.crew().kickoff(inputs=inputs)

                st.session_state.budget.record_usage(int(manager_token_cost) if os.environ['CREW_PROCESS'] == 'hierarchical' else int(est_tokens))
                st.session_state.output = str(res)
                success = True
                
            except Exception as e:
                error_msg = str(e)
                if any(x in error_msg.lower() for x in ["rate limit", "429", "resource_exhausted", "too many requests"]):
                    retry_count += 1
                    wait_time = st.session_state.budget.time_until_reset() + 5
                    q.put(f"[STATE:WAIT] ⏳ *Budget ceiling hit! Waiting {int(wait_time)}s for token window rotation...*")
                    time.sleep(wait_time)
                    q.put("[STATE:RESUME]")
                elif any(x in error_msg.lower() for x in ["tool_use_failed", "validation failed", "manager agent should not have tools"]):
                    retry_count += 1
                    q.put("⚠️ **[SYSTEM] Logic Hallucination. Bypassing Manager instantly...**")
                    os.environ['CREW_PROCESS'] = 'sequential'
                else:
                    raise e
        
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

topic = st.text_input("Enter Topic Descriptor", label_visibility="collapsed", placeholder="Enter your high-level topic... (e.g. 'The future of Quantum Computing in Healthcare')")

# Main columns layout
col1, space, col2 = st.columns([1.2, 0.1, 2])

with col1:
    st.markdown("### 🎛️ Control Panel")
    
    if st.button("🚀 Engage Agents", use_container_width=True):
        if not os.environ.get("GOOGLE_API_KEY"):
            st.error("🔑 **GOOGLE_API_KEY Missing!** Please add your Gemini key to the .env file.")
        elif not os.environ.get("GROQ_API_KEY"):
            st.error("🔑 **GROQ_API_KEY Missing!** Please add your Groq key to the .env file.")
        elif not topic:
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
        import itertools
        spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        hourglass = itertools.cycle(["⏳", "⌛"])
        is_waiting = False
        
        while t.is_alive() or not q.empty():
            while not q.empty():
                msg = q.get()
                if msg.startswith("FINISH|||"):
                    st.session_state.output = msg.split("|||", 1)[1]
                    st.session_state.complete = True
                    st.session_state.generating = False
                elif msg.startswith("ERROR|||"):
                    st.session_state.logs.append(f"❌ **CRITICAL FAILURE:** {msg.split('|||', 1)[1]}")
                    st.session_state.generating = False
                # Intercept state signals
                elif msg.startswith("[STATE:WAIT]"):
                    is_waiting = True
                    st.session_state.logs.append(msg.replace("[STATE:WAIT] ", ""))
                elif msg.startswith("[STATE:RESUME]"):
                    is_waiting = False
                else:
                    st.session_state.logs.append(msg)
                    
            # Animate the dynamic headers and the trailing dots in the log box
            display_logs = "<br><br>".join(st.session_state.logs)
            
            if is_waiting:
                ani_h = next(hourglass)
                # Add a dynamic trailing dot-dot-dot for the wait state
                dots = "." * (int(time.time() % 4))
                log_placeholder.markdown(f'### {ani_h} Throttling API Limits...\n<div class="log-box">{display_logs}<br><br>⏳ *System cooling down{dots}*</div>', unsafe_allow_html=True)
                time.sleep(0.5) 
            elif st.session_state.generating:
                ani_s = next(spinner)
                dots = "." * (int(time.time() % 4))
                log_placeholder.markdown(f'### {ani_s} Processing Subroutines...\n<div class="log-box">{display_logs}<br><br>⚡ *Active thinking in progress{dots}*</div>', unsafe_allow_html=True)
                time.sleep(0.1)

        t.join()
        st.rerun()
        
    elif len(st.session_state.logs) > 0:
        st.markdown("---")
        st.markdown("### 📡 Final Telemetry")
        display_logs = "<br><br>".join(st.session_state.logs)
        st.markdown(f'<div class="log-box">{display_logs}<br><br>✅ **PROCESS CONCLUDED**</div>', unsafe_allow_html=True)


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
