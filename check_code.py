#!/usr/bin/env python3
"""检查代码语法"""

import sys
import os
import ast

def check_syntax(file_path):
    """检查文件的语法"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ast.parse(content)
        print(f"✓ {file_path} 语法正确")
        return True
    except SyntaxError as e:
        print(f"✗ {file_path} 语法错误: {e}")
        return False
    except Exception as e:
        print(f"✗ {file_path} 错误: {e}")
        return False

def main():
    """检查所有Python文件的语法"""
    print("检查代码语法...")
    
    # 要检查的文件
    files = [
        'src/agents/scenario_agent.py',
        'src/rag/light_rag.py',
        'src/main.py',
        'test_agent.py'
    ]
    
    all_correct = True
    for file in files:
        if os.path.exists(file):
            if not check_syntax(file):
                all_correct = False
        else:
            print(f"✗ {file} 文件不存在")
            all_correct = False
    
    if all_correct:
        print("\n所有文件语法正确！")
    else:
        print("\n存在语法错误，请检查。")

if __name__ == "__main__":
    main()
