import json
import os
import subprocess
import shutil
from datetime import datetime

def run_tasks():
    # 定义路径
    ques_all_path = 'question/ques_all.json'
    ques_path = 'question/ques.json'
    workspace_dir = 'workspace/'
    cache_base_dir = 'cache/'

    # 确保必要的目录存在
    os.makedirs(cache_base_dir, exist_ok=True)

    # 1. 读取 ques_all.json
    if not os.path.exists(ques_all_path):
        print(f"错误: 找不到 {ques_all_path}")
        return

    with open(ques_all_path, 'r', encoding='utf-8') as f:
        try:
            ques_list = json.load(f)
        except json.JSONDecodeError:
            print(f"错误: {ques_all_path} 格式不正确")
            return

    if not isinstance(ques_list, list):
        print("错误: ques_all.json 应该是一个包含对象的列表")
        return

    # 2. 遍历处理每个对象
    for index, ques_obj in enumerate(ques_list):
        print(f"\n--- 正在处理第 {index + 1}/{len(ques_list)} 个任务 ---")

        # 写入 ques.json (清空并更新)
        with open(ques_path, 'w', encoding='utf-8') as f:
            json.dump(ques_obj, f, indent=4, ensure_ascii=False)
        print(f"已更新 {ques_path}")

        # 3. 运行 main.py
        try:
            print(f"正在运行 main.py...")
            # 使用 subprocess.run 等待运行结束
            subprocess.run(['python', 'main.py'], check=True)
            print("main.py 运行成功")
        except subprocess.CalledProcessError as e:
            print(f"警告: main.py 运行过程中出错: {e}")
            # 如果 main.py 出错，你可以根据需求决定是否继续
            # continue 

        # 4. 缓存 workspace/ 到 cache/ (带上时间戳)
        # 生成时间戳字符串，格式为：年ymd_时分秒
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 文件夹名示例: run_0_20231027_143005
        cache_folder_name = f"run_{index}_{timestamp}"
        current_cache_dir = os.path.join(cache_base_dir, cache_folder_name)
        
        # 复制整个 workspace 文件夹
        if os.path.exists(workspace_dir):
            try:
                shutil.copytree(workspace_dir, current_cache_dir)
                print(f"已将 {workspace_dir} 缓存至 {current_cache_dir}")
            except Exception as e:
                print(f"缓存失败: {e}")
        else:
            print(f"警告: {workspace_dir} 文件夹不存在，无法执行缓存")

    print("\n所有任务已按顺序处理完毕。")

if __name__ == "__main__":
    run_tasks()