# main.py

import requests
import json
import time

# 请在此处填入你申请的百度百科API Key
API_KEY = ""

# 按分类补全的装备搜索列表（去重、标准化）
EQUIPMENT_LIST = [
    # ===== 海军装备 =====
    # 航空母舰（用具体舰名代替分类描述，更易获得百科词条）
    "辽宁号航空母舰",
    "山东号航空母舰",
    "福建号航空母舰",
    # 驱逐舰
    "055型驱逐舰",
    "052D型驱逐舰",
    "051C型驱逐舰",
    # 护卫舰
    "054A型护卫舰",
    "056型护卫舰",
    # 两栖攻击舰
    "075型两栖攻击舰",
    "076型两栖攻击舰",
    # 舰载战斗机
    "歼-15",
    "歼-15T",
    "歼-35",
    "歼-15D",
    # 核潜艇
    "093型攻击核潜艇",
    "094型战略核潜艇",
    "096型战略核潜艇",
    # 补给舰
    "901型综合补给舰",
    "903型综合补给舰",
    "903A型综合补给舰",
    # 海军导弹
    "鹰击-12",
    "鹰击-18",
    "鹰击-18C",
    "鹰击-21",
    "鹰击-62",
    "鹰击-83",
    "巨浪-2",
    "巨浪-3",

    # ===== 空军与航空兵装备 =====
    # 战斗机（含舰载重复项已去重）
    "歼-20",
    "歼-20T",
    "歼-16",
    "歼-10",
    "歼-11",
    "歼-35A",
    "歼-15DT",
    "苏-30",
    "苏-35",
    # 战斗轰炸机
    "歼轰-7",
    # 轰炸机
    "轰-6K",
    "轰-6N",
    "轰-20",
    # 预警指挥机
    "空警-3000",
    "空警-500",
    "空警-2000",
    "空警-600",
    "空警-200",
    # 运输机/加油机
    "运-20",
    "运油-20",
    # 机载导弹
    "霹雳-10",
    "霹雳-12",
    "霹雳-15",

    # ===== 陆军与通用装备 =====
    # 主战装备
    "99A主战坦克",
    "15式轻型坦克",
    "ZBD-04A步兵战车",
    # 火炮/火箭炮
    "PLZ-05自行加榴炮",
    "PHZ-11火箭炮",
    "PLZ-07B自行榴弹炮",
    "191远程箱式火箭炮",
    "PHL-03自行火箭炮",
    "卫士-2火箭炮",
    "神鹰400制导火箭炮",
    # 支援火炮
    "155车载加榴炮",

    # ===== 火箭军与战略支援 =====
    # 战略/战术导弹
    "东风-5",
    "东风-31",
    "东风-41",
    "东风-26",
    "东风-26D",
    "东风-27",
    "东风-21",
    "东风-17",
    "东风-11",
    "东风-15",
    # 巡航导弹
    "长剑-10",
    "长剑-100",
    "长剑-20A",
    "长剑-1000",

    # ===== 无人系统与前沿技术 =====
    # 无人机
    "攻击-11",
    "彩虹-7",
    "无侦-6",
    "WJ-700",
    "翼龙-2H",
    "彩虹-6",
    "阿特拉斯",
    # 新概念武器
    "电磁炮",
    "电磁脉冲武器",
    "反卫星激光武器",
    "车载激光武器",
    "舰载激光武器",
    # 预警雷达
    "YKDP-2",
    "JL-1A",
    "7010相控阵雷达",
    "110单脉冲战略预警雷达",
    "JY-27",
    "YLC-2B",
    # 防空导弹
    "红旗-9",
    "红旗-16",
    "红旗-17",
    "红旗-22",
    "红旗-19"
]


# 百度百科API的接口地址
API_URL = "https://appbuilder.baidu.com/v2/baike/lemma/get_content"

def search_baike(keyword):
    """
    使用百度百科API搜索词条信息。
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    params = {
        "search_type": "lemmaTitle",  # 按词条名称搜索[reference:2]
        "search_key": keyword
    }
    print(headers)
    try:
        # 发送GET请求
        response = requests.get(API_URL, headers=headers, params=params)
        response.raise_for_status()  # 如果请求失败，抛出HTTPError异常
        data = response.json()

        # 根据API返回的数据结构提取信息[reference:3]
        if not data.get("code"):  # 0表示成功
            result = data.get("result", {})
            info = {
                "title": result.get("lemma_title", keyword),
                "description": result.get("lemma_desc", ""),
                "summary": result.get("summary", ""),
            }
            return info
        else:
            print(f"  [!] 词条 '{keyword}' 未获取到有效数据，状态码：{data.get('code')}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"  [X] 请求词条 '{keyword}' 时发生网络错误：{e}")
        return None
    except json.JSONDecodeError as e:
        print(f"  [X] 解析词条 '{keyword}' 的数据失败：{e}")
        return None

def main():
    """
    主函数，用于遍历装备列表、调用API并生成Markdown文件。
    """
    # 用于存储所有搜索结果
    results = []

    print("开始搜索百度百科词条...")
    for i, equipment in enumerate(EQUIPMENT_LIST, 1):
        print(f"  [{i}/{len(EQUIPMENT_LIST)}] 正在搜索词条：{equipment}")
        info = search_baike(equipment)
        if info:
            results.append(info)
        # 增加小延时，降低请求频率，避免对服务器造成压力
        time.sleep(1)

    # 生成Markdown内容
    md_content = "# 武器装备百科信息汇总\n\n"
    md_content += "本页面信息由Python程序自动从百度百科抓取并生成。\n\n"

    for item in results:
        md_content += f"## {item['title']}\n"
        if item['description']:
            md_content += f"- **词条描述**：{item['description']}\n"
        if item['summary']:
            md_content += f"- **摘要**：{item['summary']}\n"
        md_content += "\n---\n\n"

    # 写入Markdown文件
    output_filename = "军事百科.md"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"任务完成！搜索结果已写入文件：{output_filename}")

if __name__ == "__main__":
    main()