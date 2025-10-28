from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import requests
import csv
import pandas as pd
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
ffruitsearch_mode = False

# 全域讀取 CSV，只做一次
try:
    df = pd.read_csv("水果產品日交易行情.csv", encoding="utf-8-sig")
    # 假設資料有欄位：「作物名稱」、「市場名稱」、「平均價」、「交易日期」
    # 根據實際檔案的欄名調整
except Exception as e:
    print("讀取資料錯誤:", e)
    df = pd.DataFrame()

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global fruitsearch_mode
    user_text = event.message.text.strip()
    messages = []

    # 進入搜尋模式
    if user_text == "即時資訊":
        fruitsearch_mode = True
        msg = "請輸入想查詢的水果名稱"
        messages.append(TextSendMessage(text=msg))

    elif fruitsearch_mode:
        fruitsearch_mode = False
        crop_name = user_text
        results = df[df["產品"].str.contains(crop_name, case=False, na=False)]

        if not results.empty:
            latest_date = results["交易日期"].max()
            recent_data = results[results["日期"] == latest_date]

            reply_text = f"📅 最新交易日期：{latest_date}\n🍎 查詢品項：{crop_name}\n\n"
            for _, row in recent_data.iterrows():
                reply_text += (
                    f"🏬 市場：{row['市場']}\n"
                    f"💰 平均價：{row['平均價(元/公斤)']} 元/公斤\n"
                    "------------------------\n"
                )
        else:
            reply_text = f"查無「{crop_name}」的市場價格資料。"

        messages.append(TextSendMessage(text=reply_text))

    else:
        messages.append(TextSendMessage(text=f"你說了：{user_text}"))

    if messages:
        line_bot_api.reply_message(event.reply_token, messages)










if __name__ == "__main__":
    # 允許外部訪問，Cloudflare Tunnel 需要
    app.run(host="0.0.0.0", port=5000)
