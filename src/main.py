#!/usr/bin/env python3
"""Scenario Agent 主入口文件"""

import sys
import json
import time
from rich.console import Console
from rich.panel import Panel
from rich.json import JSON

from agents.scenario_agent import run_scenario_agent
from utils.logger import get_logger, get_log_file

console = Console()
logger = get_logger()

def main():
    """主函数"""
    console.print(Panel("🎯 Scenario Agent", border_style="blue"))
    console.print("欢迎使用仿真想定生成Agent！")
    console.print("请输入您的想定需求，或输入 'exit' 退出。\n")
    logger.info("Scenario Agent 启动")
    logger.info(f"日志文件路径: {get_log_file()}")
    
    while True:
        # 获取用户输入
        user_input = input("输入: ").strip()
        
        if user_input.lower() == 'exit':
            console.print("👋 再见！")
            logger.info("Scenario Agent 退出")
            break
        
        if not user_input:
            console.print("⚠️  请输入想定需求。")
            logger.warning("用户输入为空")
            continue
        
        try:
            console.print("\n🚀 正在生成想定...")
            logger.info(f"开始生成想定，用户输入: {user_input}")
            # 运行Scenario Agent
            result = run_scenario_agent(user_input)
            
            # 显示结果
            console.print("\n" + "-" * 80)
            console.print("📋 生成结果:")
            
            # 显示最终想定
            console.print("\n🎯 最终仿真想定:")
            # console.print(JSON(json.dumps(result["final_scenario"], ensure_ascii=False, indent=2)))
            console.print(result["final_scenario"])
            logger.info(f"想定生成成功！")
            
            # 显示评估结果
            console.print("\n✅ 评估结果:")
            passed = result["evaluation_result"].get("passed", False)
            status = "通过" if passed else "不通过"
            console.print(f"状态: [{'green' if passed else 'red'}]{status}[/{'green' if passed else 'red'}]")
            logger.info(f"想定评估结果: {status}")
            
            if not passed:
                issues = result["evaluation_result"].get("issues", [])
                suggestions = result["evaluation_result"].get("suggestions", [])
                console.print("\n⚠️  问题:")
                for issue in issues:
                    console.print(f"  - {issue}")
                console.print("\n💡 建议:")
                for suggestion in suggestions:
                    console.print(f"  - {suggestion}")
                logger.warning(f"想定评估不通过，问题: {'; '.join(issues)}")
            
            # 显示反思
            if result.get("reflection"):
                console.print("\n🤔 反思:")
                console.print(result["reflection"])
                logger.info(f"反思内容: {result['reflection']}")
            
            console.print("\n" + "-" * 80)
            
        except Exception as e:
            console.print(f"❌ 出错了: {e}")
            logger.error(f"生成想定出错: {e}", exc_info=True)

        time.sleep(1)

if __name__ == "__main__":
    main()
