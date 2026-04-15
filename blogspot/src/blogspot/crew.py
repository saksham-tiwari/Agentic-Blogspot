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
            allow_delegation=False, # Removed to prevent 8B model function calling crashes
            tools=[SerperDevTool()], # ONLY using Serper to prevent Token Limits from crashing!
            llm=LLM(model=os.environ.get("DRAFTING_MODEL", "groq/llama-3.3-70b-versatile")),
            step_callback=getattr(self, 'step_callback', None)
        )

    @agent
    def reporting_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['reporting_analyst'], # type: ignore[index]
            verbose=True,
            allow_delegation=False,
            llm=LLM(model=os.environ.get("DRAFTING_MODEL", "groq/llama-3.3-70b-versatile")),
            step_callback=getattr(self, 'step_callback', None)
        )

    @agent
    def editor(self) -> Agent:
        return Agent(
            config=self.agents_config['editor'], # type: ignore[index]
            verbose=True,
            allow_delegation=False,
            llm=LLM(model=os.environ.get("DRAFTING_MODEL", "groq/llama-3.3-70b-versatile")),
            step_callback=getattr(self, 'step_callback', None)
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

        return Crew(
            agents=self.agents, # Automatically created by the @agent decorator
            tasks=self.tasks, # Automatically created by the @task decorator
            process=Process.sequential, # Reverted to sequential to prevent API Rate Limits
            verbose=True,
            memory=True,  # Added to remember past iterations and avoid repeating work!
            cache=True,   # Caches API responses for speed and cost efficiency
        )
