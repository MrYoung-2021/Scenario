# 想定基本格式

## 想定结构
一个有效的想定应包含以下基本结构：

### 1. 基本信息
- `name`：想定名称（字符串）
- `type`：想定类型（字符串，如"陆战"、"海战"、"空战"、"联合作战"）
- `background`：想定背景（字符串）
- `timeframe`：想定时间范围（对象，包含start和end字段）

### 2. 红蓝双方
- `red_force`：红方信息（对象）
  - `organization`：部队编制（字符串）
  - `mission`：任务目标（字符串）
  - `area`：作战区域（字符串）
  - `capabilities`：作战能力（对象，包含strengths和weaknesses字段）
- `blue_force`：蓝方信息（对象）
  - `organization`：部队编制（字符串）
  - `mission`：任务目标（字符串）
  - `area`：作战区域（字符串）
  - `capabilities`：作战能力（对象，包含strengths和weaknesses字段）

### 3. 战场环境
- `terrain`：地形（字符串）
- `weather`：气象（字符串）
- `electromagnetic`：电磁环境（字符串）
- `time_factors`：时间因素（字符串）

### 4. 作战阶段
- `phases`：作战阶段（数组，每个元素包含name和actions字段）

### 5. 评估指标
- `assessment`：评估指标（对象）
  - `casualties`：损失情况（对象，包含red和blue字段）
  - `mission_completion`：任务完成情况（数字，0-100）
  - `combat_effectiveness`：作战效能（数字，0-100）

### 6. 特殊情况
- `special_cases`：特殊情况（对象）
  - `emergencies`：突发情况（数组）
  - `restrictions`：规则限制（数组）

## 示例格式
```json
{
  "name": "示例想定",
  "type": "陆战",
  "background": "地区冲突升级",
  "timeframe": {
    "start": "2024-01-01",
    "end": "2024-01-07"
  },
  "red_force": {
    "organization": "机械化步兵师",
    "mission": "夺取战略要地",
    "area": "北部山区",
    "capabilities": {
      "strengths": ["装备先进", "训练有素"],
      "weaknesses": ["后勤补给困难"]
    }
  },
  "blue_force": {
    "organization": "装甲旅",
    "mission": "防御战略要地",
    "area": "北部山区",
    "capabilities": {
      "strengths": ["地形熟悉", "防御工事完善"],
      "weaknesses": ["装备老化"]
    }
  },
  "battlefield_environment": {
    "terrain": "山地地形，起伏较大",
    "weather": "冬季，低温，可能降雪",
    "electromagnetic": "存在轻度电磁干扰",
    "time_factors": "昼夜温差大，夜间能见度低"
  },
  "phases": [
    {
      "name": "侦察阶段",
      "actions": "双方进行侦察活动，收集情报"
    },
    {
      "name": "进攻阶段",
      "actions": "红方发起进攻，蓝方组织防御"
    },
    {
      "name": "收尾阶段",
      "actions": "双方调整部署，评估战果"
    }
  ],
  "assessment": {
    "casualties": {
      "red": "轻度",
      "blue": "中度"
    },
    "mission_completion": 75,
    "combat_effectiveness": 80
  },
  "special_cases": {
    "emergencies": ["可能出现恶劣天气"],
    "restrictions": ["禁止使用化学武器"]
  }
}
```
