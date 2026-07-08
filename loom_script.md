# Loom Video Script: Multi-Agent AI Workflow Automator
**Target Duration:** ~2 minutes (120 seconds)  
**Target Word Count:** ~260 words (spoken at a moderate pace of 130 WPM)  
**Tone:** Professional, engaging, and tech-savvy  

---

## Storyboard & Script

| Timestamp | Screen / Visual Action | Voiceover / Audio Script |
| :--- | :--- | :--- |
| **0:00 - 0:15** <br>*(15s)* | **Show the React Frontend Homepage.** <br>Mouse hovering over the task input area. | "Hey everyone! Today, I’m excited to show you the **Multi-Agent AI Workflow Automator**—a production-grade system designed to handle complex, multi-step research and analysis tasks that standard single LLM prompts fail to solve." |
| **0:15 - 0:45** <br>*(30s)* | **Type a task** like *"Compare LangGraph and CrewAI for building multi-agent systems"* and **click Submit**. <br><br>Immediately show the dual-panel layout slide in, showing **Agent Log** streaming live steps via WebSockets, and **Result Panel** showing "processing". | "Let’s submit a task to compare LangGraph and CrewAI. <br><br>As soon as I hit submit, the backend spawns an asynchronous background task and returns a 202 immediately to prevent HTTP timeouts. On the left, you can see real-time steps streaming in via WebSockets directly from our LangGraph orchestrator." |
| **0:45 - 1:15** <br>*(30s)* | **Open the `project_documentation.md` architecture diagram (or point to the visual steps on screen).** <br>Highlight nodes like `MEMORY_LOAD`, `PLAN`, `RESEARCHER`, `SUMMARISER`, `WRITER`, `VALIDATE`. | "Under the hood, **LangGraph** manages the state. It first loads context from **FAISS** vector memory, creates a step-by-step plan, and routes the work dynamically between specialized agents like our Researcher, Summariser, and Writer, before validating the output against the original request." |
| **1:15 - 1:45** <br>*(30s)* | **Show the final markdown report** render in the **Result Panel** on the right. <br><br>Point out the confidence score (e.g., 0.92) and notice that no sensitive information is present. | "And there it is! Our Writer compiled a beautifully formatted markdown report. <br><br>Before displaying, the output passed through our **Output Guardrail** to scrub PII and calculate a confidence score. If the score is high, it updates PostgreSQL and saves the task embedding in our local FAISS index for long-term memory." |
| **1:45 - 2:00** <br>*(15s)* | **Show the codebase structure** briefly in VS Code (backend FastAPI files, frontend components, and docker-compose). | "The entire stack runs on **FastAPI**, **React with TypeScript**, and **Groq Llama-3.3** with a **Gemini** fallback. It's fully containerized with Docker and ready for production. Thanks for watching!" |

---

## 💡 Quick Tips for Recording
1. **Preparation:** Copy the script above or have it open on a second monitor/phone.
2. **Speed & Energy:** Speak clearly with high energy. 2 minutes goes by fast, so practice once to get the timing right.
3. **Environment:** Make sure your terminal or Docker container is running beforehand so you can demo the actual frontend interaction live.
4. **Resolution:** Record in full screen (1080p) to keep the streaming logs and code legible.
