# 📊 Lulu AI Stock Card Bot (Mega Watchlist Edition)

**Lulu AI Stock Card Bot** 是一个专为美股投资者设计的智能量化分析与交易决策助手。它能够在交易时段（开盘、盘中、收盘前）自动拉取美股数据，计算技术指标，抓取新闻，并生成高清 TradingView 截图。

本版本专为 **50+ 只股票的 Mega Watchlist** 打造，创新性地引入了 **Python 极速筛选 + 大模型混合架构 (Hybrid Model)**，能在兼顾成本（每月低至 $6）的前提下，实现极高水准的 AI 图文看盘。

---

## 🗺️ 系统原理与大模型混合架构 (Hybrid Architecture)

为了解决 API Token 成本和信息过载问题，系统采取了以下架构：

```mermaid
graph TD
    A[watchlist.txt 50只股票池] -->|定时触发| B[main.py 主程序]
    
    subgraph 第一层：极速初筛与排名 (Python)
        B --> C[拉取 OHLCV / 计算 EMA, MACD, RSI]
        C --> D[scorer.py 量化打分]
        D -->|计算: 趋势 + 买点 + 财报/异动加权| E[生成 Urgent Ranking]
    end
    
    subgraph 第二层：混合大模型架构 (Hybrid Model)
        E -->|Top 1-5 名| F[截图 + Claude 3.5 Sonnet 多模态深扒]
        E -->|第 6-50 名| G[纯量化数据 + Claude 3 Haiku 极速汇总]
    end
    
    F --> H[组合为极简带 Tag 的 Summary + Top 5 详情卡片]
    G --> H
    H -->|推送| I[Telegram 群组]
```

### 🧠 混合大模型策略 (Cost Optimization)
所有的数学指标（EMA, MACD, 财报日, 税后收益估算）均由 Python 精准算出，绝不依赖大模型。大模型仅负责语言理解与形态归纳：
- **前 5 名（Top 5 Actionable）**：自动调用最聪明的 `Claude 3.5 Sonnet`，搭配高管 TradingView 截图进行**视觉核对**。
- **后 45 名（Observation）**：自动调用超快且极便宜的 `Claude 3 Haiku`，仅生成文字一句话建议，不上报截图。

---

## 🏆 排名引擎逻辑 (Scoring Engine)

**系统并不依赖大模型进行排名**，而是由 `src/scorer.py` 免费、瞬间完成 50 只股票的筛选，确保最有操作价值的股票进入 Top 5：

1. **买点得分 (Entry Score, 60%)**：
   - 价格正好回踩触及 EMA20 / EMA50 支撑位（大幅加分）。
   - MACD 刚刚金叉或动能转多（大幅加分）。
   - RSI 跌入极度超卖区间（加分）；若极度超买（扣分）。
2. **长线趋势 (Trend Score, 40%)**：
   - 价格站在 EMA200/100/50 之上，证明多头排列健康。
3. **⭐事件驱动权重 (Event-Driven Bonus, 强制抢占 Top 5)**：
   - **财报临近**：如果某只股票在 **未来 3 天内** 发财报，直接 +3 分，强制送入 Top 5，带上 🔥 标签。
   - **巨量异动**：如果今天成交量超过平时 **2.5 倍**，直接 +2 分，强制送入 Top 5，带上 🚀 标签。

---

## 🎯 核心 AI 提示词 (System Prompt)

系统采用严苛的提示词模板，倒逼大模型生成可以直接挂单的“交易计划”，而非模糊的废话：

```text
你是 Lulu AI Stock Analyst，专门为美股投资者生成简洁精准的操作参考卡片。

格式模板（每行必须有，顺序不变）：
[SYMBOL]（$[价格]  [涨跌幅]%）
状态：[一句话当前状态]
买点波段：[当前处于第几波或哪种形态]
AI层：[该股在AI产业链的层级定位]
下季财报：[日期及倒计时]
综合评分：[X/10] 
长期趋势：[X/10] 当前买点：[X/10]
MACD：[状态] | RSI：[数值] | Volume：[状态]
关键支撑：[区间] | 关键阻力：[区间]
正常目标：$[价格]（约 +[X]%，税后约 +[A]%）
乐观目标：$[价格]（约 +[Y]%，税后约 +[B]%）
明天操作：[挂单/观望/低吸/分批]
挂单计划：
  价格1：$[挂单价]，投入 30%，触达概率 [高/中/低]，理由：[技术面原因]
  价格2：$[挂单价]，投入 40%，触达概率 [高/中/低]，理由：[技术面原因]
  价格3：$[挂单价]，投入 30%，触达概率 [高/中/低]，理由：[技术面原因]
止损/失效条件：[跌破某价格且放量]
仓位建议：[仓位大小]
防守：[触发条件]
一句话：[最终操作建议，必须包含具体挂单或防守的价格数字，如：挂单 $200.40 (EMA50)]
```

---

## 🛠️ 快速上手与 GitHub 自动化

### 1. 准备您的 Watchlist
在 `watchlist.txt` 中写入您关注的股票及对应 Tag，例如：
```text
NVDA,核心底仓
VRT,AI基建
APLD,AI高弹性
```

### 2. 配置环境 (.env / GitHub Secrets)
必须配置以下环境变量（本地放在 `.env`，GitHub 上放在 **Settings -> Secrets and variables -> Actions**）：

```env
ANTHROPIC_API_KEY=your_anthropic_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
# 推荐填入以下两项以开启双模型省钱架构：
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_MODEL_CHEAP=claude-haiku-4-5-20251001
```

### 3. GitHub Actions 自动部署
由于包含了浏览器内核下载，直接在 GitHub Actions 上运行是最稳定且免费的。
在完成代码修改后，只需运行以下终端命令即可将代码推送到云端开启自动化：

```bash
git add .
git commit -m "Upgrade to Mega Watchlist with Hybrid Models and Top 5 truncating"
git push origin claude/lulu-stock-card-bot-VEOLw
```

配置好 Secret 后，GitHub 会在每个工作日的美东时间 `9:45`、`13:00`、`15:45` 自动触发！
