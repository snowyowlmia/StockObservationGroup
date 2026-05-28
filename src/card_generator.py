"""
Generate Lulu AI Stock Cards via Claude API.
One API call per stock for maximum analysis quality.
"""
import os
import base64
import logging
from datetime import datetime
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """你是 Lulu AI Stock Analyst，专门为美股投资者生成简洁精准的操作参考卡片。

你的输出规则：
1. 纯文本，不用 markdown 符号（无*、无#、无-）
2. 严格按照指定格式输出，不加多余内容
3. 数字精确到小数点后2位
4. 语言：中文，简洁有力
5. 一句话建议必须直接说操作建议，不废话

格式模板（每行必须有，顺序不变）：
[SYMBOL]（$[价格]  [涨跌幅]%）
状态：[一句话当前状态]
买点波段：[当前处于第几波或哪种形态]
AI层：[该股在AI产业链的层级定位]
综合评分：[X/10]
长期趋势：[X/10]
当前买点：[X/10]
MACD：[状态描述]
RSI：[数值，状态说明]
Volume：[成交量状态及含义]
关键支撑：[价格区间1]  /  [价格区间2]  /  [价格区间3]
关键阻力：[价格区间1]  /  [价格区间2]
防守：[止损位和触发条件]
一句话：[最终操作建议]"""


def _build_prompt(stock: dict) -> str:
    ind = stock["indicators"]
    fib = stock.get("fib", {})
    pivots = stock.get("pivots", {})
    news = stock.get("news_text", "暂无近期新闻")
    info = stock.get("info", {})
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

    chg_sign = "+" if ind.get("chg_1d_pct", 0) >= 0 else ""

    return f"""分析以下股票，生成一张 Lulu AI Stock Card：

股票：{symbol}  公司：{company}
板块：{sector} / {industry}
当前价格：${fmt(ind.get('price'))}  （今日{chg_sign}{fmt(ind.get('chg_1d_pct'))}%  本周{'+' if (ind.get('chg_5d_pct') or 0) >= 0 else ''}{fmt(ind.get('chg_5d_pct'))}%）

移动均线：
{ema_lines}

动量指标：
  RSI(14)：{fmt(rsi, 1)}  （{rsi_state}）
  MACD(12,26,9)：{macd_state}
    MACD值: {fmt(ind.get('macd'), 4)}  信号线: {fmt(ind.get('macd_signal'), 4)}  柱状: {fmt(macd_hist, 4)}

成交量：
  今日量 vs 20日均量：{vol_ratio:.1f}x  （{vol_desc}）
  今日量：{ind.get('volume', 0):,}  20日均量：{ind.get('vol_avg20', 0):,}

{bb_line}
{fib_lines}
{pivot_lines}

近期新闻：
{news}

技术评分参考（供你综合判断）：
  长期趋势初步评分：{stock.get('trend_score', 5)}/10
  当前买点初步评分：{stock.get('entry_score', 5)}/10

请输出该股的 Lulu AI Stock Card，严格按照系统提示中的格式模板。"""


def generate_card(stock: dict) -> str:
    """Call Claude and return the formatted card text."""
    try:
        prompt = _build_prompt(stock)
        client = _get_client()
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            system=SYSTEM_PROMPT,
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



def generate_card_with_vision(stock: dict, image_path: str) -> str:
    """Call Claude with both the stock data and a screenshot of the chart."""
    try:
        if not os.path.exists(image_path):
            logger.error(f"Screenshot path does not exist: {image_path}. Falling back to text-only.")
            return generate_card(stock)
            
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("utf-8")
            
        text_prompt = _build_prompt(stock)
        # Add visual check instructions to prompt
        text_prompt += "\n\n【视觉校验要求】：同时参考上传的 TradingView 截图（其中包含 EMA20/50/200 均线、RSI、MACD指标）。比对给定的技术数据与图表形态。如果两者一致，请原样按照模板格式输出卡片；如果视觉图表显示存在明显的趋势背离、均线缠绕、MACD/RSI 拐点偏离或画线阻力支撑差错，请以图表视觉呈现为准修正卡片中『状态』、『买点波段』、『防守』与『一句话』的描述，并在相关部分点出视觉上看到的具体盘面细节（如：价格正处于斐波那契回撤阻力位，或K线出现长下影线等）。确保卡片文字与图片视觉内容相符。"

        client = _get_client()
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            system=SYSTEM_PROMPT,
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
