"""
Generate Lulu AI Stock Cards via Claude API.
One API call per stock for maximum analysis quality.
"""
import os
import base64
import logging
from datetime import datetime
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_MODEL_CHEAP, TAX_RATE

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """你是 Lulu AI Stock Analyst，专门为美股投资者生成简洁精准的操作参考卡片。

你的输出规则：
1. 纯文本，不用 markdown 符号（无*、无#、无-，挂单计划缩进使用空格）
2. 严格按照指定格式输出，不加多余内容
3. 数字精确到小数点后2位
4. 语言：中文，简洁有力
5. 一句话建议必须直接说操作建议，不废话

格式模板（每行必须有，顺序不变）：
[SYMBOL]（$[价格]  [涨跌幅]%）
状态：[一句话当前状态]
买点波段：[当前处于第几波或哪种形态]
AI层：[该股在AI产业链的层级定位]
市值与弹性：[例如：1250亿大盘股，盘子重拉升慢 / 30亿小盘股，高弹性资金易推升]
下季财报：[日期及倒计时备注，如“2026-08-27（还有 90 天）”，“已于 3 天前发布”或“暂无数据”]
综合评分：[X/10]
长期趋势：[X/10]
当前买点：[X/10]
MACD：[状态描述]
RSI：[数值，状态说明]
Volume：[成交量状态及含义]
关键支撑：[价格区间1]  /  [价格区间2]  /  [价格区间3]
关键阻力：[价格区间1]  /  [价格区间2]
正常目标：$[价格区间]（约 +[X]%–[Y]%，税后约 +[A]%–[B]%）
乐观目标：$[价格区间]（约 +[X]%–[Y]%，税后约 +[A]%–[B]%）
明天操作：[具体操作建议，如“挂单”、“观望”、“低吸买入”、“分批建仓”]
挂单计划：
  价格1：$[具体挂单价格]，投入 [比例，如30]%，触达概率 [高/中/低]，理由：[简短技术面原因]
  价格2：$[具体挂单价格]，投入 [比例，如40]%，触达概率 [高/中/低]，理由：[简短技术面原因]
  价格3：$[具体挂单价格]，投入 [比例，如30]%，触达概率 [高/中/低]，理由：[简短技术面原因]
止损/失效条件：[说明跌破什么具体价格且放量，或指标如何死叉时短线趋势失效]
仓位建议：[如：小仓、中仓、重仓、小仓到中仓]
防守：[原本的止损位和触发条件]
一句话：[最终操作建议，必须包含具体挂单或防守的价格数字，如：挂单 $200.40 (EMA50)]

【特别注意】：
1. 如果技术评分中的『当前买点初步评分』大于等于 6.0 分，意味着系统量化判定目前是一个极佳的买入窗口（如深度回踩均线或极度超卖）。此时，你的『明天操作』和『一句话』必须明确给出积极的【买入/建仓】建议，不要一味劝退或观望！
2. 当前发送时间语境为：{session_context}。请根据时间点微调你的『明天操作』标题（例如盘后改为“明天挂单计划”，盘中改为“尾盘抢筹计划”等）。"""


