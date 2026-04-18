from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai_tools import SerperDevTool, ScrapeWebsiteTool
from typing import List
import os
# you can use the @before_kickoff and @after_kickoff decorators
# https://docs.crewai.com/concepts/crews#example-crew-class-with-decorators

@CrewBase
class Blogspot():
    """Blogspot crew"""

    agents: List[BaseAgent]
    tasks: List[Task]

    # Learn more about YAML configuration files here:
    # Agents: https://docs.crewai.com/concepts/agents#yaml-configuration-recommended
    # Tasks: https://docs.crewai.com/concepts/tasks#yaml-configuration-recommended
    
    # If you would like to add tools to your agents, you can learn more about it here:
    # https://docs.crewai.com/concepts/agents#agent-tools
    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config['researcher'], # type: ignore[index]
            verbose=True,
            allow_delegation=False,
            # Keep Researcher on 70B for the highest quality deep-dives
            tools=[SerperDevTool(), ScrapeWebsiteTool()], 
            llm=LLM(model="groq/llama-3.3-70b-versatile"), 
            step_callback=getattr(self, 'step_callback', None)
        )

    @agent
    def reporting_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['reporting_analyst'], # type: ignore[index]
            verbose=True,
            allow_delegation=False,
            # Testing Gemini 2.0 Flash Lite here for synthesis speed
            llm=LLM(model="gemini/gemini-2.0-flash-lite"), 
            step_callback=getattr(self, 'step_callback', None)
        )

    @agent
    def editor(self) -> Agent:
        return Agent(
            config=self.agents_config['editor'], # type: ignore[index]
            verbose=True,
            allow_delegation=False,
            # Switched to 8B for the final mile to bypass TPM limits
            llm=LLM(model="groq/llama-3.1-8b-instant"), 
            step_callback=getattr(self, 'step_callback', None)
        )

    def blog_manager(self) -> Agent:
        return Agent(
            role="Blog Project Manager",
            goal="Efficiently coordinate the crew to produce a high-quality, publication-ready blog post.",
            backstory="""You are a veteran Content Director. Your job is to oversee the research and writing process. 
            CRITICAL RULE: When you are providing the final synthesized blog post to the user, you must NOT 
            include any internal tool syntax, XML tags like <delegate_work_to_coworker>, or technical jargon. 
            Provide ONLY the beautifully formatted markdown blog post itself.""",
            allow_delegation=True,
            # Using 'gemini-flash-latest' for the 1M context window and standard flash quotas
            llm=LLM(model="gemini/gemini-flash-latest"), 
            verbose=True
        )

    # To learn more about structured task outputs,
    # task dependencies, and task callbacks, check out the documentation:
    # https://docs.crewai.com/concepts/tasks#overview-of-a-task
    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config['research_task'], # type: ignore[index]
            callback=getattr(self, 'task_callback', None)
        )

    @task
    def reporting_task(self) -> Task:
        return Task(
            config=self.tasks_config['reporting_task'], # type: ignore[index]
            callback=getattr(self, 'task_callback', None)
        )

    @task
    def editing_task(self) -> Task:
        return Task(
            config=self.tasks_config['editing_task'], # type: ignore[index]
            output_file='report.md',
            callback=getattr(self, 'task_callback', None)
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Blogspot crew"""
        # To learn how to add knowledge sources to your crew, check out the documentation:
        # https://docs.crewai.com/concepts/knowledge#what-is-knowledge

        process_type = Process.hierarchical if os.environ.get('CREW_PROCESS', 'hierarchical') == 'hierarchical' else Process.sequential
        
        # Manager Engine - Using Groq 8B for orchestrating to bypass TPM limits
        manager_engine = LLM(model="groq/llama-3.1-8b-instant") if process_type == Process.hierarchical else None

        return Crew(
            agents=self.agents, # Automatically created by the @agent decorator
            tasks=self.tasks, # Automatically created by the @task decorator
            process=process_type, # Dynamic execution structure
            manager_agent=self.blog_manager() if process_type == Process.hierarchical else None,
            verbose=True,
            max_rpm=2,   # Lowered to 2 to ensure we stay well within Groq TPM/RPM windows
            memory=False, 
            cache=True,   
        )
