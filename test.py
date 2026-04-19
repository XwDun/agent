import asyncio
import json
import re
import logging
import time
from datetime import datetime
from pathlib import Path
from codex_app_server import Codex


TASK_REGISTRY = {}

def register_task(name: str):
    """用于将类注册到 TASK_REGISTRY 的装饰器"""
    def wrapper(cls):
        TASK_REGISTRY[name] = cls
        return cls
    return wrapper

@register_task("planner")
class Planner:
    """Reads ques.json and generates a plan."""
    
    def __init__(self, codex: Codex, workdir: Path):
        self.codex = codex
        self.workdir = workdir
    
    def _load_prompt_file(self, filename: str) -> str | None:
        """Load prompt content from a markdown file if it exists."""
        prompt_path = self.workdir / "planner" / filename
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return None
    
    async def run(self) -> dict:
        """Read ques.json, plan the solution, return plan dict."""
        ques_path = self.workdir / "question" /"ques.json"
        if not ques_path.exists():
            raise FileNotFoundError(f"Question file not found: {ques_path}")
        
        with open(ques_path, "r") as f:
            question_data = json.load(f)
        
        # Auto-load planner.md as custom prompt if available
        planner_prompt = self._load_prompt_file("planner.md")
        
        if planner_prompt:
            # Use planner.md content as developer_instructions
            developer_instructions = planner_prompt
            base_instructions = "Output valid JSON with steps, resources, and success criteria."
        else:
            # Fallback to default instructions
            developer_instructions = "You are a planning assistant. Create structured, actionable plans."
            base_instructions = "Output valid JSON with steps, resources, and success criteria."
        
        thread = self.codex.thread_start(
            model="qwen3.5-plus",
            developer_instructions=developer_instructions,
            base_instructions=base_instructions
        )
        
        prompt = f"{json.dumps(question_data, indent=2)}"
        result = await asyncio.to_thread(thread.run, prompt)
        
        try:
            plan = json.loads(result.final_response)
        except json.JSONDecodeError:
            plan = {"raw_response": result.final_response, "steps": []}
        
        # Save plan for builder
        plan_path = self.workdir / "plan" / "plan.json"
        with open(plan_path, "w") as f:
            json.dump(plan, f, indent=2)
        
        return plan

@register_task("builder")
class Builder:
    """Reads plan.json and builds the solution."""
    
    def __init__(self, codex: Codex, workdir: Path):
        self.codex = codex
        self.workdir = workdir
    
    def _load_prompt_file(self, filename: str) -> str | None:
        """Load prompt content from a markdown file if it exists."""
        prompt_path = self.workdir / "builder" / filename
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return None
    
    async def run(self, plan: dict = None )-> dict:
        """Read plan.json (or use provided plan), execute steps, return solution."""
        plan_path = self.workdir / "plan" / "plan.json"
        if not plan_path.exists() and not plan:
            raise FileNotFoundError(f"Plan file not found: {plan_path}")
        
        if not plan and plan_path.exists():
            with open(plan_path, "r") as f:
                plan = json.load(f)
        
        # Auto-load builder.md as custom prompt if available
        builder_prompt = self._load_prompt_file("builder.md")
        
        if builder_prompt:
            developer_instructions = builder_prompt
            base_instructions = "Output valid JSON with results."
        else:
            developer_instructions = "You are a solution builder. Implement plans precisely."
            base_instructions = "Output valid JSON with results."
        
        thread = self.codex.thread_start(
            model="qwen3.5-plus",
            developer_instructions=developer_instructions,
            base_instructions=base_instructions
        )
        
        prompt = f"{json.dumps(plan, indent=2)}"
        result = await asyncio.to_thread(thread.run, prompt)
        
        try:
            solution = json.loads(result.final_response)
        except json.JSONDecodeError:
            solution = {"raw_response": result.final_response}
        
        # Save solution for evaluator
        solu_path = self.workdir / "solution" / "solu.json"
        with open(solu_path, "w") as f:
            json.dump(solution, f, indent=2)
        
        return solution

@register_task("evaluator")
class Evaluator:
    """Reads solu.json and evaluates the solution."""
    
    def __init__(self, codex: Codex, workdir: Path):
        self.codex = codex
        self.workdir = workdir
    
    def _load_prompt_file(self, filename: str) -> str | None:
        """Load prompt content from a markdown file if it exists."""
        prompt_path = self.workdir / "evaluator" / filename
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return None
    
    async def run(self, solution: dict = None, original_question: dict = None) -> dict:
        """Read solu.json (or use provided solution), evaluate quality, return assessment."""
        solu_path = self.workdir / "solution" / "solu.json"
        if not solu_path.exists() and not solution:
            raise FileNotFoundError(f"Solution file not found: {solu_path}")
        
        if not solution and solu_path.exists():
            with open(solu_path, "r") as f:
                solution = json.load(f)
        
        # Load original question if available for context
        ques_path = self.workdir / "question" / "ques.json"
        question_context = ""
        if ques_path.exists():
            with open(ques_path, "r") as f:
                question_context = json.load(f)
        
        # Auto-load evaluator.md as custom prompt if available
        evaluator_prompt = self._load_prompt_file("evaluator.md")
        
        if evaluator_prompt:
            developer_instructions = evaluator_prompt
            base_instructions = "Output valid JSON with score (0-100), feedback, and pass/fail."
        else:
            developer_instructions = "You are an evaluator. Assess solution correctness and completeness."
            base_instructions = "Output valid JSON with score (0-100), feedback, and pass/fail."
        
        thread = self.codex.thread_start(
            model="qwen3.5-plus",
            developer_instructions=developer_instructions,
            base_instructions=base_instructions
        )
        
        eval_input = {
            "question": question_context,
            "solution": solution,
            "criteria": ["correctness", "completeness", "efficiency"]
        }
        prompt = f"Evaluate this solution: {json.dumps(eval_input, indent=2)}"
        result = await asyncio.to_thread(thread.run, prompt)
        
        try:
            evaluation = json.loads(result.final_response)
        except json.JSONDecodeError:
            evaluation = {"raw_response": result.final_response, "score": None}
            
        eval_path = self.workdir / "evaluation" / "eval.json"
        with open(eval_path, "w") as f:
            json.dump(evaluation, f, indent=2)
        
        return evaluation
        
    
