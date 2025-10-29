from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from difflib import get_close_matches
import os
import requests
import csv
import pandas as pd
import logging
import traceback
import sys
import re
app = Flask(__name__)

# ⚠️ 換成你的 LINE Channel 資料
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 測試頁面
@app.route("/")
def home():
    return "Flask LINE Bot is running!"

# LINE Webhook endpoint
@app.route("/callback", methods=['POST', 'GET', 'OPTIONS'])
def callback():
    # 如果是非 POST，直接回 200，避免 405 Method Not Allowed
    if request.method != 'POST':
        return 'OK', 200

    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK', 200

# 回覆文字訊息
logging.basicConfig(level=logging.ERROR)

# 使用者狀態記錄
user_state = {}

# 嘗試讀取 CSV
try:
    df = pd.read_csv("水果產品日交易行情.csv", encoding="utf-8-sig")
    df.columns = df.columns.str.replace(r'\s+', '', regex=True).str.replace('\ufeff', '')
    df["產品_clean"] = df["產品"].astype(str).str.replace(r"[\s　]+", "", regex=True)
    df["產品_name_only"] = df["產品"].astype(str).str.replace(r"^\d+\s*", "", regex=True)
    print("✅ 成功讀入即時行情資料。")
except Exception as e:
    print("❌ 無法讀入即時行情資料:", e)
    df = pd.DataFrame()

# 產期資料（新的）
try:
    df_crop = pd.read_csv(
        "每月盛產農產品產地.csv",
        encoding="utf-8-sig",
        on_bad_lines="skip",
        engine="python"
    )
    df_crop.columns = df_crop.columns.str.replace(r'\s+', '', regex=True).str.replace('\ufeff', '')
    df_crop = df_crop.applymap(lambda x: str(x).strip().replace("　", "") if isinstance(x, str) else x)
    df_crop.fillna("", inplace=True)
    print(f"✅ 成功讀入產期資料，共 {len(df_crop)} 筆。")
    print(df_crop[df_crop["品項"].astype(str).str.contains("你測不到的那個關鍵字", na=False)])
except Exception as e:
    print("❌ 無法讀入產期資料:", e)
    df_crop = pd.DataFrame()

# ----------- 輔助函式區 -----------

CITY_MAP = {
    "台北": ["台北市"],
    "臺北": ["台北市"],
    "新北": ["新北市"],
    "基隆": ["基隆市", "基隆縣"],
    "桃園": ["桃園市"],
    "新竹": ["新竹市", "新竹縣"],
    "苗栗": ["苗栗縣"],
    "台中": ["台中市"],
    "臺中": ["台中市"],
    "彰化": ["彰化縣"],
    "南投": ["南投縣"],
    "雲林": ["雲林縣"],
    "嘉義": ["嘉義市", "嘉義縣"],
    "台南": ["台南市"],
    "臺南": ["台南市"],
    "高雄": ["高雄市"],
    "屏東": ["屏東縣"],
    "宜蘭": ["宜蘭縣"],
    "花蓮": ["花蓮縣"],
    "台東": ["台東縣"],
    "臺東": ["台東縣"],
    "澎湖": ["澎湖縣"],
    "金門": ["金門縣"],
    "連江": ["連江縣"]
}

TYPE_KEYWORDS = ["水果", "蔬菜", "花卉", "雜糧"]

# 🆕 類型同義詞補充
TYPE_ALIASES = {
    "果類": "水果",
    "蔬果": "蔬菜",
    "糧食": "雜糧"
}

def detect_region_and_type(user_text: str):
    """偵測輸入文字中的地區與類型"""
    regions, crop_type = [], None

    # ✅ 改進：可同時偵測多個地區
    for short, full_list in CITY_MAP.items():
        if short in user_text:
            regions.extend(full_list)

    # ✅ 改進：支援別名轉換（果類→水果、蔬果→蔬菜等）
    for t in TYPE_KEYWORDS + list(TYPE_ALIASES.keys()):
        if t in user_text:
            crop_type = TYPE_ALIASES.get(t, t)
            break

    return regions, crop_type


