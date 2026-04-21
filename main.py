import asyncio
import json
import logging
import time
from pathlib import Path
import subprocess
import sys
#import atexit

#p=None
#def router():
#    global p
#    p = subprocess.Popen([sys.executable, "python", "router.py"], check=True)
#def on_exit():
#    global p
#    if p:
#        p.kill()

#atexit.register(on_exit)
'''
import httpx
from httpx import Request, Response

# 日志写入文件（自动追加，自动刷新）
def write_log(content: str):
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(content + "\n\n")
        f.flush()  # 立刻写入，不缓存

# 请求日志
def log_request(request: Request):
    try:
        body = request.read().decode("utf-8", errors="replace")
    except:
        body = "无法读取请求体"
    
    log = f"→ {request.method} {request.url}\n{body}"
    print(log)  # 控制台也显示
    write_log(log)

# 响应日志
def log_response(response: Response):
    try:
        body = response.read().decode("utf-8", errors="replace")
    except:
        body = "无法读取响应体"
    
    log = f"← {response.status_code}\n{body}"
    print(log)
    write_log(log)

# 带日志的客户端
client = httpx.Client(
    event_hooks={
        "request": [log_request],
        "response": [log_response]
    }
)
'''
def err_logger(msg: str):
    print(f"\033[91m{msg}\033[0m")
thisworktime=time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
def info_logger(msg: str):
    # 写在log文件夹时间+_info.log文件中
    log_file =  Path("log") / f"{thisworktime}_info.log"
    with open(log_file, "a",encoding="utf-8") as f:
        f.write(f"{msg}\n")
    if len(msg) > 30:
        print(f"\033[92m{msg[:30]+'...'}\033[0m")
    else:
        print(f"\033[92m{msg}\033[0m")
      
def check_and_install_codex_app_server():
    """检查 codex_app_server 是否存在，如果不存在则自动安装"""
    try:
        from codex_app_server import AsyncCodex, AppServerConfig, AppServerClient, TextInput,SkillInput
        return AsyncCodex, AppServerConfig, AppServerClient, TextInput, SkillInput
    except ImportError:
        print("codex_app_server 未安装，正在自动安装...")
        
        # 切换到 env 目录
        env_dir = Path.cwd() / "env"
        if not env_dir.exists():
            err_logger(f"env 目录不存在: {env_dir}")
            sys.exit(1)
        
        # 运行 pip install -e .
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", "."],
                cwd=env_dir,
                capture_output=True,
                text=True,
                check=True
            )
            print("codex_app_server 安装成功")
            print(result.stdout)
            result = subprocess.run(
                [sys.executable, Path("main.py")],
                cwd=Path.cwd(),
                text=True,
                check=True
            )
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            print(f"安装失败: {e}")
            print(f"错误输出: {e.stderr}")
            sys.exit(1)
        
        

AsyncCodex, AppServerConfig, AppServerClient,TextInput, SkillInput = check_and_install_codex_app_server()


  
# 任务注册表，用于存储已注册的任务类
TASK_REGISTRY = {}

def register_task(name: str):
    """装饰器：将任务类注册到 TASK_REGISTRY"""
    def wrapper(cls):
        TASK_REGISTRY[name] = cls
        return cls
    return wrapper

@register_task("planner")
class Planner:
    """读取 ques.json 并生成执行计划"""
    
    def __init__(self, codex: AsyncCodex, workdir: Path):
        self.codex = codex
        self.workdir = workdir
    
    def _load_prompt_file(self, filename: str) -> str | None:
        """如果存在则从 markdown 文件加载提示内容"""
        prompt_path = self.workdir / "agent" / "planner" / filename
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return None
    
    async def run(self) -> dict:
        """读取 ques.json，规划解决方案，返回计划字典"""
        ques_path = self.workdir / "question" / "ques.json"
        if not ques_path.exists():
            err_logger(f"问题文件未找到: {ques_path}")
            exit(1)
        
        with open(ques_path, "r") as f:
            question_data = json.load(f)
        
        # 如果存在 planner.md 则自动加载作为自定义提示
        planner_prompt = self._load_prompt_file("planner.md")
        planner_base_prompt = self._load_prompt_file("planner_base.md")
        if planner_prompt:
            # 使用 planner.md 内容作为开发者指令
            developer_instructions = planner_prompt
            if planner_base_prompt:
                base_instructions = planner_base_prompt
            else:
                base_instructions = "输出包含步骤、资源和成功标准的有效 JSON。"
        else:
            err_logger(f"规划提示文件未找到: {self.workdir / 'agent' / 'planner' / 'planner.md'}")
            exit(1)

        thread = await self.codex.thread_start(
            model="qwen3.5-plus",
            developer_instructions=developer_instructions,
            base_instructions=base_instructions
        )
        prompt = f"{json.dumps(question_data, indent=2)}"
        handle = await thread.turn(input = TextInput(prompt))
        
        stream = handle.stream()
        
        from codex_app_server._run import _collect_async_run_result
        try:
            result = await _collect_async_run_result(stream, turn_id=handle.id)
            print(result.final_response)  
        finally:
            await stream.aclose()
        
        try:
            plan = json.loads(result.final_response)
        except json.JSONDecodeError:
            plan = {"raw_response": result.final_response, "steps": []}
        
        # 保存计划供 builder 使用
        plan_path = self.workdir / "workspace" / "plan" / "plan.json"
        with open(plan_path, "w") as f:
            json.dump(plan, f, indent=2)
        
        info_logger(f"plan: {plan}\nplan_path: {plan_path}\n")
        return plan