def get_task_registry(codex: Codex, workdir: Path):
    """
    动态从 TASK_REGISTRY 生成实例映射表
    """
    # 动态生成：{ "planner": planner_instance.run, "builder": builder_instance.run }
    return {
        name: task_cls(codex, workdir).run 
        for name, task_cls in TASK_REGISTRY.items()
    }

class AsyncWorkflowEngine:
    def __init__(self, workflow_config, task_registry):
        self.workflow = workflow_config
        self.task_registry = task_registry

    def _replace_params(self, params, loop_index):
        if loop_index is None: return params
        s = json.dumps(params).replace("{{loop_index}}", str(loop_index))
        return json.loads(s)

    async def execute(self, step, loop_index=None):
        stype = step.get("type")
        name = step.get("name", "Unnamed")

        # 1. 原子任务 (异步执行)
        if stype == "task":
            func = self.task_registry[step["func"]]
            params = self._replace_params(step.get("params", {}), loop_index)
            print(f"  [执行任务] {name}")
            # 注意：此处保持原样或根据你的任务返回值决定是否包装
            if params:
                return await func(self, **params)
            else:
                return await func()

        # 2. 顺序管线 - 已修改为字典语法
        # 2. 顺序管线
        elif stype == "pipeline":
            print(f"\n>> 进入管线: {name}")
            task_results = []
            last_res = {} # 记录最后一个任务的结果
            for sub_step in step["tasks"]:
                last_res = await self.execute(sub_step, loop_index)
                task_results.append(last_res)
                await asyncio.sleep(0.2)
            
            # 将最后一个任务的结果合并到返回字典中，方便 break_condition 读取
            return {
                "status": "success", 
                "data": task_results, 
                **last_res  # <--- 关键：解包最后一个任务的字典
            }

        # 3. 异步并行 - 已修改为字典语法
        elif stype == "parallel":
            print(f"\n>> 启动并行: {name}")
            tasks = [self.execute(s, loop_index) for s in step["tasks"]]
            combined_results = await asyncio.gather(*tasks)
            # 返回字典而不是列表
            return {"status": "success", "type": "parallel", "data": combined_results}

        # 4. 异步循环
        elif stype == "loop":
            print(f"\n>> 启动循环: {name}")
            times = step["times"]
            loop_history = []
            for i in range(1, times + 1):
                res = await self.execute(step["body"], loop_index=i)
                loop_history.append(res)
                
                # 现在 res 是一个字典了，下面这行 eval 不会再报 'list' attribute 错误
                if step.get("break_condition"):
                    if eval(step["break_condition"], {"result": res}):
                        print(f"🛑 循环中断: 满足条件")
                        break
            return {"status": "finished", "type": "loop", "data": loop_history}

    async def run(self):
        start_time = time.perf_counter()
        print(f"🚀 异步引擎启动: {self.workflow.get('workflow_name')}")
        
        for step in self.workflow["tasks"]:
            await self.execute(step)
            
        print(f"\n✅ 流程全部完成，总耗时: {time.perf_counter() - start_time:.2f}s")


async def main():
    # 1. 基础环境初始化
    codex_instance = Codex() 
    work_path = Path.cwd()

    # 2. 获取实例化的任务注册表 (关键步骤！)
    # 这一步将 TASK_REGISTRY 里的类变成实例的 .run 方法
    active_registry = get_task_registry(codex_instance, work_path)

    # 3. 定义 JSON 配置化的工作流 (由引擎驱动)
    #workflow_config = {
    #    "workflow_name": "自动开发流程",
    #    "tasks": [
    #        {
    #            "type": "pipeline",
    #            "name": "标准构建链",
    #            "tasks": [
    #                {
    #                    "type": "task",
    #                    "name": "生成规划",
    #                    "func": "planner", # 对应 TASK_REGISTRY 的 key
    #                },
    #                {
    #                    "type": "task",
    #                    "name": "执行构建",
    #                    "func": "builder",
    #                }
     #           ]
     #       }
     #   ]
    #}
    
    workflow_config = json.loads((Path.cwd() / "workflow.json").read_text(encoding="utf-8"))

    # 4. 实例化引擎并运行
    # 注意：这里传入的是 active_registry (已实例化的方法映射)
    engine = AsyncWorkflowEngine(workflow_config, active_registry)
    await engine.run()

if __name__ == "__main__":
    asyncio.run(main())
