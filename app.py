import streamlit as st
import pandas as pd
import requests
import base64
import json
import io
from PIL import Image

# --------------------------------------------------
# 初期設定
# --------------------------------------------------
API_KEY = st.secrets["GEMINI_API_KEY"]
# ★ 安定性最優先のため、エンジンを 2.5 Flash に換装
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

st.set_page_config(page_title="見積再計算ツール Pro", layout="wide")

# --------------------------------------------------
# ★ スマホUI最適化CSS
# --------------------------------------------------
st.markdown("""
    <style>
    .sticky-footer {
        position: fixed;
        left: 0;
        bottom: 45px; 
        width: 100%;
        background-color: #111827; 
        color: #f8fafc;
        text-align: center;
        padding: 15px;
        font-size: 1.4rem;
        font-weight: bold;
        box-shadow: 0 -8px 20px rgba(0,0,0,0.5);
        z-index: 999999;
        border-top-left-radius: 15px;
        border-top-right-radius: 15px;
    }
    .main-content {
        margin-bottom: 150px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-content">', unsafe_allow_html=True)

st.title("見積再計算ツール Pro")
st.write("PDFまたはカメラで撮影した写真を複数枚アップロードすると、シミュレーション表を作成します。")

uploaded_files = st.file_uploader("BMW見積書 (PDF / 写真) をアップロード", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files:
    if 'raw_data' not in st.session_state:
        st.session_state.raw_data = None

    if st.button("🔥 見積書を解析する", use_container_width=True):
        with st.spinner('AIが精密解析中...（通信を安定化させています）'):
            try:
                parts_list = [
                    {
                        "text": """
                        提供された車検見積書（PDFまたは複数枚の画像）を視覚的に解析し、作業明細のみを抽出して以下のJSON配列形式で出力してください。
                        ※複数枚に渡る場合も、すべて統合して1つのJSON配列にまとめてください。
                        
                        【見積書の構造と抽出の絶対ルール】
                        1. 左端付近にある「A」「AA」「AB」「A1」などのアルファベットから始まる行（例：A: 法定2年点検、AA: ワイパーブレード交換など）が「大項目（親タスク）」です。
                        2. その大項目の下に記載されている個別の部品名や作業名（例：ブレーキパッドペースト、パーツクリーナー等）が「項目（小項目）」です。
                        3. すべての小項目に対し、それが属している「大項目」の名前（アルファベット記号を含む主作業名）を正確に紐付けて分類してください。
                        4. 項目名と、その行の右側にある「単価」「数量」「金額」をレイアウトから目で見て正確に紐付けること。絶対に「0」で埋めないこと。
                        
                        出力フォーマット例:
                        [
                          {"大項目": "A: 法定2年点検", "項目": "検査測定機器使用料", "単価": 1430, "数量": 8, "金額": 11440},
                          {"大項目": "AA: ワイパーブレード交換", "項目": "ワイパーブレードセット", "単価": 8000, "数量": 1, "金額": 8000}
                        ]
                        """
                    }
                ]

                for f in uploaded_files:
                    mime_type = f.type
                    if mime_type in ["image/jpeg", "image/jpg", "image/png"]:
                        img = Image.open(f)
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # ★ 圧縮をさらに強化（1600px -> 1024px, quality 85 -> 80）
                        max_width = 1024
                        if img.width > max_width:
                            ratio = max_width / img.width
                            new_height = int(img.height * ratio)
                            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                        
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=80)
                        file_bytes = buf.getvalue()
                        mime_type = "image/jpeg"
                    else:
                        file_bytes = f.getvalue()

                    file_base64 = base64.b64encode(file_bytes).decode('utf-8')
                    parts_list.append({
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": file_base64
                        }
                    })
                
                payload = {"contents": [{"parts": parts_list}]}
                headers = {'Content-Type': 'application/json'}
                response = requests.post(URL, headers=headers, json=payload)
                response.raise_for_status()
                
                ai_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                ai_text = ai_text.replace("```json", "").replace("```", "").strip()
                st.session_state.raw_data = json.loads(ai_text)
                
            except Exception as e:
                safe_error_msg = str(e).replace(API_KEY, "********")
                st.error(f"解析エラー: {safe_error_msg}")
                st.warning("Googleのサーバーが混雑しているか、通信タイムアウトが発生しました。時間を置いてからお試しください。")

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
                cat_sum = 0
                
                # ★ スマホ用の「カード型レイアウト」で縦に並べる
                for idx, row in cat_items.iterrows():
                    col1, col2 = st.columns([1, 9])
                    with col1:
                        is_checked = st.checkbox(" ", value=True, key=f"chk_{cat}_{idx}", label_visibility="collapsed")
                    with col2:
                        st.markdown(f"**{row['項目']}**")
                        st.caption(f"¥{row['単価']:,.0f} × {row['数量']} ＝ **¥{row['金額']:,.0f}**")
                        
                    if is_checked:
                        cat_sum += row['金額']
                
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
                シミュレーション合計: ¥ {total_amount:,.0f}
            </div>
        """, unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