def normalize_crop_name(name: str) -> str:
    """統一使用者輸入名稱格式"""
    return re.sub(r"[\s　]+", "", name)

def match_crop_in_period_data(keyword: str):
    """以品項名稱模糊搜尋產期資料"""
    keyword = normalize_crop_name(keyword)
    match_rule = df_crop[
        df_crop["品項"].astype(str).str.contains(keyword, case=False, na=False)
    ]
    return match_rule

def expand_fruit_alias(keyword: str):
    """模糊關鍵字補全（同義詞轉換）"""
    mapping = {
        "釋迦": "番荔枝",
        "棗子": "印度棗",
        "梨子": "梨",
        "芭樂": "番石榴",
        "橘子": "柑"
    }
    for k, v in mapping.items():
        if k in keyword:
            return v
    return keyword

# ----------- 主處理邏輯 -----------
required_cols = ["日期", "市場", "產品", "平均價(元/公斤)", "價格增減%"]
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_id = event.source.user_id
        user_text = event.message.text.strip()
        messages = []

        print(f"📩 收到使用者輸入：{user_text}")
        if user_text == "輔助工具":
            user_state[user_id] = "search"
            msg = "很抱歉，輔助工具目前尚未開發完畢🙏\n你可以使用月份、蔬果種類、鄉鎮市等進行查詢功能\n也可以使用即時資訊進行市場價查詢"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
            return
        if user_text == "答題果園":
            user_state[user_id] = "search"
            msg = "很抱歉，答題果園目前尚未開發完畢🙏\n你可以使用月份、蔬果種類、鄉鎮市等進行查詢功能\n也可以使用即時資訊進行市場價查詢"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
            return
        if user_text == "本周水果報":
            user_state[user_id] = "search"
            msg = "很抱歉，本周水果報目前尚未開發完畢🙏\n你可以使用月份、蔬果種類、鄉鎮市等進行查詢功能\n也可以使用即時資訊進行市場價查詢"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
            return
        # -------------------- #
        # 即時查詢入口
        # -------------------- #
        if user_text == "即時資訊":
            user_state[user_id] = "search"
            msg = "請輸入想查詢的水果名稱（例如：香蕉、芭樂、火龍果）"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
            return

        # -------------------- #
        # 即時查詢模式
        # -------------------- #
        if user_state.get(user_id) == "search":
            user_state[user_id] = None
            crop_name_input = re.sub(r"[\s　]+", "", user_text)
            print(f"🔍 搜尋關鍵字：{crop_name_input}")

            try:
                if df.empty:
                    raise ValueError("即時行情資料尚未載入")

                if not all(col in df.columns for col in required_cols):
                    raise KeyError(f"欄位名稱不符，目前 CSV 欄位：{df.columns.tolist()}")

                results = df[df["產品_name_only"].str.contains(crop_name_input, case=False, na=False)]
                if results.empty:
                    results = df[df["產品_clean"].str.contains(crop_name_input, case=False, na=False)]

                if not results.empty:
                    latest_date = results["日期"].max()
                    recent_data = results[results["日期"] == latest_date]

                    reply_text = f"📅 最新交易日期：{latest_date}\n🍎 查詢關鍵字：{crop_name_input}\n------------------------\n"
                    for _, row in recent_data.iterrows():
                        try:
                            change = float(row['價格增減%'])
                        except ValueError:
                            change = 0
                        arrow = "📈" if change > 0 else "📉" if change < 0 else "💲"

                        reply_text += (
                            f"🥭 品項：{row['產品']}\n"
                            f"🏬 市場：{row['市場']}\n"
                            f"💰 平均價：{row['平均價(元/公斤)']} 元/公斤\n"
                            f"{arrow} 價格漲幅(%)：{row['價格增減%']} %\n"
                            "------------------------\n"
                        )
                else:
                    reply_text = f"查無「{crop_name_input}」的市場價格資料。"

            except Exception as e:
                import traceback
                print(traceback.format_exc())  # ✅ 顯示完整錯誤
                reply_text = f"⚠️ 錯誤：{e}"

            # 分段回覆
            max_len = 1900
            if len(reply_text) > max_len:
                chunks = [reply_text[i:i + max_len] for i in range(0, len(reply_text), max_len)]
                messages = [TextSendMessage(text=chunk) for chunk in chunks]
            else:
                messages = [TextSendMessage(text=reply_text)]

            line_bot_api.reply_message(event.reply_token, messages)
            return

                # -------------------- #
        # 🔹 二、月份查詢 → 查有哪些品項（支援類型分段）
        # 範例：「7月有什麼水果」或「7月有什麼農產品」
        # -------------------- #
        month_match = re.search(r"(\d{1,2})\s*月", user_text)
        if month_match:
            month_num = int(month_match.group(1))
            print(f"📅 偵測到月份查詢：{month_num}月")

            # 檢查資料
            if df_crop.empty:
                reply_text = "⚠️ 尚未載入產期資料，請稍後再試。"
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
                return

            # 嘗試判斷是否有指定類型（水果、蔬菜等）
            crop_type = None
            for t in TYPE_KEYWORDS + list(TYPE_ALIASES.keys()):
                if t in user_text:
                    crop_type = TYPE_ALIASES.get(t, t)
                    break

            # 篩選該月份資料
            month_data = df_crop[df_crop["月份"].astype(str).str.contains(f"{month_num}", na=False)]
            if crop_type:
                month_data = month_data[month_data["類型"].astype(str).str.contains(crop_type, na=False)]

            if not month_data.empty:
                if crop_type:
                    # ✅ 有指定類型，直接列出品項
                    items = list(dict.fromkeys(month_data["品項"].astype(str).tolist()))
                    if len(items) > 30:
                        items = items[:30]
                    joined_items = "、".join(items)
                    reply_text = f"{month_num}月的{crop_type}有：{joined_items}。"
                else:
                    # ✅ 沒指定類型 → 分類分段顯示
                    grouped = month_data.groupby("類型")
                    reply_text = f"🍀 {month_num}月盛產的農產品如下：\n=====================\n"

                    for gtype in TYPE_KEYWORDS:
                        if gtype in grouped.groups:
                            sub = grouped.get_group(gtype)
                            items = list(dict.fromkeys(sub["品項"].astype(str).tolist()))
                            if len(items) > 30:
                                items = items[:30]
                            joined_items = "、".join(items)
                            reply_text += f"【{gtype}】\n{joined_items}\n---------------------\n"

                    # 額外處理不在 TYPE_KEYWORDS 的其他類型
                    other_types = [t for t in grouped.groups.keys() if t not in TYPE_KEYWORDS]
                    for t in other_types:
                        sub = grouped.get_group(t)
                        items = list(dict.fromkeys(sub["品項"].astype(str).tolist()))
                        if len(items) > 30:
                            items = items[:30]
                        joined_items = "、".join(items)
                        reply_text += f"【{t}】\n{joined_items}\n---------------------\n"

            else:
                reply_text = f"❌ 查無 {month_num} 月的{crop_type or '農產品'}資料。"

            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return

        # -------------------- #
        # 偵測地區查詢（支援分項分類顯示）
        # -------------------- #
        regions, crop_type = detect_region_and_type(user_text)
        if regions:
            print(f"🗺️ 偵測到地區：{regions}, 類型：{crop_type}")

            try:
                if df_crop.empty:
                    raise ValueError("產期資料尚未載入")

                # ✅ 可多縣市查詢
                region_data = pd.concat([
                    df_crop[df_crop["縣市"].astype(str).str.contains(region, na=False)]
                    for region in regions
                ], ignore_index=True)

                if crop_type:
                    # ✅ 若有明確類型，僅顯示該類型
                    region_data = region_data[
                        region_data["類型"].astype(str).str.contains(crop_type, na=False)
                    ]

                if not region_data.empty:
                    shown_region = "、".join([r.replace("臺", "台") for r in regions])

                    # ✅ 若有指定 crop_type，維持舊格式
                    if crop_type:
                        items = list(dict.fromkeys(region_data["品項"].astype(str).tolist()))
                        joined_items = "、".join(items)
                        reply_text = f"{shown_region}盛產的{crop_type}有：{joined_items}。"

                    else:
                        # ✅ 沒有指定類型 → 依類型分組顯示
                        grouped = region_data.groupby("類型")
                        reply_text = f"🍀 {shown_region}盛產項目如下：\n"
                        reply_text += "=====================\n"

                        for gtype in TYPE_KEYWORDS:
                            if gtype in grouped.groups:
                                sub = grouped.get_group(gtype)
                                items = list(dict.fromkeys(sub["品項"].astype(str).tolist()))
                                joined_items = "、".join(items)
                                reply_text += f"【{gtype}】\n{joined_items}\n---------------------\n"

                        # 若有額外類型（不在預設四種）
                        other_types = [t for t in grouped.groups.keys() if t not in TYPE_KEYWORDS]
                        for t in other_types:
                            sub = grouped.get_group(t)
                            items = list(dict.fromkeys(sub["品項"].astype(str).tolist()))
                            joined_items = "、".join(items)
                            reply_text += f"【{t}】\n{joined_items}\n---------------------\n"

                else:
                    shown_region = "、".join([r.replace("臺", "台") for r in regions])
                    reply_text = f"❌ 查無 {shown_region} 的{crop_type or '農產品'}資料。"

            except Exception as e:
                import traceback
                print(traceback.format_exc())
                reply_text = f"⚠️ 查詢地區資料時發生錯誤：{e}"

            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return


        # -------------------- #
        # 自動偵測產期查詢（主功能）
         # -------------------- #
        crop_inputs = re.split(r"[、,，\s]+", user_text)
        crop_inputs = [normalize_crop_name(c) for c in crop_inputs if c]

        if not crop_inputs:
            msg = "請輸入水果名稱，例如：香蕉、芭樂、火龍果"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
            return

        reply_text = ""
        found_any = False

        for crop_input in crop_inputs:
            alias = expand_fruit_alias(crop_input)
            results = match_crop_in_period_data(crop_input)

            if results.empty and alias != crop_input:
                results = match_crop_in_period_data(alias)

            if not results.empty:
                found_any = True
                reply_text += f"🍀 查詢作物：{crop_input}\n=====================\n"

                # ✅ 合併相同項目的不同月份
                # 以 類型、品項、品種、縣市 為群組鍵，將月份合併
                grouped = (
                    results.groupby(["類型", "品項", "品種", "縣市"], dropna=False)
                    .agg({"月份": lambda x: "、".join(sorted(set(str(v) for v in x if str(v).strip())))})
                    .reset_index()
                )

                # 輸出整理後的結果
                for _, row in grouped.iterrows():
                    parts = []
                    if "類型" in row and str(row["類型"]).strip():
                        parts.append(f"類型：{row['類型']}")
                    if "品項" in row and str(row["品項"]).strip():
                        parts.append(f"品項：{row['品項']}")
                    if "品種" in row and str(row["品種"]).strip():
                        parts.append(f"品種：{row['品種']}")
                    if "縣市" in row and str(row["縣市"]).strip():
                        parts.append(f"縣市：{row['縣市']}")
                    if "月份" in row and str(row["月份"]).strip():
                        parts.append(f"月份：{row['月份']}")

                    reply_text += "\n".join(parts) + "\n---------------------\n"

            else:
                reply_text += f"❌ 查無 {crop_input} 的產期資料。\n---------------------\n"

        if not found_any:
            reply_text = f"⚠️錯誤的回訊方式"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 系統發生錯誤，請稍後再試。"))


    # 除錯訊息（保留）
    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"收到了：{user_text}"))
    except Exception as e:
        print("⚠️ 無法回覆除錯訊息：", e)









if __name__ == "__main__":
    # 允許外部訪問，Cloudflare Tunnel 需要
    app.run(host="0.0.0.0", port=5000)
