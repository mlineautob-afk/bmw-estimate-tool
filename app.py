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

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --------------------------------------------------
# UI最適化CSS（階層型・明細レイアウト）
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
        left: 0; bottom: 0; width: 100%;
        background-color: #111827; color: #f8fafc;
        text-align: left; padding: 15px 20px; 
        font-size: 1.4rem; font-weight: bold;
        box-shadow: 0 -8px 20px rgba(0,0,0,0.5);
        z-index: 999999;
    }
    .main-content { margin-bottom: 150px; }

    /* 階層型明細書デザイン */
    .invoice-container {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 10px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .invoice-header {
        border-bottom: 2px solid #1e293b;
        padding-bottom: 8px; margin-bottom: 20px;
        color: #1e293b; font-size: 1.3rem; font-weight: bold; text-align: center;
    }
    .category-block { margin-bottom: 25px; }
    .category-title {
        background-color: #f8fafc;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 1.1rem;
        font-weight: bold;
        color: #0066b3;
        border-left: 5px solid #0066b3;
        margin-bottom: 10px;
    }
    .item-row {
        display: flex;
        justify-content: space-between;
        padding: 6px 12px;
        border-bottom: 1px solid #f1f5f9;
        font-size: 0.95rem;
        color: #475569;
    }
    .subtotal-row {
        display: flex;
        justify-content: flex-end;
        padding: 10px 12px;
        font-weight: bold;
        color: #1e293b;
        font-size: 1rem;
    }
    .final-total-area {
        margin-top: 30px;
        padding-top: 15px;
        border-top: 2px double #cbd5e1;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .final-total-label { font-size: 1rem; color: #64748b; }
    .final-total-amount { font-size: 1.6rem; font-weight: bold; color: #0066b3; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-content">', unsafe_allow_html=True)

st.title("見積再計算TOOL FinalEdition")

uploaded_files = st.file_uploader(
    "BMW見積書 (PDF / 写真) をアップロード", 
    type=["pdf", "jpg", "jpeg", "png"], 
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.uploader_key}"
)

if uploaded_files:
    if 'raw_data' not in st.session_state:
        st.session_state.raw_data = None

    if st.button("🔘 見積書を解析する", use_container_width=True):
        with st.spinner('AIが精密解析中...'):
            images = []
            has_pdf = False
            pdf_bytes = None
            for f in uploaded_files:
                if f.type in ["image/jpeg", "image/jpg", "image/png"]:
                    img = Image.open(f)
                    if img.mode != 'RGB': img = img.convert('RGB')
                    if img.width > 1500:
                        ratio = 1500 / img.width
                        img = img.resize((1500, int(img.height * ratio)), Image.Resampling.LANCZOS)
                    images.append(img)
                else:
                    has_pdf = True; pdf_bytes = f.getvalue()

            if images and not has_pdf:
                total_height = sum(img.height for img in images); max_width = max(img.width for img in images)
                combined_img = Image.new('RGB', (max_width, total_height), (255, 255, 255))
                current_y = 0
                for img in images: combined_img.paste(img, (0, current_y)); current_y += img.height
                buf = io.BytesIO(); combined_img.save(buf, format="JPEG", quality=85); final_bytes = buf.getvalue(); mime_type = "image/jpeg"
            elif has_pdf:
                final_bytes = pdf_bytes; mime_type = "application/pdf"
            else:
                final_bytes = uploaded_files[0].getvalue(); mime_type = uploaded_files[0].type

            file_base64 = base64.b64encode(final_bytes).decode('utf-8')
            payload = {
                "contents": [{
                    "parts": [
                        { "text": "Analyze the BMW estimate sheet. Extract all items into a strict JSON array. Rule: Identify main categories starting with uppercase letters and include their full titles (e.g., 'A: 法定2年点検'). Format: [{'大項目': 'A: 法定2年点検', '項目': 'Item Name', '単価': 1000, '数量': 1, '金額': 1000}]. Return ONLY raw JSON." },
                        { "inline_data": { "mime_type": mime_type, "data": file_base64 } }
                    ]
                }]
            }
            headers = {'Content-Type': 'application/json'}
            try:
                response = requests.post(URL, headers=headers, json=payload)
                response.raise_for_status()
                ai_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                st.session_state.raw_data = json.loads(ai_text.replace("```json", "").replace("```", "").strip())
            except:
                st.error("解析エラーが発生しました。時間を置いてお試しください。")

    if st.session_state.raw_data:
        df_full = pd.DataFrame(st.session_state.raw_data)
        for col in ['単価', '数量', '金額']:
            df_full[col] = pd.to_numeric(df_full[col], errors='coerce').fillna(0)

        categories = df_full["大項目"].unique()
        total_amount = 0
        final_approved_items = []

        for cat in categories:
            cat_items = df_full[df_full["大項目"] == cat].copy()
            cat_on = st.checkbox(f"📁 {cat}", value=True, key=f"master_{cat}")
            if cat_on:
                if '実施' not in cat_items.columns: cat_items.insert(0, "実施", True)
                edited_df = st.data_editor(cat_items.drop(columns=["大項目"]), hide_index=True, use_container_width=True, key=f"editor_{cat}")
                approved_rows = edited_df[edited_df["実施"]].copy()
                approved_rows.insert(0, "大項目", cat)
                final_approved_items.append(approved_rows)
                cat_sum = approved_rows["金額"].sum(); total_amount += cat_sum
                st.write(f"小計: ¥{cat_sum:,.0f}")
            st.markdown("---")

        # --------------------------------------------------
        # プロフェッショナル最終明細書（階層レイアウトUI）
        # --------------------------------------------------
        if final_approved_items:
            final_df = pd.concat(final_approved_items, ignore_index=True)
            st.markdown("### 📄 最終シミュレーション明細")
            
            # HTML構築
            invoice_html = '<div class="invoice-container"><div class="invoice-header">Final Simulation</div>'
            
            for cat in final_df["大項目"].unique():
                cat_df = final_df[final_df["大項目"] == cat]
                invoice_html += f'<div class="category-block"><div class="category-title">{cat}</div>'
                
                for _, row in cat_df.iterrows():
                    invoice_html += f'''
                    <div class="item-row">
                        <span>{row['項目']}</span>
                        <span>¥{row['金額']:,.0f}</span>
                    </div>
                    '''
                
                cat_total = cat_df["金額"].sum()
                invoice_html += f'<div class="subtotal-row">小計: ¥{cat_total:,.0f}</div></div>'
            
            invoice_html += f'''
                <div class="final-total-area">
                    <span class="final-total-label">総合計 (税込想定)</span>
                    <span class="final-total-amount">¥{total_amount:,.0f}</span>
                </div>
            </div>
            '''
            st.markdown(invoice_html, unsafe_allow_html=True)
            
            csv_data = final_df.drop(columns=["実施"]).to_csv(index=False).encode('utf-8-sig')
            st.download_button(label="📥 この明細をExcel(CSV)で保存", data=csv_data, file_name=f"BMW_Sim_{time.strftime('%Y%m%d')}.csv", mime="text/csv", use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ 全てリセット", use_container_width=True):
            st.session_state.raw_data = None; st.session_state.uploader_key += 1; st.rerun()
        st.markdown(f'<div class="sticky-footer">合計: ¥ {total_amount:,.0f}</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
