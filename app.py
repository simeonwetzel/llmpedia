import json
import time
import streamlit as st

from streamlit_plotly_events import plotly_events
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np

import utils.app_utils as au
import utils.plots as pt
import utils.db as db

## Page config.
st.set_page_config(
    layout="wide",
    page_title="📚 LLMpedia",
    page_icon="📚",
    initial_sidebar_state="expanded",
)

# Initialization of state variables
if "papers" not in st.session_state:
    st.session_state.papers = None

if "page_number" not in st.session_state:
    st.session_state.page_number = 0

if "num_pages" not in st.session_state:
    st.session_state.num_pages = 0

if "arxiv_code" not in st.session_state:
    st.session_state.arxiv_code = ""

if "openai_api_key" not in st.session_state:
    st.session_state.openai_api_key = ""

if "all_years" not in st.session_state:
    st.session_state.all_years = False


collection_map = {
    "GTE-Large": "arxiv_vectors",
    "🆕 Cohere V3": "arxiv_vectors_cv3",
}

st.markdown(
    """
    <style>
        @import 'https://fonts.googleapis.com/css2?family=Orbitron&display=swap';
        .pixel-font {
            font-family: 'Orbitron', sans-serif;
            font-size: 32px;
            margin-bottom: 1rem;
        }
    </style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
        .centered {
            display: flex;
            justify-content: center;
            margin-bottom: 10px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def combine_input_data():
    arxiv_df = db.load_arxiv()
    summaries_df = db.load_summaries()
    topics_df = db.load_topics()
    citations_df = db.load_citations()
    recursive_summaries_df = db.load_recursive_summaries()
    markdown_summaries = db.load_summary_markdown()
    tweets = db.load_tweet_insights()
    similar_docs_df = db.load_similar_documents()
    # extended_summaries_dict = (
    #     extended_summaries_df.groupby("arxiv_code")[["level", "summary"]]
    #     .apply(lambda g: dict(zip(g["level"], g["summary"])))
    #     .to_dict()
    # )

    papers_df = summaries_df.join(arxiv_df, how="left")
    papers_df = papers_df.join(topics_df, how="left")
    papers_df = papers_df.join(citations_df, how="left")
    papers_df = papers_df.join(recursive_summaries_df, how="left")
    papers_df = papers_df.join(markdown_summaries, how="left")
    papers_df = papers_df.join(tweets, how="left")
    papers_df = papers_df.join(similar_docs_df, how="left")
    # papers_df["extended_summaries"] = papers_df.index.map(extended_summaries_dict)
    papers_df["arxiv_code"] = papers_df.index
    papers_df["url"] = papers_df["arxiv_code"].map(
        lambda l: f"https://arxiv.org/abs/{l}"
    )
    papers_df.sort_values("published", ascending=False, inplace=True)
    return papers_df


def prepare_calendar_data(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Prepares data for the creation of a calendar heatmap."""
    df["published"] = pd.to_datetime(df["published"])
    df_year = df[df["published"].dt.year == int(year)].copy()
    ## publishes dates with zero 'Counts' with full year dates.
    df_year = (
        df_year.set_index("published")
        .reindex(pd.date_range(start=f"{year}-01-01", end=f"{year}-12-31", freq="D"))
        .fillna(0)
        .reset_index()
    )
    df_year.columns = ["published", "Count"]
    df_year["week"] = df_year["published"].dt.isocalendar().week - 1
    df_year["weekday"] = df_year["published"].dt.weekday
    return df_year


@st.cache_data
def load_data():
    """Load data from compiled dataframe."""
    result_df = combine_input_data()

    ## Remapping with emotion.
    classification_map = {
        "TRAINING": "🏋️‍ TRAINING",
        "FINE-TUNING": "🔧 FINE-TUNING",
        "ARCHITECTURES": "⚗️MODELS",
        "BEHAVIOR": "🧠 BEHAVIOR",
        "PROMPTING": "✍️ PROMPTING",
        "USE CASES": "💰 USE CASES",
        "OTHER": "🤷 OTHER",
    }
    ## Round published and updated columns.
    result_df["updated"] = pd.to_datetime(result_df["updated"]).dt.date
    result_df["published"] = pd.to_datetime(result_df["published"].dt.date)
    result_df["category"] = result_df["category"].apply(
        lambda x: classification_map.get(x, "🤷 OTHER")
    )
    result_df[["citation_count", "influential_citation_count"]] = result_df[
        ["citation_count", "influential_citation_count"]
    ].fillna(0)

    return result_df


@st.cache_data
def get_weekly_summary(date: str):
    return db.get_weekly_summary(date)


@st.cache_data
def get_max_report_date():
    max_date = db.get_max_table_date(
        db.db_params,
        "weekly_reviews",
    )
    if max_date.weekday() != 6:
        max_date = max_date + pd.Timedelta(days=6 - max_date.weekday())
    return max_date


@st.cache_data
def generate_calendar_df(df: pd.DataFrame):
    """Daily counts of papers."""
    published_df = df.groupby("published").count()["title"]
    published_df = published_df.reindex(
        pd.date_range(
            start=published_df.index.min(), end=published_df.index.max(), freq="D"
        )
    ).fillna(0)
    published_df = published_df.reset_index()
    published_df.columns = ["published", "Count"]
    return published_df


def get_similar_titles(
    title: str, df: pd.DataFrame, n: int = 5
) -> Tuple[List[str], str]:
    """Return similar titles based on topic cluster."""
    title = title.lower()
    if title in df["title"].str.lower().values:
        cluster = df[df["title"].str.lower() == title]["topic"].values[0]
        similar_df = df[df["topic"] == cluster]
        similar_df = similar_df[similar_df["title"].str.lower() != title]

        size = similar_df.shape[0]
        similar_df = similar_df.sample(min(n, size))

        similar_names = [
            f"{row['title']} (arxiv:{row['arxiv_code']})"
            for index, row in similar_df.iterrows()
        ]
        similar_names = [au.add_links_to_text_blob(title) for title in similar_names]

        return similar_names, cluster
    else:
        return [], ""


@st.cache_data
def get_similar_docs(
    arxiv_code: str, df: pd.DataFrame, n: int = 5
) -> Tuple[List[str], List[str], List[str]]:
    """Get most similar documents based on cosine similarity."""
    if arxiv_code in df.index:
        similar_docs = df.loc[arxiv_code]["similar_docs"]
        similar_docs = [d for d in similar_docs if d in df.index]

        if len(similar_docs) > n:
            similar_docs = np.random.choice(similar_docs, n, replace=False)

        similar_titles = [df.loc[doc]["title"] for doc in similar_docs]
        publish_dates = [df.loc[doc]["published"] for doc in similar_docs]

        return similar_docs, similar_titles, publish_dates
    else:
        return [], [], []


def create_paper_card(paper: Dict, mode="closed", name=""):
    """Creates card UI for paper details."""
    img_cols = st.columns((1, 3))
    expanded = False
    if mode == "open":
        expanded = True
    paper_code = paper["arxiv_code"]
    try:
        # img_cols[0].image(f"imgs/{paper_code}.png", use_column_width=True)
        img_cols[0].image(
            f"https://llmpedia.s3.amazonaws.com/{paper_code}.png", use_column_width=True
        )
    except:
        pass

    paper_title = paper["title"]
    paper_url = paper["url"]
    img_cols[1].markdown(
        f'<h2><a href="{paper_url}" style="color: #FF4B4B;">{paper_title}</a></h2>',
        unsafe_allow_html=True,
    )

    pub_date = pd.to_datetime(paper["published"]).strftime("%B %d, %Y")
    upd_date = pd.to_datetime(paper["updated"]).strftime("%B %d, %Y")
    tweet_insight = paper["tweet_insight"]
    if not pd.isna(tweet_insight):
        tweet_insight = tweet_insight.split("):")[1].strip()
        img_cols[1].markdown(f"🐦 *{tweet_insight}*")
    img_cols[1].markdown(f"#### Published: {pub_date}")
    if pub_date != upd_date:
        img_cols[1].caption(f"Last Updated: {upd_date}")
    img_cols[1].markdown(f"*{paper['authors']}*")
    influential_citations = int(paper["influential_citation_count"])
    postpend = ""
    if influential_citations > 0:
        postpend = f" ({influential_citations} influential)"
    img_cols[1].markdown(f"`{int(paper['citation_count'])} citations {postpend}`")
    arxiv_comment = paper["arxiv_comment"]
    if arxiv_comment:
        img_cols[1].caption(f"*{arxiv_comment}*")

    report_log_space = img_cols[1].empty()
    action_btn_cols = img_cols[1].columns((1, 1, 1))
    report_btn = action_btn_cols[0].popover("🚨 Report")
    if report_btn.checkbox("Report bad image", key=f"report_v1_{paper_code}_{name}"):
        db.report_issue(paper_code, "bad_image")
        report_log_space.success("Reported bad image. Thanks!")
        time.sleep(3)
        report_log_space.empty()
    if report_btn.checkbox("Report bad summary", key=f"report_v2_{paper_code}_{name}"):
        db.report_issue(paper_code, "bad_summary")
        report_log_space.success("Reported bad summary. Thanks!")
        time.sleep(3)
        report_log_space.empty()
    if report_btn.checkbox(
        "Report non-LLM paper", key=f"report_v3_{paper_code}_{name}"
    ):
        db.report_issue(paper_code, "non_llm")
        report_log_space.success("Reported non-LLM paper. Thanks!")
        time.sleep(3)
        report_log_space.empty()

    with st.expander(f"💭 Abstract (arXiv:{paper_code})", expanded=False):
        st.markdown(paper["summary"])

    with st.expander(f"🗒 **Notes**", expanded=True):
        level_select = st.selectbox(
            "Detail",
            ## high-level overview, summary notes, detailed notes
            ["📝 High-Level Overview", "🔎 Detailed Research Notes"],
            label_visibility="collapsed",
            index=0,
            key=f"level_select_{paper_code}{name}",
        )

        # summary = paper["recursive_summary"] if paper["recursive_summary"] else paper["contribution_content"]
        summary = (
            paper["recursive_summary"]
            if not pd.isna(paper["recursive_summary"])
            else paper["contribution_content"]
        )
        markdown_summary = paper["markdown_notes"]

        if level_select == "📝 High-Level Overview":
            st.markdown(summary)
        elif level_select == "🔎 Detailed Research Notes":
            if not pd.isna(markdown_summary):
                markdown_summary = markdown_summary.replace("#", "###")
                st.markdown(markdown_summary)
            else:
                st.markdown("Currently unavailable. Check again soon!")

    with st.expander("👮 **Interrogate** (Chat)", expanded=expanded):
        paper_question = st.text_area(
            "Ask GPT Maestro about this paper.",
            height=100,
            key=f"chat_{paper_code}{name}",
        )
        if st.button("Send", key=f"send_{paper_code}{name}"):
            response = au.interrogate_paper(paper_question, paper_code)
            db.log_qna_db(f"[{paper_code}] ::: {paper_question}", response)
            st.write(response)

    with st.expander("🌟 **GPT Assessments**", expanded=False):
        assessment_cols = st.columns((1, 3, 1, 3, 1, 3))
        assessment_cols[0].metric("Novelty", f"{paper['novelty_score']}/3", "🚀")
        assessment_cols[1].caption(f"{paper['novelty_analysis']}")
        assessment_cols[2].metric(
            "Technical Depth", f"{paper['technical_score']}/3", "🔧"
        )
        assessment_cols[3].caption(f"{paper['technical_analysis']}")
        assessment_cols[4].metric("Readability", f"{paper['enjoyable_score']}/3", "📚")
        assessment_cols[5].caption(f"{paper['enjoyable_analysis']}")

    with st.expander(
        f"✏️ **Takeaways & Applications**:  {paper['takeaway_title']}", expanded=False
    ):
        st.markdown(f"{paper['takeaway_example']}")

    # with st.expander("🥉 **GPT Assessments**", expanded=False):
    #     ## GPT Cluster category.
    #     st.markdown(f"**GPT Cluster Group**: {paper['topic']}")
    #
    #     novelty_cols = st.columns((1, 10))
    #     novelty_cols[0].metric("Novelty", f"{paper['novelty_score']}/3", "🚀")
    #     novelty_cols[1].markdown(f"{paper['novelty_analysis']}")
    #
    #     tech_cols = st.columns((1, 10))
    #     tech_cols[0].metric("Technical Depth", f"{paper['technical_score']}/3", "🔧")
    #     tech_cols[1].markdown(f"{paper['technical_analysis']}")
    #
    #     enjoy_cols = st.columns((1, 10))
    #     enjoy_cols[0].metric("Readability", f"{paper['enjoyable_score']}/3", "📚")
    #     enjoy_cols[1].markdown(f"{paper['enjoyable_analysis']}")

    with st.expander(f"📚 **Similar Papers**", expanded=False):
        papers_df = st.session_state["papers"]
        if paper_code in papers_df.index:
            similar_codes = papers_df.loc[paper_code]["similar_docs"]
            if any(pd.isna(similar_codes)):
                st.write("Not available yet. Check back soon!")
            else:
                similar_codes = [d for d in similar_codes if d in papers_df.index]
                if len(similar_codes) > 5:
                    similar_codes = np.random.choice(similar_codes, 5, replace=False)
                similar_df = papers_df.loc[similar_codes]
                generate_grid_gallery(similar_df, extra_key="_sim", n_cols=5)
            # cols = st.columns(5)
        # for i in range(len(similar_titles)):
        #     try:
        #         cols[i].image(
        #             f"https://llmpedia.s3.amazonaws.com/{similar_codes[i]}.png"
        #         )
        #         centered_date = (
        #             f"<p align='center'><code>{publish_dates[i].strftime('%b %d, %Y')}</code></p>"
        #         )
        #         cols[i].markdown(centered_date, unsafe_allow_html=True)
        #         centered_title = (
        #             f"<p align='center'><small>{similar_titles[i]}</small></p>"
        #         )
        #         cols[i].markdown(centered_title, unsafe_allow_html=True)
        #     except:
        #         pass
    st.markdown("---")


def generate_grid_gallery(df, n_cols=5, extra_key=""):
    """Create streamlit grid gallery of paper cards with thumbnail."""
    n_rows = int(np.ceil(len(df) / n_cols))
    for i in range(n_rows):
        cols = st.columns(n_cols)
        for j in range(n_cols):
            if i * n_cols + j < len(df):
                with cols[j]:
                    try:
                        # st.image(f"imgs/{df.iloc[i*n_cols+j]['arxiv_code']}.png")
                        st.image(
                            f"https://llmpedia.s3.amazonaws.com/{df.iloc[i*n_cols+j]['arxiv_code']}.png"
                        )
                    except:
                        pass
                    paper_url = df.iloc[i * n_cols + j]["url"]
                    paper_title = df.iloc[i * n_cols + j]["title"].replace("\n", "")
                    star_count = (
                        df.iloc[i * n_cols + j]["influential_citation_count"] > 0
                    )
                    publish_date = pd.to_datetime(
                        df.iloc[i * n_cols + j]["published"]
                    ).strftime("%b %d, %Y")
                    star = ""
                    if star_count:
                        star = "⭐️"

                    centered_code = f"""
                    <div class="centered">
                        <code>{star} {publish_date}</code>
                    </div>
                    """
                    st.markdown(centered_code, unsafe_allow_html=True)

                    paper_code = df.iloc[i * n_cols + j]["arxiv_code"]
                    focus_btn = st.button(
                        "Focus",
                        key=f"focus_{paper_code}{extra_key}",
                        use_container_width=True,
                    )
                    if focus_btn:
                        st.session_state.arxiv_code = paper_code
                        click_tab(2)

                    st.markdown(
                        f'<p style="text-align: center"><strong><a href="{paper_url}" style="color: #FF4B4B;">{paper_title}</a></strong></p>',
                        unsafe_allow_html=True,
                    )

                    last_updated = pd.to_datetime(
                        df.iloc[i * n_cols + j]["published"]
                    ).strftime("%b %d, %Y")
                    authors_str = df.iloc[i * n_cols + j]["authors"]
                    authors_str = (
                        authors_str[:30] + "..."
                        if len(authors_str) > 30
                        else authors_str
                    )
                    # st.markdown(authors_str)


def create_pagination(items, items_per_page, label="summaries"):
    num_items = len(items)
    num_pages = num_items // items_per_page
    if num_items % items_per_page != 0:
        num_pages += 1

    st.session_state["num_pages"] = num_pages

    st.markdown(f"**{num_items} items found.**")
    st.markdown(f"**Pg. {st.session_state.page_number + 1} of {num_pages}**")
    prev_button, mid, next_button = st.columns((1, 10, 1))
    prev_clicked = prev_button.button("Prev", key=f"prev_{label}")
    next_clicked = next_button.button("Next", key=f"next_{label}")

    if prev_clicked and "page_number" in st.session_state:
        st.session_state.page_number = max(0, st.session_state.page_number - 1)
    if next_clicked and "page_number" in st.session_state:
        st.session_state.page_number = min(
            num_pages - 1, st.session_state.page_number + 1
        )

    start_index = st.session_state.page_number * items_per_page
    end_index = min(start_index + items_per_page, num_items)

    return items[start_index:end_index]


def create_bottom_navigation(label):
    num_pages = st.session_state["num_pages"]
    st.write(f"**Pg. {st.session_state.page_number + 1} of {num_pages}**")
    prev_button_btm, _, next_button_btm = st.columns((1, 10, 1))
    prev_clicked_btm = prev_button_btm.button("Prev", key=f"prev_{label}_btm")
    next_clicked_btm = next_button_btm.button("Next", key=f"next_{label}_btm")
    if prev_clicked_btm and "page_number" in st.session_state:
        st.session_state.page_number = max(0, st.session_state.page_number - 1)
        st.rerun()
    if next_clicked_btm and "page_number" in st.session_state:
        st.session_state.page_number = min(
            num_pages - 1, st.session_state.page_number + 1
        )
        st.rerun()


def click_tab(tab_num):
    js = f"""
    <script>
        var tabs = window.parent.document.querySelectorAll("[id^='tabs-bui'][id$='-tab-{tab_num}']");
        if (tabs.length > 0) {{
            tabs[0].click();
        }}
    </script>
    """
    st.components.v1.html(js)


def main():
    ## URL info extraction.
    url_query = st.query_params
    if "arxiv_code" in url_query and len(st.session_state.arxiv_code) == 0:
        db.log_visit(url_query["arxiv_code"])
        paper_code = url_query["arxiv_code"]
        st.session_state.arxiv_code = paper_code
        click_tab(2)

    st.markdown(
        """<div class="pixel-font">LLMpedia</div>
    """,
        unsafe_allow_html=True,
    )
    st.markdown("##### The Illustrated Large Language Model Encyclopedia")
    ## Humorous and poetic introduction.
    st.markdown(
        "LLMpedia is a curated collection of key papers on Large Language Models, selected and analyzed by GPT Maestro. "
        " With pixel art and structured summaries, the encyclopedia is designed to guide you through the extensive research on LLMs. "
        "If you have any questions go to the *Chat* section and talk to the Maestro. "
        "And don't forget to follow us [@GPTMaestro](https://twitter.com/GPTMaestro) for the latest updates and paper reviews.\n\n"
        "*Buona lettura!*"
    )

    ## Main content.
    full_papers_df = load_data()
    st.session_state["papers"] = full_papers_df

    ## Filter sidebar.
    st.sidebar.markdown("# 📁 Filters")
    ## Add option to filter by year of select all of them.
    year_cols = st.sidebar.columns((1, 2))
    _ = year_cols[0].markdown("#### Year")
    all_years = year_cols[0].checkbox("All ", value=st.session_state.all_years)
    st.session_state.all_years = all_years

    _ = year_cols[1].markdown("####")
    year = year_cols[1].slider(
        "Year",
        min_value=2016,
        max_value=2024,
        value=2024,
        step=1,
        label_visibility="collapsed",
        disabled=st.session_state.all_years,
    )

    search_term = st.sidebar.text_input("Search", "")
    search_opt_cols = st.sidebar.columns((1, 1))
    title_only = search_opt_cols[0].checkbox("`Title Only`", value=True)
    code_only = search_opt_cols[1].checkbox("`Arxiv Code`", value=False)
    categories = st.sidebar.multiselect(
        "Categories",
        list(full_papers_df["category"].unique()),
    )
    topics = st.sidebar.multiselect(
        "Topic Group",
        list(full_papers_df["topic"].unique()),
    )

    min_citations = st.sidebar.select_slider(
        "Min Citations",
        options=[0, 1, 5, 10, 100],
        value=0,
    )

    ## Sort by.
    sort_by = st.sidebar.selectbox(
        "Sort By",
        ["Published Date", "Last Updated", "Citations", "Random"],
    )

    ## Year filter.
    if not st.session_state.all_years:
        papers_df = full_papers_df[full_papers_df["published"].dt.year == int(year)]
    else:
        papers_df = full_papers_df.copy()

    ## Search terms.
    if len(search_term) > 0 and title_only:
        search_term = search_term.lower()
        papers_df = papers_df[papers_df["title"].str.lower().str.contains(search_term)]
    elif len(search_term) > 0 and code_only:
        search_term = search_term.lower()
        papers_df = papers_df[
            papers_df["arxiv_code"].str.lower().str.contains(search_term)
        ]
        st.session_state.arxiv_code = search_term
    elif len(search_term) > 0:
        search_term = search_term.lower()
        papers_df = papers_df[
            papers_df["title"].str.lower().str.contains(search_term)
            | papers_df["arxiv_code"].str.lower().str.contains(search_term)
            | papers_df["authors"].str.lower().str.contains(search_term)
            | papers_df["summary"].str.lower().str.contains(search_term)
            | papers_df["contribution_title"].str.lower().str.contains(search_term)
            | papers_df["contribution_content"].str.lower().str.contains(search_term)
            | papers_df["takeaway_title"].str.lower().str.contains(search_term)
            | papers_df["takeaway_content"].str.lower().str.contains(search_term)
        ]

    ## Categories.
    if len(categories) > 0:
        papers_df = papers_df[papers_df["category"].isin(categories)]

    # Cluster.
    if len(topics) > 0:
        papers_df = papers_df[papers_df["topic"].isin(topics)]

    ## Citations.
    papers_df = papers_df[papers_df["citation_count"] >= min_citations]

    ## Order.
    if sort_by == "Last Updated":
        papers_df = papers_df.sort_values("updated", ascending=False)
    elif sort_by == "Published Date":
        papers_df = papers_df.sort_values("published", ascending=False)
    elif sort_by == "Citations":
        papers_df = papers_df.sort_values("citation_count", ascending=False)
    elif sort_by == "Random":
        papers_df = papers_df.sample(frac=1)

    if len(papers_df) == 0:
        st.error("No papers found.")
        return

    ## Calendar selector.
    published_df = generate_calendar_df(papers_df)
    if not st.session_state.all_years:
        heatmap_data = prepare_calendar_data(published_df, year)
        release_calendar, padded_date = pt.plot_activity_map(heatmap_data)
        st.markdown(f"### 📅 {year} Release Calendar")
        calendar_select = plotly_events(release_calendar, override_height=220)
        # calendar_select = st.plotly_chart(release_calendar, use_container_width=True, on_select="rerun")
        # st.write(calendar_select)

        # Published date.
        if len(calendar_select) > 0:
            ## Select from padded dates.
            x_coord = 6 - calendar_select[0]["pointNumber"][0]
            y_coord = calendar_select[0]["pointNumber"][1]
            publish_date = pd.to_datetime(
                padded_date.loc[x_coord, y_coord] + f" {year}"
            )

            if len(papers_df[papers_df["published"] == publish_date]) > 0:
                papers_df = papers_df[papers_df["published"] == publish_date]
                ## Add option to clear filter on sidebar.
                if st.sidebar.button(
                    f"📅 **Publish Date Filter:** {publish_date.strftime('%B %d, %Y')}",
                    help="Double click on calendar chart to remove date filter.",
                ):
                    pass

    st.sidebar.markdown(
        """
    <style>
        .reportview-container .main footer {visibility: hidden;}
        .footer {
            position: fixed;
            bottom: 0;
            width: 0%;
            text-align: center;
            color: #888;
            font-size: 0.75rem;
        }
        .footer a {
            color: inherit;
            text-decoration: none;
        }
    </style>
    <div class="footer">
        <a href="https://github.com/masta-g3/llmpedia/blob/main/VERSIONS.md" target="_blank">v1.2.2</a>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if len(papers_df) == 0:
        st.markdown("No papers found.")
        return

    ## Content tabs.
    content_tabs = st.tabs(
        [
            "🧮 Grid View",
            # "🎞 Feed View",
            # "🗒️ Table View",
            "🗺️ Over View",
            "🔍 Focus View",
            "🤖 Chat",
            "🗞 Weekly Report",
        ]
    )

    with content_tabs[0]:
        ## Gried view.
        if "page_number" not in st.session_state:
            st.session_state.page_number = 0

        papers_df_subset = create_pagination(papers_df, items_per_page=25, label="grid")
        generate_grid_gallery(papers_df_subset)
        create_bottom_navigation(label="grid")

    # with content_tabs[1]:
    #     ## Feed view.
    #     if "page_number" not in st.session_state:
    #         st.session_state.page_number = 0
    #
    #     papers_subset = create_pagination(papers, items_per_page=7, label="summaries")
    #     st.markdown(f"**{len(papers)} papers found.**")
    #     for paper in papers_subset:
    #         create_paper_card(paper, mode="closed", name="_feed")
    #     create_bottom_navigation(label="summaries")

    # with content_tabs[1]:
    #     ## Table view.
    #     display_df = papers_df.reset_index(drop=True)
    #     # https://llmpedia.s3.amazonaws.com/2403.14624.png
    #     display_df["display_url"] = display_df["arxiv_code"].map(
    #         lambda l: f"https://llmpedia.s3.amazonaws.com/{l}.png"
    #     )
    #     column_config = {
    #         "url": st.column_config.LinkColumn(
    #             label="Arxiv Link",
    #             display_text="https://arxiv\.org/abs/(.*?)(?:v\d+)?$",
    #         ),
    #         "display_url": st.column_config.ImageColumn(
    #             label="Artwork",
    #         ),
    #         "published": st.column_config.DateColumn(
    #             label="Published",
    #             format="MMM DD, YYYY",
    #             # width="small",
    #         ),
    #         "title": st.column_config.TextColumn(
    #             label="Title",
    #             width="large",
    #         ),
    #         "topic": st.column_config.TextColumn(
    #             label="Topic",
    #             width="large",
    #         ),
    #         "citation_count": "Citations",
    #         "influential_citation_count": "⭐️Influential Citations",
    #     }
    #     display_cols = [
    #         "display_url",
    #         "published",
    #         "title",
    #         "citation_count",
    #         "influential_citation_count",
    #         "topic",
    #     ]
    #     display_df = display_df[column_config.keys()]
    #     st.dataframe(
    #         display_df,
    #         column_config=column_config,
    #         hide_index=True,
    #         use_container_width=True,
    #     )

    with content_tabs[1]:
        ## Over view.
        total_papers = len(papers_df)
        st.markdown(f"### 📈 Total Publication Counts: {total_papers}")
        plot_type = st.radio(
            label="Plot Type",
            options=["Daily", "Cumulative"],
            index=1,
            label_visibility="collapsed",
            horizontal=True,
        )
        cumulative = plot_type == "Cumulative"
        ts_plot = pt.plot_publication_counts(papers_df, cumulative=cumulative)
        st.plotly_chart(ts_plot, use_container_width=True)

        ## Cluster map.
        st.markdown(f"### {year} Topic Model Map")
        cluster_map = pt.plot_cluster_map(papers_df)
        st.plotly_chart(cluster_map, use_container_width=True)

    with content_tabs[2]:
        ## Focus on a paper.
        arxiv_code = st.text_input("arXiv Code", st.session_state.arxiv_code)
        st.session_state.arxiv_code = arxiv_code
        if len(arxiv_code) > 0:
            if arxiv_code in full_papers_df.index:
                paper = full_papers_df.loc[arxiv_code].to_dict()
                create_paper_card(paper, mode="open", name="_focus")
            else:
                st.error("Paper not found.")

    with content_tabs[3]:
        st.markdown("##### 🤖 Chat with the GPT maestro.")
        config_cols = st.columns((3, 3, 10))
        # embedding_name = config_cols[0]._selectbox(
        #     label="Embeddings",
        #     options=["GTE-Large", "🆕 Cohere V3"],
        #     index=1,
        # )
        embedding_name = "🆕 Cohere V3"

        # llm_name = config_cols[1]._selectbox(
        #     label="LLM", options=["GPT-3.5-Turbo", "GPT-4"]
        # )

        collection_name = collection_map[embedding_name]
        user_question = st.text_area(
            label="Ask any question about LLMs or the arxiv papers.", value=""
        )
        chat_btn_disabled = len(user_question) == 0
        chat_cols = st.columns((1, 2, 1))
        chat_btn = chat_cols[0].button("Send", disabled=chat_btn_disabled)
        # response_length = chat_cols[2].select_slider(
        #     "Response Length",
        #     options=["Short Answer", "Normal"],
        #     value="Short Answer",
        #     label_visibility="collapsed",
        # )
        response_length = "Short Answer"
        if chat_btn:
            if user_question != "":
                with st.spinner(
                    "Consulting the GPT maestro, this might take a minute..."
                ):
                    response = au.query_llmpedia_new(
                        user_question,
                        response_length,  # , collection_name, model="claude-haiku"
                    )
                    db.log_qna_db(user_question, response)
                    st.divider()
                    st.markdown(response)

    with content_tabs[4]:
        report_top_cols = st.columns((5, 2))
        with report_top_cols[0]:
            st.markdown("# 📰 LLM Weekly Review")
        with report_top_cols[1]:
            max_date = get_max_report_date()
            week_select = st.date_input(
                "Select Week",
                value=pd.to_datetime(max_date),
                min_value=pd.to_datetime("2023-01-01"),
                max_value=pd.to_datetime(max_date),
            )
            ## convert selection to previous monday.
            date_report = week_select - pd.Timedelta(days=week_select.weekday())

        weekly_report = get_weekly_summary(date_report)
        try:
            weekly_report_dict = json.loads(weekly_report)
            weekly_report_dict = {
                au.report_sections_map[k]: au.add_links_to_text_blob(v)
                for k, v in weekly_report_dict.items()
            }
            report_sections = list(weekly_report_dict.keys())[1:]
            title = f"###### *({date_report.strftime('%B %d, %Y')} to {(date_report + pd.Timedelta(days=6)).strftime('%B %d, %Y')})*"
        except:
            weekly_report_dict = au.parse_weekly_report(weekly_report)
            report_sections = list(weekly_report_dict.keys())[1:]
            title = list(weekly_report_dict.keys())[0]

        ## Title & developments.
        title = title.replace("# Weekly Review ", "##### ")
        st.markdown(f"{title}")
        st.markdown(f"## 🔬 {report_sections[0]}")
        st.markdown(weekly_report_dict[report_sections[0]])

        ## Highlights.
        st.markdown(f"## 🌟 {report_sections[1]}")
        report_highlights_cols = st.columns((1, 4))
        highlight_img = au.get_img_link_for_blob(weekly_report_dict[report_sections[1]])
        report_highlights_cols[0].image(highlight_img, use_column_width=True)
        report_highlights_cols[1].markdown(weekly_report_dict[report_sections[1]])

        ## Repos (optional).
        if len(report_sections) > 2:
            st.markdown(f"## 💿 {report_sections[2]}")
            st.markdown(weekly_report_dict[report_sections[2]])


if __name__ == "__main__":
    try:
      main()
    except Exception as e:
        db.log_error_db(e)
        st.error("Something went wrong. Please refresh the app and try again.")
