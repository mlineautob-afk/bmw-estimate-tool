import streamlit as st
import pandas as pd
import requests
import base64
import json

# --------------------------------------------------
# 初期設定
# --------------------------------------------------
API_KEY = st.secrets["GEMINI_API_KEY"]
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={API_KEY}"

st.set_page_config(page_title="見積再計算ツール", layout="wide")
st.title("見積再計算ツール")
st.write("PDFまたはカメラで撮影した写真を複数枚アップロードすると、シミュレーション表を作成します。")

# ★ 変更点1: accept_multiple_files=True を追加して複数枚の撮影・選択を許可
uploaded_files = st.file_uploader("BMW見積書 (PDF / 写真) をアップロード", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files: # ファイルが1つ以上ある場合
    if 'raw_data' not in st.session_state:
        st.session_state.raw_data = None
    if 'edited_dfs' not in st.session_state:
        st.session_state.edited_dfs = {}

    # --- 解析実行 ---
    if st.button("見積書を解析する") or st.session_state.raw_data is not None:
        if st.session_state.raw_data is None:
            with st.spinner('AIが精密解析中...（約15秒かかります）'):
                try:
                    # ★ 変更点2: AIに渡す「指示書」と「画像データ」のリストを組み立てる
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

                    # アップロードされた全ファイル（写真1枚目、2枚目...）を順番に処理して追加
                    for f in uploaded_files:
                        file_mime_type = f.type 
                        file_base64 = base64.b64encode(f.getvalue()).decode('utf-8')
                        parts_list.append({
                            "inline_data": {
                                "mime_type": file_mime_type,
                                "data": file_base64
                            }
                        })
                    
                    payload = {
                        "contents": [{
                            "parts": parts_list
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
            
            for col in ['単価', '数量', '金額']:
                df_full[col] = pd.to_numeric(df_full[col], errors='coerce').fillna(0)

            categories = df_full["大項目"].unique()
            total_amount = 0

            st.success("解析完了。各カテゴリのマスターチェックボックスで一括操作が可能です。")

            for cat in categories:
                cat_items = df_full[df_full["大項目"] == cat].copy()
                
                cat_on = st.checkbox(f"📁 {cat} をすべて含める", value=True, key=f"master_{cat}")
                
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
                    st.info(f"{cat} は計算から除外されています")
                
                st.markdown("---")

            st.metric(label="シミュレーション合計金額", value=f"¥ {total_amount:,.0f}")

            if st.button("データをリセット"):
                st.session_state.raw_data = None
                st.rerun()
