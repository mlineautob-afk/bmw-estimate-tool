import streamlit as st
import pandas as pd
import requests
import base64
import json
import io
import time
from PIL import Image

# --------------------------------------------------
# 初期設定
# --------------------------------------------------
API_KEY = st.secrets["GEMINI_API_KEY"]
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={API_KEY}"

st.set_page_config(page_title="見積再計算TOOL FinalEdition", layout="wide")

# --------------------------------------------------
# UI最適化CSS
# --------------------------------------------------
st.markdown("""
    <style>
    div[data-testid="stButton"] button {
        width: 100% !important;
        height: 3.5rem !important;
        font-size: 1.2rem !important;
        font-weight: bold !important;
        border-radius: 10px !important;
    }
    .sticky-footer {
        position: fixed;
        left: 0;
        bottom: 0; 
        width: 100%;
        background-color: #111827; 
        color: #f8fafc;
        text-align: left; 
        padding: 15px 20px; 
        font-size: 1.4rem;
        font-weight: bold;
        box-shadow: 0 -8px 20px rgba(0,0,0,0.5);
        z-index: 999999;
    }
    .main-content {
        margin-bottom: 120px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-content">', unsafe_allow_html=True)

st.title("見積再計算TOOL FinalEdition")
st.write("PDFまたはカメラで撮影した写真を複数枚アップロードすると、シミュレーション表を作成します。")

uploaded_files = st.file_uploader("BMW見積書 (PDF / 写真) をアップロード", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files:
    if 'raw_data' not in st.session_state:
        st.session_state.raw_data = None

    if st.button("🔘　見積書を解析する", use_container_width=True):
        with st.spinner('AIが精密解析中...（混雑回避モード稼働中）'):
            
            # --- 画像の最適化と1枚への結合処理 ---
            images = []
            has_pdf = False
            pdf_bytes = None
            
            for f in uploaded_files:
                if f.type in ["image/jpeg", "image/jpg", "image/png"]:
                    img = Image.open(f)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    # 個々の画像を最大幅1500pxにリサイズしてメモリ節約
                    if img.width > 1500:
                        ratio = 1500 / img.width
                        img = img.resize((1500, int(img.height * ratio)), Image.Resampling.LANCZOS)
                    images.append(img)
                else:
                    has_pdf = True
                    pdf_bytes = f.getvalue()

            # 複数枚の画像がある場合、縦に1枚に結合してサーバーの負荷を劇的に減らす
            if images and not has_pdf:
                total_height = sum(img.height for img in images)
                max_width = max(img.width for img in images)
                
                combined_img = Image.new('RGB', (max_width, total_height), (255, 255, 255))
                current_y = 0
                for img in images:
                    combined_img.paste(img, (0, current_y))
                    current_y += img.height
                
                buf = io.BytesIO()
                combined_img.save(buf, format="JPEG", quality=85) # 高画質と軽量化のベストバランス
                final_bytes = buf.getvalue()
                mime_type = "image/jpeg"
            elif has_pdf:
                final_bytes = pdf_bytes
                mime_type = "application/pdf"
            else:
                final_bytes = uploaded_files[0].getvalue()
                mime_type = uploaded_files[0].type

            file_base64 = base64.b64encode(final_bytes).decode('utf-8')

            # --- 負荷を極限まで減らしたダイエット版プロンプト ---
            payload = {
                "contents": [{
                    "parts": [
                        {
                            "text": "Analyze the BMW estimate sheet. Extract all items into a strict JSON array. Rule: Identify main categories starting with uppercase letters and include their full titles (e.g., 'A: 法定2年点検'). Format: [{'大項目': 'A: 法定2年点検', '項目': 'Item Name', '単価': 1000, '数量': 1, '金額': 1000}]. Return ONLY raw JSON."
                        },
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": file_base64
                            }
                        }
                    ]
                }]
            }
            headers = {'Content-Type': 'application/json'}

            # --- 自動リトライ（粘り強いアタック）機能の組み込み ---
            max_retries = 3
            success = False
            
            for attempt in range(max_retries):
                try:
                    response = requests.post(URL, headers=headers, json=payload)
                    response.raise_for_status()
                    
                    ai_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                    ai_text = ai_text.replace("```json", "").replace("```", "").strip()
                    st.session_state.raw_data = json.loads(ai_text)
                    success = True
                    break # 成功したらループを抜ける
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(3) # 503エラー時は3秒待って再試行
                        continue
                    else:
                        safe_error_msg = str(e).replace(API_KEY, "********")
                        st.error(f"解析エラー: {safe_error_msg}")
                        st.warning("Googleのサーバーが極度に混雑しています。少し時間を空けてから再度お試しください。")

    if st.session_state.raw_data:
        df_full = pd.DataFrame(st.session_state.raw_data)
        
        for col in ['単価', '数量', '金額']:
            df_full[col] = pd.to_numeric(df_full[col], errors='coerce').fillna(0)

        categories = df_full["大項目"].unique()
        total_amount = 0

        st.success("解析完了。各カテゴリのトグルで一括操作が可能です。")

        for cat in categories:
            cat_items = df_full[df_full["大項目"] == cat].copy()
            
            cat_on = st.checkbox(f"📁 {cat} を計算に含める", value=True, key=f"master_{cat}")
            
            if cat_on:
                if '実施' not in cat_items.columns:
                    cat_items.insert(0, "実施", True)
                
                edited_df = st.data_editor(
                    cat_items.drop(columns=["大項目"]),
                    hide_index=True,
                    use_container_width=True,
                    key=f"editor_{cat}"
                )
                
                cat_sum = edited_df[edited_df["実施"]]["金額"].sum()
                total_amount += cat_sum
                st.write(f"小計: ¥{cat_sum:,.0f}")
            else:
                st.info(f"{cat} は除外中")
            
            st.markdown("---")

        if st.button("🗑️ データをリセットして新しい見積もりへ", use_container_width=True):
            st.session_state.raw_data = None
            st.rerun()

        st.markdown(f"""
            <div class="sticky-footer">
                合計: ¥ {total_amount:,.0f}
            </div>
        """, unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
