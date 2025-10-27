from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import requests
import csv
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
fruitsearch_mode = False  
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global fruitsearch_mode
    user_text = event.message.text.strip()

    # 進入搜尋模式
    if user_text == "水果品項":
        fruitsearch_mode = True
        try:
            TextSendMessage(text="正在讀取開放資料，請稍後")
            with open("東部地區時令水果產期資訊.csv", "r", encoding="utf-8") as f:
                data = csv.DictReader(f)
            TextSendMessage(text="開放資料讀取完畢")
        except Exception:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⚠️ 無法讀取水果資料檔，請稍後再試。")
            )
            return

        # 取得所有品項
        all_fruits = [item["品項"] for item in data]
        fruits_text = "、".join(all_fruits)

        msg = f"請輸入想查詢的水果名稱，目前可查詢品項有：\n{fruits_text}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        return

    # 若目前在搜尋模式
    if fruitsearch_mode:
        fruitsearch_mode = False  # 查完一次後關閉搜尋模式
        crop_name = user_text
        try:
            TextSendMessage(text="正在讀取開放資料，請稍後")
            with open("東部地區時令水果產期資訊.csv", "r", encoding="utf-8") as f:
                data = csv.DictReader(f)
            TextSendMessage(text="開放資料讀取完畢")
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⚠️ 開放資料連線異常，請稍後再試。")
            )
            return

        # 搜尋水果名稱
        result = None
        for item in data:
            if crop_name in item["品項"]:
                result = item
                break

        if result:
            msg = (
                f"🍎品項：{result['品項']}\n"
                f"📅主要產期：{result['主要產期']}\n"
                f"📍主要產地：{result['主要產地']}"
            )
        else:
            msg = f"查無「{crop_name}」的相關資料，請確認名稱是否正確。"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        return

    # 一般回覆（非搜尋模式）
    reply = f"你說了：{user_text}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))










if __name__ == "__main__":
    # 允許外部訪問，Cloudflare Tunnel 需要
    app.run(host="0.0.0.0", port=5000)
