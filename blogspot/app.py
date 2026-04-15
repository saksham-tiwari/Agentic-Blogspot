import streamlit as st
import os
from datetime import datetime
from blogspot.crew import Blogspot

st.set_page_config(page_title="Blogspot AI", page_icon="📝", layout="centered")

st.title("📝 BlogSpot AI Generator")
st.markdown("Generate comprehensive blog posts on any topic using CrewAI.")

topic = st.text_input("What is the topic you want to write about?", placeholder="e.g. The Future of AI LLMs in 2026")

if st.button("Generate Blog Post", type="primary", use_container_width=True):
    if not topic:
        st.warning("Please enter a topic.")
    else:
        with st.status("🧠 Agents are working...", expanded=True) as status:
            st.write("Initializing agents...")
            
            def step_callback(step):
                # This could be called many times, so we just add a small generic message to the status layout
                st.write(f"⚙️ Agent has completed a logic block. Synthesizing data...")

            def task_callback(task_output):
                st.write(f"✅ One of the major tasks is complete.")

            blog = Blogspot()
            blog.step_callback = step_callback
            blog.task_callback = task_callback
            
            inputs = {'topic': topic, 'current_year': str(datetime.now().year)}
            
            st.write("Starting Research and Writing (This may take a minute)...")
            try:
                res = blog.crew().kickoff(inputs=inputs)
                status.update(label="Blog Generated Successfully!", state="complete", expanded=False)
                
                st.success("Generation complete!")
                
                # Check for output file
                if os.path.exists("report.md"):
                    with open("report.md", "r") as f:
                        content = f.read()
                else:
                    content = str(res)
                
                st.markdown("### Generated Blog Post")
                st.markdown(content)
                
                st.download_button(
                    label="Download Markdown", 
                    data=content, 
                    file_name="blog_post.md", 
                    mime="text/markdown"
                )
                
            except Exception as e:
                status.update(label="An error occurred", state="error", expanded=True)
                st.error(f"Error: {e}")
