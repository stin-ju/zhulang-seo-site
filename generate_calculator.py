#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
计算器页面生成脚本
现在数据从API动态获取，此脚本只负责复制模板到calculator.html
"""

import os

# 读取模板
template_path = os.path.join(os.path.dirname(__file__), 'calculator_template.html')
output_path = os.path.join(os.path.dirname(__file__), 'calculator.html')

with open(template_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 写入输出文件
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ calculator.html 已生成（数据从API动态获取）")
