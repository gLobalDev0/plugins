import os

from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task

# Groq ücretsiz planda 70b TPD ve 8b TPM limiti — tek model + yeniden deneme
_GROQ_MODEL = os.environ.get("MODEL", "groq/llama-3.1-8b-instant").replace("groq/", "")
_SHARED_LLM = LLM(
    model="groq/%s" % _GROQ_MODEL,
    temperature=0.35,
    max_retries=int(os.environ.get("LITELLM_NUM_RETRIES", "12")),
    timeout=120,
)


@CrewBase
class KicadUavCrew():
    """KicadUavCrew ekibi"""

    @agent
    def kicad_consultant(self) -> Agent:
        return Agent(
            config=self.agents_config['kicad_consultant'],
            llm=_SHARED_LLM,
            verbose=True,
        )

    @agent
    def senior_pcb_reviewer(self) -> Agent:
        return Agent(
            config=self.agents_config['senior_pcb_reviewer'],
            llm=_SHARED_LLM,
            verbose=True,
        )

    @agent
    def track_router_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['track_router_agent'],
            llm=_SHARED_LLM,
            verbose=True,
        )

    @task
    def requirement_gathering_task(self) -> Task:
        return Task(
            config=self.tasks_config['requirement_gathering_task']
        )

    @task
    def electrical_review_task(self) -> Task:
        return Task(
            config=self.tasks_config['electrical_review_task']
        )

    @task
    def routing_optimization_task(self) -> Task:
        return Task(
            config=self.tasks_config['routing_optimization_task']
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            max_rpm=6,
        )