def _build_prompt(stock: dict, session: str = "close") -> str:
    ind = stock["indicators"]
    fib = stock.get("fib", {})
    pivots = stock.get("pivots", {})
    news = stock.get("news_text", "暂无近期新闻")
    info = stock.get("info", {})
    tax_percent_str = f"{TAX_RATE * 100:.0f}%"
    symbol = stock["symbol"]

    def fmt(v, decimals=2):
        if v is None:
            return "N/A"
        return f"{v:.{decimals}f}"

    ema_lines = "\n".join(
        f"  EMA{p}: ${fmt(ind.get(f'ema{p}'))}" for p in [10, 20, 50, 100, 200]
    )

    fib_lines = ""
    if fib:
        fib_lines = f"""
斐波那契回撤（近{60}日 High: ${fib.get('swing_high','?')}  Low: ${fib.get('swing_low','?')}）：
  0.236: ${fib.get('0.236','?')}  |  0.382: ${fib.get('0.382','?')}  |  0.5: ${fib.get('0.5','?')}  |  0.618: ${fib.get('0.618','?')}"""

    pivot_lines = ""
    if pivots:
        pivot_lines = f"""
Pivot Points（前一交易日）：
  P: ${pivots.get('P','?')}  R1: ${pivots.get('R1','?')}  R2: ${pivots.get('R2','?')}  S1: ${pivots.get('S1','?')}  S2: ${pivots.get('S2','?')}"""

    bb_lower = ind.get("bb_lower")
    bb_upper = ind.get("bb_upper")
    bb_line = f"  Bollinger Bands: Lower ${fmt(bb_lower)}  Upper ${fmt(bb_upper)}" if bb_lower else ""

    fib_band_line = ""
    fib_band_mid = ind.get("fib_band_mid")
    if fib_band_mid is not None:
        fib_band_line = f"""  Fibonacci Bollinger Bands (Fib Bands):
    Upper3: ${fmt(ind.get('fib_band_u3'))} | Upper2: ${fmt(ind.get('fib_band_u2'))} | Upper1: ${fmt(ind.get('fib_band_u1'))}
    Middle: ${fmt(fib_band_mid)}
    Lower1: ${fmt(ind.get('fib_band_l1'))} | Lower2: ${fmt(ind.get('fib_band_l2'))} | Lower3: ${fmt(ind.get('fib_band_l3'))}"""

    kdj_k = ind.get("kdj_k")
    kdj_d = ind.get("kdj_d")
    kdj_j = ind.get("kdj_j")
    kdj_line = ""
    if kdj_k is not None:
        kdj_line = f"  KDJ(9,3,3)：K={fmt(kdj_k, 1)}  D={fmt(kdj_d, 1)}  J={fmt(kdj_j, 1)}"

    vol_ratio = ind.get("vol_ratio", 1.0)
    vol_desc = "放量" if vol_ratio > 1.3 else ("缩量" if vol_ratio < 0.7 else "正常量")

    rsi = ind.get("rsi")
    rsi_state = ""
    if rsi is not None:
        if rsi < 30:
            rsi_state = "超卖区域"
        elif rsi < 45:
            rsi_state = "偏低，健康回调"
        elif rsi < 55:
            rsi_state = "中性"
        elif rsi < 70:
            rsi_state = "偏强"
        else:
            rsi_state = "超买，注意回调风险"

    macd_hist = ind.get("macd_hist", 0) or 0
    prev_macd_hist = ind.get("prev_macd_hist", 0) or 0
    if macd_hist > 0 and prev_macd_hist <= 0:
        macd_state = "刚刚金叉，动能转多"
    elif macd_hist < 0 and prev_macd_hist >= 0:
        macd_state = "刚刚死叉，动能转空"
    elif macd_hist > 0 and macd_hist > prev_macd_hist:
        macd_state = "金叉上方，动能增强"
    elif macd_hist > 0:
        macd_state = "金叉上方，动能减弱"
    elif macd_hist < 0 and macd_hist < prev_macd_hist:
        macd_state = "死叉下方，空头加速"
    else:
        macd_state = "死叉下方，动能趋缓"

    sector = info.get("sector", "")
    industry = info.get("industry", "")
    company = info.get("name", symbol)
    market_cap = info.get("market_cap", 0)
    
    market_cap_str = "未知"
    if market_cap:
        if market_cap >= 1e12:
            market_cap_str = f"{market_cap / 1e12:.2f} 万亿美元"
        elif market_cap >= 1e8:
            market_cap_str = f"{market_cap / 1e8:.2f} 亿美元"
        else:
            market_cap_str = f"${market_cap:,.0f}"

    earnings_date = info.get("earnings_date", "")
    days_to_earnings = info.get("days_to_earnings")
    earnings_info = "暂无数据"
    if earnings_date:
        earnings_info = f"{earnings_date}"
        if days_to_earnings is not None:
            if days_to_earnings > 0:
                earnings_info += f"（还有 {days_to_earnings} 天）"
            elif days_to_earnings == 0:
                earnings_info += "（今日财报！）"
            else:
                earnings_info += f"（已于 {-days_to_earnings} 天前发布）"

    chg_sign = "+" if ind.get("chg_1d_pct", 0) >= 0 else ""

    return f"""分析以下股票，生成一张 Lulu AI Stock Card：

股票：{symbol}  公司：{company}
板块：{sector} / {industry}
市值：{market_cap_str}
下季财报：{earnings_info}
当前价格：${fmt(ind.get('price'))}  （今日{chg_sign}{fmt(ind.get('chg_1d_pct'))}%  本周{'+' if (ind.get('chg_5d_pct') or 0) >= 0 else ''}{fmt(ind.get('chg_5d_pct'))}%）

移动均线：
{ema_lines}

动量指标：
  RSI(14)：{fmt(rsi, 1)}  （{rsi_state}）
  MACD(12,26,9)：{macd_state}
    MACD值: {fmt(ind.get('macd'), 4)}  信号线: {fmt(ind.get('macd_signal'), 4)}  柱状: {fmt(macd_hist, 4)}
{kdj_line}

成交量：
  今日量 vs 20日均量：{vol_ratio:.1f}x  （{vol_desc}）
  今日量：{ind.get('volume', 0):,}  20日均量：{ind.get('vol_avg20', 0):,}

{bb_line}
{fib_band_line}
{fib_lines}
{pivot_lines}

近期新闻：
{news}

技术评分参考（供你综合判断）：
  长期趋势初步评分：{stock.get('trend_score', 5)}/10
  当前买点初步评分：{stock.get('entry_score', 5)}/10

税率说明（用于估算税后目标收益）：
  本账户适用的预计短期资本利得税率为：{tax_percent_str}。
  计算公式：税后涨幅 % = 税前涨幅 % * (1 - {TAX_RATE:.2f})。请依据此税率计算『正常目标』和『乐观目标』的税后收益率，并严格按照格式模板输出。

请输出该股的 Lulu AI Stock Card，严格按照系统提示中的格式模板。"""


