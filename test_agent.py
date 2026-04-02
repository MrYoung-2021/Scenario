#!/usr/bin/env python3
"""测试Scenario Agent核心功能"""

import sys
import os

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.agents.scenario_agent import run_scenario_agent

def test_agent():
    """测试Scenario Agent"""
    print("测试Scenario Agent...")
    
    # 测试输入
    user_input = "生成一个陆战想定"
    
    try:
        # 运行agent
        result = run_scenario_agent(user_input)
        
        # 打印结果
        print("\n测试结果:")
        print(f"最终想定: {result['final_scenario']['name']}")
        print(f"评估结果: {'通过' if result['evaluation_result']['passed'] else '不通过'}")
        if not result['evaluation_result']['passed']:
            print(f"问题: {result['evaluation_result']['issues']}")
        print("\n测试成功！")
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        return False

if __name__ == "__main__":
    # test_agent()
    # from langchain_classic.indexes import SQLRecordManager, index
    # record_manager = SQLRecordManager(
    #     namespace="chroma/my_docs",
    #     db_url=f"sqlite:///{os.path.join('D:/Workspace/Scenario/src/chroma_db', 'record_manager.sqlite')}"
    # )
    # record_manager.create_schema()
    sdf = [1,2]
    su = [5,6]
    ss = '; '.join(zip(sdf, su))
    print(ss)
    pass
