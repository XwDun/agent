# Agent Workflow Engine 使用指南

## 快速配置

### 1. 问题配置 (question/ques.json)

在`ques.json`中定义需要解决的问题：

```json
{
  "problem": "你的问题描述"
}
```

### 2. 工作流配置 (workflow.json)

配置任务执行流程，支持多种模式：

```json
{
  "type": "pipeline",
  "name": "标准构建链",
  "tasks": [
    {
      "name": "规划阶段",
      "type": "task",
      "func": "planner"
    },
    {
      "name": "优化循环",
      "type": "loop",
      "times": 3,
      "break_condition": "result.get(\"score\") >= 98",
      "body": {
        "type": "pipeline",
        "name": "构建评估链",
        "tasks": [
          {
            "name": "构建阶段",
            "type": "task",
            "func": "builder"
          },
          {
            "name": "评估阶段",
            "type": "task",
            "func": "evaluator"
          }
        ]
      }
    }
  ]
}
```

**工作流模式说明：**

- **task**: 执行单个任务
- **pipeline**: 顺序执行多个任务
- **parallel**: 并行执行多个任务
- **loop**: 循环执行，支持中断条件

### 3. Agent提示配置

#### 规划器 (agent/planner/)

**planner.md** - 开发者指令：
```
你是一个规划器。
读取输入问题并给出解决计划。
你的输出必须是JSON格式，包含问题和计划。
```

**planner_base.md** - 基础指令：
```
输出包含步骤、资源和成功标准的有效JSON。
```

#### 构建器 (agent/builder/)

**builder.md** - 开发者指令：
```
你是一个构建器。
读取输入问题和计划并给出解决方案。
```

**builder_base.md** - 基础指令：
```
输出包含结果的有效JSON。
```

#### 评估器 (agent/evaluator/)

**evaluator.md** - 开发者指令：
```
你是一个评估器。
评估解决方案的质量。
```

**evaluator_base.md** - 基础指令：
```
输出包含评分和反馈的有效JSON。
```

## 运行方式

```bash
python main.py
```

系统会自动：
1. 检查并安装codex_app_server依赖
2. 读取ques.json中的问题
3. 按照workflow.json配置执行工作流
4. 生成结果文件到workspace目录
  
如果要解决多个问题，请确保是json列表格式，将题目文件命名为`ques_all.json`并放入题目文件夹中，然后运行：

```bash
python runner.py
```
这种运行方式带有缓存功能。

## 输出文件

- `workspace/plan/plan.json` - 规划结果
- `workspace/solution/solu.json` - 解决方案  
- `workspace/evaluation/eval.json` - 评估结果

## 自定义配置示例

### 添加自定义任务

1. 在main.py中添加任务类：

```python
@register_task("custom_task")
class CustomTask:
    async def run(self, **params) -> dict:
        return {"result": "自定义任务完成"}
```

2. 在workflow.json中使用：

```json
{
  "name": "自定义任务",
  "type": "task",
  "func": "custom_task"
}
```

### 修改提示模板

直接编辑对应的md文件即可立即生效，无需重启程序。

## 故障排除

1. **依赖安装失败**：检查网络连接，手动运行`cd env && pip install -e .`
2. **JSON解析错误**：检查workflow.json格式是否正确
3. **任务执行失败**：确认对应的md提示文件存在且格式正确