@register_task("builder")
class Builder:
    """读取 plan.json 并构建解决方案"""
    
    def __init__(self, codex: AsyncCodex, workdir: Path):
        self.codex = codex
        self.workdir = workdir
    
    def _load_prompt_file(self, filename: str) -> str | None:
        """如果存在则从 markdown 文件加载提示内容"""
        prompt_path = self.workdir / "agent" / "builder" / filename
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return None
    
    async def run(self, plan: dict = None) -> dict:
        """读取 plan.json（或使用传入的计划），执行步骤，返回解决方案"""
        plan_path = self.workdir / "workspace" / "plan" / "plan.json"
        if not plan_path.exists() and not plan:
            err_logger(f"计划文件未找到: {plan_path}")
            exit(1)
        
        if not plan and plan_path.exists():
            with open(plan_path, "r") as f:
                plan = json.load(f)
        
        # 如果存在 builder.md 则自动加载作为自定义提示
        builder_prompt = self._load_prompt_file("builder.md")
        builder_base_prompt = self._load_prompt_file("builder_base.md")
        
        if builder_prompt:
            developer_instructions = builder_prompt
            if builder_base_prompt:
                base_instructions = builder_base_prompt
            else:
                base_instructions = "输出包含结果的有效 JSON。"
        else:
            err_logger(f"解决方案提示文件未找到: {self.workdir / 'agent' / 'builder' / 'builder.md'}")
            exit(1)
        
        
        thread = await self.codex.thread_start(
            model="qwen3.5-plus",
            developer_instructions=developer_instructions,
            base_instructions=base_instructions
        )
        
        prompt = f"{json.dumps(plan, indent=2)}"
        handle = await thread.turn(input = TextInput(prompt))
        stream = handle.stream()

        from codex_app_server._run import _collect_async_run_result
        try:
            result = await _collect_async_run_result(stream, turn_id=handle.id)
            print(result.final_response)  
        finally:
            await stream.aclose()
        
        try:
            solution = json.loads(result.final_response)
        except json.JSONDecodeError:
            solution = {"raw_response": result.final_response}
        
        # 保存解决方案供 evaluator 使用
        solu_path = self.workdir / "workspace" / "solution" / "solu.json"
        with open(solu_path, "w") as f:
            json.dump(solution, f, indent=2)
        
        info_logger(f"solu: {solution}\nsolu_path: {solu_path}\n")
        return solution

@register_task("evaluator")
class Evaluator:
    """读取 solu.json 并评估解决方案"""
    
    def __init__(self, codex: AsyncCodex, workdir: Path):
        self.codex = codex
        self.workdir = workdir
    
    def _load_prompt_file(self, filename: str) -> str | None:
        """如果存在则从 markdown 文件加载提示内容"""
        prompt_path = self.workdir / "agent" / "evaluator" / filename
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return None
    
    async def run(self, solution: dict = None) -> dict:
        """读取 solu.json（或使用传入的解决方案），执行评估，返回评估结果"""
        solu_path = self.workdir / "workspace" / "solution" / "solu.json"
        if not solu_path.exists() and not solution:
            err_logger(f"解决方案文件未找到: {solu_path}")
            exit(1)
        
        if not solution and solu_path.exists():
            with open(solu_path, "r") as f:
                solution = json.load(f)
        
        ques_path = self.workdir / "question" / "ques.json"
        with open(ques_path, "r") as f:
            question_data = json.load(f)
        
        # 如果存在 evaluator.md 则自动加载作为自定义提示
        evaluator_prompt = self._load_prompt_file("evaluator.md")
        evaluator_base_prompt = self._load_prompt_file("evaluator_base.md") 
        
        if evaluator_prompt:
            developer_instructions = evaluator_prompt
            if evaluator_base_prompt:
                base_instructions = evaluator_base_prompt
            else:
                base_instructions = "输出包含评分和反馈的有效 JSON。"
        else:
            err_logger(f"评估提示文件未找到: {self.workdir / 'agent' / 'evaluator' / 'evaluator.md'}")
            exit(1)

        
        thread = await self.codex.thread_start(
            model="qwen3.5-plus",
            developer_instructions=developer_instructions,
            base_instructions=base_instructions
        )
        
        prompt = f"问题: {json.dumps(question_data, indent=2)}\n\n解决方案: {json.dumps(solution, indent=2)}"
        handle = await thread.turn(input = TextInput(prompt))
        stream = handle.stream()

        from codex_app_server._run import _collect_async_run_result
        try:
            result = await _collect_async_run_result(stream, turn_id=handle.id)
            print(result.final_response)  
        finally:
            await stream.aclose()
        try:
            evaluation = json.loads(result.final_response)
        except json.JSONDecodeError:
            evaluation = {"raw_response": result.final_response}
        
        # 保存评估结果
        eval_path = self.workdir / "workspace" / "evaluation" / "eval.json"
        with open(eval_path, "w") as f:
            json.dump(evaluation, f, indent=2)
        
        info_logger(f"evaluation: {evaluation}\neval_path: {eval_path}\n")
        return evaluation

