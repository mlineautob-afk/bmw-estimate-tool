import streamlit as st
import pandas as pd
import requests
import base64
import json

# --------------------------------------------------
# 初期設定
# --------------------------------------------------
API_KEY = st.secrets["GEMINI_API_KEY"]
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

st.set_page_config(page_title="見積再計算ツール", layout="wide")
st.title("見積再計算ツール")
st.write("PDFをアップロードすると、カテゴリごとの一括選択と個別調整が可能なシミュレーション表を作成します。")

uploaded_file = st.file_uploader("BMW見積書 (PDF) をアップロード", type="pdf")

if uploaded_file is not None:
    # 状態の初期化
    if 'raw_data' not in st.session_state:
        st.session_state.raw_data = None
    if 'edited_dfs' not in st.session_state:
        st.session_state.edited_dfs = {}

    # --- 解析実行 ---
    if st.button("見積書を解析する") or st.session_state.raw_data is not None:
        if st.session_state.raw_data is None:
            with st.spinner('AIが精密解析中...（約15秒かかります）'):
                try:
                    pdf_base64 = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
                    payload = {
                        "contents": [{
                            "parts": [
                                {
                                    "text": """
                                    提供された車検見積書（PDF）を視覚的に解析し、作業明細のみを抽出して以下のJSON配列形式で出力してください。
                                    
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
                                },
                                {
                                    "inline_data": {
                                        "mime_type": "application/pdf",
                                        "data": pdf_base64
                                    }
                                }
                            ]
                        }]
                    }
                    headers = {'Content-Type': 'application/json'}
                    response = requests.post(URL, headers=headers, json=payload)
                    response.raise_for_status()
                    
                    ai_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                    ai_text = ai_text.replace("```json", "").replace("```", "").strip()
                    st.session_state.raw_data = json.loads(ai_text)
                except Exception as e:
                    st.error(f"解析エラー: {e}")

        # --- 解析データがある場合のUI構築 ---
        if st.session_state.raw_data:
            df_full = pd.DataFrame(st.session_state.raw_data)
            
            # 数値型に強制変換（エラー回避）
            for col in ['単価', '数量', '金額']:
                df_full[col] = pd.to_numeric(df_full[col], errors='coerce').fillna(0)

            categories = df_full["大項目"].unique()
            total_amount = 0

            st.success("解析完了。各カテゴリのマスターチェックボックスで一括操作が可能です。")

            # カテゴリごとにループ
            for cat in categories:
                cat_items = df_full[df_full["大項目"] == cat].copy()
                
                # --- マスターチェックボックス ---
                cat_on = st.checkbox(f"📁 {cat} をすべて含める", value=True, key=f"master_{cat}")
                
                if cat_on:
                    # 個別選択用の列を追加（デフォルトTrue）
                    if '実施' not in cat_items.columns:
                        cat_items.insert(0, "実施", True)
                    
                    # ユーザーが編集できる表（大項目の列は不要なので隠す）
                    edited_df = st.data_editor(
                        cat_items.drop(columns=["大項目"]),
                        hide_index=True,
                        use_container_width=True,
                        key=f"editor_{cat}"
                    )
                    
                    # チェックが入っている行の金額だけを合計
                    cat_sum = edited_df[edited_df["実施"]]["金額"].sum()
                    total_amount += cat_sum
                    st.write(f"小計: ¥{cat_sum:,.0f}")
                else:
                    st.info(f"{cat} は計算から除外されています")
                
                st.markdown("---")

            # --- 最終合計 ---
            st.metric(label="シミュレーション合計金額", value=f"¥ {total_amount:,.0f}")

            if st.button("データをリセット"):
                st.session_state.raw_data = None
                st.rerun()