def generate_card(stock: dict, use_cheap_model: bool = False, session: str = "close") -> str:
    """Call Claude and return the formatted card text."""
    try:
        session_context = {
            "open": "开盘异动扫描 (10:00 ET)，早盘波动剧烈，寻找日内最佳入场点",
            "mid": "盘中趋势确认 (13:00 ET)，趋势趋稳，排查假突破或洗盘",
            "close": "尾盘绝杀抢筹 (15:45 ET)，日内方向已定，是波段建仓的最重要时刻",
            "post": "盘后复盘总结 (20:00 ET)，总结当日走势与盘后新闻，制定明天的挂单计划"
        }.get(session, "常规分析")
        
        system_prompt = SYSTEM_PROMPT.replace("{session_context}", session_context)
        prompt = _build_prompt(stock, session)
        client = _get_client()
        model_to_use = CLAUDE_MODEL_CHEAP if use_cheap_model else CLAUDE_MODEL
        resp = client.messages.create(
            model=model_to_use,
            max_tokens=1200,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"Card generation failed for {stock['symbol']}: {e}")
        ind = stock["indicators"]
        return (
            f"{stock['symbol']}（${ind.get('price', '?')}）\n"
            f"状态：数据获取正常，AI分析暂时失败\n"
            f"一句话：请手动检查图表"
        )



def generate_card_with_vision(stock: dict, image_path: str, session: str = "close") -> str:
    """Call Claude with both the stock data and a screenshot of the chart."""
    try:
        if not os.path.exists(image_path):
            logger.error(f"Screenshot path does not exist: {image_path}. Falling back to text-only.")
            return generate_card(stock, session=session)
            
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("utf-8")
            
        session_context = {
            "open": "开盘异动扫描 (10:00 ET)，早盘波动剧烈，寻找日内最佳入场点",
            "mid": "盘中趋势确认 (13:00 ET)，趋势趋稳，排查假突破或洗盘",
            "close": "尾盘绝杀抢筹 (15:45 ET)，日内方向已定，是波段建仓的最重要时刻",
            "post": "盘后复盘总结 (20:00 ET)，总结当日走势与盘后新闻，制定明天的挂单计划"
        }.get(session, "常规分析")
        
        system_prompt = SYSTEM_PROMPT.replace("{session_context}", session_context)
        
        text_prompt = _build_prompt(stock, session)
        # Add visual check instructions to prompt
        text_prompt += "\n\n【视觉校验要求】：同时参考上传的 TradingView 截图（其中包含 EMA20/50/200 均线、RSI、MACD指标）。比对给定的技术数据与图表形态。如果两者一致，请原样按照模板格式输出卡片；如果视觉图表显示存在明显的趋势背离、均线缠绕、MACD/RSI 拐点偏离或画线阻力支撑差错，请以图表视觉呈现为准修正卡片中『状态』、『买点波段』、『防守』与『一句话』的描述，并在相关部分点出视觉上看到的具体盘面细节（如：价格正处于斐波那契回撤阻力位，或K线出现长下影线等）。确保卡片文字与图片视觉内容相符。"

        client = _get_client()
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1200,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": text_prompt
                        }
                    ]
                }
            ]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"Card generation with vision failed for {stock['symbol']}: {e}. Falling back to text-only.")
        return generate_card(stock)


def build_daily_header(session_label: str) -> str:

    """Build the header line for the daily card message."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    return (
        f"📊 LULU AI STOCK CARDS — {date_str} {session_label}\n"
        f"{'═' * 42}"
    )
