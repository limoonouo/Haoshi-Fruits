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
    df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=True)

    # 🔹 清除欄位內所有空白（全形與半形）
    df["產品"] = (
        df["產品"]
        .astype(str)
        .str.replace(r"\s+", "", regex=True)   # 半形空格
        .str.replace(r"　+", "", regex=True)   # 全形空格
    )

    print("✅ 成功讀入資料，欄位如下：", df.columns.tolist())
except Exception as e:
    print("❌ 讀取資料錯誤:", e)
    df = pd.DataFrame()

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_id = event.source.user_id
        user_text = event.message.text.strip()
        messages = []

        print(f"📩 收到使用者輸入：{user_text}")  # ←偵錯用

        # 進入搜尋模式
        if user_text == "即時資訊":
            user_state[user_id] = "search"
            msg = "請輸入想查詢的水果名稱（例如：香蕉、芭樂、火龍果）"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
            return

        # 搜尋模式
        if user_state.get(user_id) == "search":
            user_state[user_id] = None
            crop_name = re.sub(r"[\s　]+", "", user_text)
            print(f"🔍 搜尋關鍵字：{crop_name}")  # ←偵錯用

            try:
                required_cols = ["日期", "市場", "產品", "平均價(元/公斤)", "交易量(公斤)"]
                if not all(col in df.columns for col in required_cols):
                    raise KeyError(f"欄位名稱不符，目前 CSV 欄位：{df.columns.tolist()}")

                df["產品"] = (
                    df["產品"]
                    .astype(str)
                    .str.replace(r"\s+", "", regex=True)
                    .str.replace(r"　+", "", regex=True)
                )

                all_crops = df["產品"].dropna().unique().tolist()
                close_matches = get_close_matches(crop_name, all_crops, n=5, cutoff=0.3)

                if not close_matches:
                    results = df[df["產品"].astype(str).str.contains(crop_name, case=False, na=False)]
                else:
                    results = df[df["產品"].isin(close_matches)]

                if not results.empty:
                    latest_date = results["日期"].max()
                    recent_data = results[results["日期"] == latest_date]

                    reply_text = f"📅 最新交易日期：{latest_date}\n🍎 查詢關鍵字：{crop_name}\n\n"
                    for _, row in recent_data.iterrows():
                        reply_text += (
                            f"🥭 品項：{row['產品']}\n"
                            f"🏬 市場：{row['市場']}\n"
                            f"💰 平均價：{row['平均價(元/公斤)']} 元/公斤\n"
                            f"📦 交易量：{row['交易量(公斤)']} 公斤\n"
                            "------------------------\n"
                        )
                else:
                    reply_text = f"查無「{crop_name}」的市場價格資料。"

            except Exception as e:
                reply_text = f"⚠️ 錯誤：{e}"

            # 分段回覆
            max_len = 1900
            if len(reply_text) > max_len:
                chunks = [reply_text[i:i+max_len] for i in range(0, len(reply_text), max_len)]
                messages = [TextSendMessage(text=chunk) for chunk in chunks]
            else:
                messages = [TextSendMessage(text=reply_text)]

            line_bot_api.reply_message(event.reply_token, messages)
            return

        # 非搜尋模式
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"你說了：{user_text}"))

    except Exception as e:
        print("❌ 錯誤：", e)
        traceback.print_exc(file=sys.stdout)









if __name__ == "__main__":
    # 允許外部訪問，Cloudflare Tunnel 需要
    app.run(host="0.0.0.0", port=5000)
