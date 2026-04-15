from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio
import json
from blogspot.crew import Blogspot
from datetime import datetime
import uuid
import queue
import threading
import os

app = FastAPI()

# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

streams = {}

def bg_run_crew(topic: str, request_id: str):
    q = queue.Queue()
    streams[request_id] = q

    def step_callback(step):
        # We can extract more info from step if needed
        q.put({"type": "step", "message": "Agent finished a thought/step. Analyzing data..."})

    def task_callback(task_output):
        q.put({"type": "task", "message": "Task Successfully Completed!"})

    try:
        blog = Blogspot()
        blog.step_callback = step_callback
        blog.task_callback = task_callback
        
        inputs = {'topic': topic, 'current_year': str(datetime.now().year)}
        
        q.put({"type": "status", "message": "Starting the BlogSpot Crew..."})
        res = blog.crew().kickoff(inputs=inputs)
        
        if os.path.exists("report.md"):
            with open("report.md", "r") as f:
                res_content = f.read()
        else:
            res_content = str(res)
            
        q.put({"type": "complete", "content": res_content})
    except Exception as e:
        q.put({"type": "error", "message": f"An error occurred: {str(e)}"})
    finally:
        q.put(None)

@app.get("/api/stream")
async def stream_blog(topic: str):
    request_id = str(uuid.uuid4())
    
    thread = threading.Thread(target=bg_run_crew, args=(topic, request_id))
    thread.start()
    
    async def event_generator():
        # wait a tiny bit to make sure thread stores the queue
        await asyncio.sleep(0.1)
        q = streams.get(request_id)
        if not q:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to initialize.'})}\n\n"
            return
            
        while True:
            try:
                item = await asyncio.to_thread(q.get, timeout=1.0)
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                # Keep alive
                yield f": keep-alive\n\n"
                
        # Clean up
        del streams[request_id]
                
    return StreamingResponse(event_generator(), media_type="text/event-stream")
