import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import plotly.express as px

st.set_page_config(page_title="تقرير التوصيل للافرع", layout="wide")
st.title("📦 أداة تحليل التوصيل لكل الفروع")

if "manifest_data" not in st.session_state:
    st.session_state["manifest_data"] = None

# ✅ التوكن من secrets.toml
TOKEN = st.secrets["token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# ✅ تحميل بيانات المنفيستات لآخر 3 أيام مع pagination
if st.session_state["manifest_data"] is None:
    all_data = []
    today = datetime.utcnow().date()
    date_list = [today - timedelta(days=i) for i in range(3)]

    for date in date_list:
        page = 1
        while True:
            body = {
                "manifestDate": str(date),
                "pageNumber": page,
                "pageSize": 100
            }
            response = requests.post(
                "https://jenni.alzaeemexp.com/api/liaison/manifest/getAllLiaisonManifest",
                headers=HEADERS,
                json=body
            )
            if response.status_code == 200:
                result = response.json()
                data_page = result.get("data", [])
                if not data_page:
                    break
                all_data.extend(data_page)

                total_pages = result.get("totalPages", 1)
                if page >= total_pages:
                    break
                page += 1
            else:
                st.error(f"❌ فشل في جلب البيانات بتاريخ {date}. الرمز: {response.status_code}")
                break

    st.session_state["manifest_data"] = all_data
    st.success(f"✅ تم تحميل {len(all_data)} منفيست بنجاح لآخر 3 أيام")

# ✅ تحليل البيانات
if st.session_state["manifest_data"]:
    data = st.session_state["manifest_data"]

    def parse_manifest_data(data):
        rows = []
        for record in data:
            branch = record.get("lamToBranchName", "غير معروف").strip()
            date = record.get("manifestDate")
            try:
                manifest_date = (datetime.fromisoformat(date.replace("Z", "+00:00")) + timedelta(hours=3)).date()
            except:
                continue

            for stage in record.get("stageStepAggregations", []):
                rows.append({
                    "فرع": branch,
                    "تاريخ المنفيست": manifest_date,
                    "المرحلة": stage.get("stepArabicName", "غير معروفة").strip(),
                    "عدد الشحنات": stage.get("currentCasesCount", 0)
                })
        return pd.DataFrame(rows)

    df = parse_manifest_data(data)

    # ✅ الفلاتر
    st.sidebar.header("📅 الفلاتر")
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    filter_option = st.sidebar.radio("اختر نطاق التاريخ", ("اليوم", "البارحة", "تاريخ مخصص"))

    if filter_option == "اليوم":
        filtered_df = df[df["تاريخ المنفيست"] == today]
    elif filter_option == "البارحة":
        filtered_df = df[df["تاريخ المنفيست"] == yesterday]
    else:
        custom_date = st.sidebar.date_input("اختر تاريخ", value=today)
        filtered_df = df[df["تاريخ المنفيست"] == custom_date]

    total_shipments = filtered_df["عدد الشحنات"].sum()
    st.metric(label="📦 مجموع كل الشحنات في التاريخ المحدد", value=f"{total_shipments:,}")

    if filtered_df.empty:
        st.warning("لا توجد بيانات في هذا التاريخ.")
    else:
        st.subheader("📊 إجمالي عدد الشحنات لكل فرع")
        branch_counts = filtered_df.groupby("فرع")["عدد الشحنات"].sum().reset_index().sort_values("عدد الشحنات", ascending=False)
        fig1 = px.bar(branch_counts, x="فرع", y="عدد الشحنات", text="عدد الشحنات",
                     title="عدد الشحنات حسب الفرع", labels={"فرع": "اسم الفرع", "عدد الشحنات": "عدد الشحنات"})
        st.plotly_chart(fig1, use_container_width=True)

        st.subheader("📌 تفاصيل المراحل حسب الفروع")
        selected_branch = st.selectbox("اختر فرعًا لعرض التفاصيل", branch_counts["فرع"].unique())
        branch_steps = filtered_df[filtered_df["فرع"] == selected_branch]
        step_summary = branch_steps.groupby("المرحلة")["عدد الشحنات"].sum().reset_index().sort_values("عدد الشحنات", ascending=False)

        step_colors = {
            "شحنات سلمت بنجاح": "darkgreen",
            "راجع عند المندوب": "lightcoral",
            "رواجع الفروع في المخزن": "darkred",
            "مؤجل": "purple",
            "راجع مؤكد": "firebrick",
            "قيد التوصيل": "skyblue",
            "راجع كلي": "maroon",
            "تسليم جزئيا أو أستبدال": "lightgreen",
            "إعادة توصيل": "lightskyblue",
            "سلمت مع تغيير المبلغ": "lightgreen",
            "طباعة المنفيست لمندوبين التوصيل": "lightskyblue",
            "داخل المخزن": "gold",
            "شحنات جديدة بين فرعين": "gold"
        }

        color_map = [step_colors.get(name.split('-')[0].strip(), "gray") for name in step_summary["المرحلة"]]

        col1, col2 = st.columns(2)
        with col1:
            st.dataframe(step_summary, use_container_width=True)
        with col2:
            fig2 = px.pie(step_summary, names="المرحلة", values="عدد الشحنات",
                          title=f"نسبة الشحنات حسب المراحل - {selected_branch}")
            fig2.update_traces(marker=dict(colors=color_map))
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("📈 مقارنة نسب الشحنات الواصلة بين الفروع")

        filtered_df["اسم المرحلة"] = filtered_df["المرحلة"].apply(lambda x: x.split('-')[0].strip())

        success_stages = [
            "تسليم جزئيا أو أستبدال",
            "سلمت مع تغيير المبلغ",
            "شحنات سلمت بنجاح"
        ]

        total_by_branch = filtered_df.groupby("فرع")["عدد الشحنات"].sum().reset_index(name="مجموع الشحنات")
        success_by_branch = filtered_df[filtered_df["اسم المرحلة"].isin(success_stages)]
        success_summary = success_by_branch.groupby("فرع")["عدد الشحنات"].sum().reset_index(name="الشحنات الواصلة")

        merged = pd.merge(total_by_branch, success_summary, on="فرع", how="left").fillna(0)
        merged["نسبة النجاح"] = (merged["الشحنات الواصلة"] / merged["مجموع الشحنات"] * 100).round(2)
        merged["إجمالي الشحنات"] = merged["مجموع الشحنات"].astype(int)
        merged["الشحنات الواصلة"] = merged["الشحنات الواصلة"].astype(int)

        st.dataframe(merged[["فرع", "إجمالي الشحنات", "الشحنات الواصلة", "نسبة النجاح"]], use_container_width=True)

        fig_success = px.bar(
            merged,
            x="فرع",
            y="نسبة النجاح",
            text_auto=True,
            color="نسبة النجاح",
            color_continuous_scale="greens",
            labels={"نسبة النجاح": "% نسبة الشحنات الواصلة"},
            title="نسبة الشحنات التي تم توصيلها بنجاح لكل فرع"
        )
        st.plotly_chart(fig_success, use_container_width=True)