def get_task_registry(codex: AsyncCodex, workdir: Path) -> dict:
    """获取已实例化的任务注册表，将类转换为可调用方法"""
    registry = {}
    for name, cls in TASK_REGISTRY.items():
        instance = cls(codex, workdir)
        registry[name] = instance.run
    return registry

class AsyncWorkflowEngine:
    """异步工作流引擎：解析并执行 JSON 配置的工作流"""
    
    def __init__(self, workflow: dict, task_registry: dict):
        self.workflow = workflow
        self.task_registry = task_registry

    def _replace_params(self, params, loop_index):
        """替换参数中的循环索引占位符"""
        if loop_index is None:
            return params
        s = json.dumps(params).replace("{{loop_index}}", str(loop_index))
        return json.loads(s)

    async def execute(self, step, loop_index=None):
        """执行单个工作流步骤"""
        stype = step.get("type")
        name = step.get("name", "Unnamed")

        # 原子任务：异步执行单个函数
        if stype == "task":
            func = self.task_registry[step["func"]]
            params = self._replace_params(step.get("params", {}), loop_index)
            info_logger(f"  [执行任务] {name}")
            if params:
                return await func(self, **params)
            else:
                return await func()

        # 顺序管线：按顺序执行多个子任务
        elif stype == "pipeline":
            info_logger(f"\n>> 进入管线: {name}")
            task_results = []
            last_res = {}
            for sub_step in step["tasks"]:
                last_res = await self.execute(sub_step, loop_index)
                task_results.append(last_res)
                await asyncio.sleep(0.2)
            # 合并最后一个任务的结果到返回字典中，便于 break_condition 读取
            return {
                "status": "success", 
                "data": task_results, 
                **last_res
            }

        # 异步并行：同时执行多个子任务
        elif stype == "parallel":
            info_logger(f"\n>> 启动并行: {name}")
            tasks = [self.execute(s, loop_index) for s in step["tasks"]]
            combined_results = await asyncio.gather(*tasks)
            return {"status": "success", "type": "parallel", "data": combined_results}

        # 异步循环：重复执行任务体指定次数
        elif stype == "loop":
            info_logger(f"\n>> 启动循环: {name}")
            times = step["times"]
            loop_history = []
            for i in range(1, times + 1):
                res = await self.execute(step["body"], loop_index=i)
                loop_history.append(res)
                # 检查中断条件，如果满足则提前退出循环
                if step.get("break_condition"):
                    if eval(step["break_condition"], {"result": res}):
                        info_logger(f"循环中断: 满足条件")
                        break
            return {"status": "finished", "type": "loop", "data": loop_history}

    async def run(self):
        """执行整个工作流"""
        start_time = time.perf_counter()
        info_logger(f"异步引擎启动: {self.workflow.get('workflow_name')}")
        
        for step in self.workflow["tasks"]:
            await self.execute(step)
            
        info_logger(f"\n流程全部完成，总耗时: {time.perf_counter() - start_time:.2f}s")

# 主程序入口
config = AppServerConfig()
where_result = subprocess.run(["where", "codex.cmd"], text=True, capture_output=True, check=True,)
config.codex_bin = where_result.stdout.strip()

async def main():
    # 1. 基础环境初始化
    codex_instance = AsyncCodex(config=config) 
    work_path = Path.cwd()

    # 2. 获取实例化的任务注册表（关键步骤）
    # 将 TASK_REGISTRY 里的类变成实例的 .run 方法
    active_registry = get_task_registry(codex_instance, work_path)

    # 3. 加载 JSON 配置化的工作流（由引擎驱动）
    workflow_config = json.loads((Path.cwd() / "workflow.json").read_text(encoding="utf-8"))

    # 4. 实例化引擎并运行
    # 传入的是 active_registry（已实例化的方法映射）
    engine = AsyncWorkflowEngine(workflow_config, active_registry)
    await engine.run()

if __name__ == "__main__":

    #args = sys.argv[1:] 
    #if "--router" in args:
    #    router()
    asyncio.run(main())
    