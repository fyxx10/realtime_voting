import time  # For time-related functions
import pandas as pd  # For data manipulation and analysis
import simplejson as json  # For JSON manipulation
import streamlit as st  # For creating web applications
from kafka import KafkaConsumer  # Kafka consumer for receiving messages
from streamlit_autorefresh import st_autorefresh  # For auto-refreshing Streamlit app
import psycopg2  # PostgreSQL database adapter for Python
import plotly.express as px  # For creating plots
import plotly.graph_objects as go  # For creating more complex plots

# Initialize session state variables for total votes
if 'total_votes' not in st.session_state:
    st.session_state['total_votes'] = 0

# Function to create a Kafka consumer
def create_kafka_consumer(topic_name):
    # Set up a Kafka consumer with specified topic and configurations
    consumer = KafkaConsumer(
        topic_name,
        bootstrap_servers='localhost:9092',
        auto_offset_reset='earliest',
        value_deserializer=lambda x: json.loads(x.decode('utf-8')))
    return consumer

# Function to fetch voting statistics from PostgreSQL database
@st.cache_data
def fetch_voting_stats():
    # Connect to PostgreSQL database
    conn = psycopg2.connect("host=localhost dbname=election_db user=postgres password=postgres port=5433")
    cur = conn.cursor()

    # Fetch total number of voters
    cur.execute("""
        SELECT count(*) voters_count FROM voters
    """)
    voters_count = cur.fetchone()[0]

    # Fetch total number of candidates
    cur.execute("""
        SELECT count(*) candidates_count FROM candidates
    """)
    candidates_count = cur.fetchone()[0]

    return voters_count, candidates_count

# Function to fetch data from Kafka
def fetch_data_from_kafka(consumer):
    # Poll Kafka consumer for messages within a timeout period
    messages = consumer.poll(timeout_ms=1000)
    data = []

    # Extract data from received messages
    for message in messages.values():
        for sub_message in message:
            data.append(sub_message.value)
    return data

# Function to aggregate votes per candidate
def aggregate_votes(data):
    df = pd.DataFrame(data)
    aggregated_data = df.groupby(['candidate_id', 'candidate_name', 'party_affiliation']).size().reset_index(name='total_votes')
    return aggregated_data

# Function to plot a bar chart for vote counts per candidate using Plotly
def plot_colored_bar_chart(results):
    fig = px.bar(results, x='candidate_name', y='total_votes', color='candidate_name',
                 labels={'candidate_name': 'Candidate', 'total_votes': 'Total Votes'},
                 title='Vote Counts per Candidate')
    fig.update_layout(xaxis_title='Candidate', yaxis_title='Total Votes')
    return fig

# Function to plot a donut chart for vote distribution using Plotly
def plot_donut_chart(data: pd.DataFrame, title='Donut Chart', type='candidate'):
    if type == 'candidate':
        labels = data['candidate_name']
    elif type == 'gender':
        labels = data['gender']
    sizes = data['total_votes']
    fig = go.Figure(data=[go.Pie(labels=labels, values=sizes, hole=.3)])
    fig.update_layout(title_text=title)
    return fig

# Function to update data displayed on the dashboard
def update_data():
    # Placeholder to display last refresh time
    last_refresh = st.empty()
    last_refresh.text(f"Last refreshed at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Fetch voting statistics
    voters_count, candidates_count = fetch_voting_stats()

    # Fetch data from Kafka on votes
    consumer = create_kafka_consumer("votes_topic")
    data = fetch_data_from_kafka(consumer)

    # Update total votes count in session state
    st.session_state['total_votes'] = len(data)

    # Display total voters and candidates metrics
    st.markdown("""---""")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Voters", voters_count)
    col2.metric("Total Candidates", candidates_count)
    col3.metric("Total Votes", st.session_state['total_votes'])

    # Aggregate votes
    aggregated_data = aggregate_votes(data)

    # Identify the leading candidate
    if not aggregated_data.empty:
        leading_candidate = aggregated_data.loc[aggregated_data['total_votes'].idxmax()]

        # Display leading candidate information
        st.markdown("""---""")
        st.header('Leading Candidate')
        col1, col2 = st.columns(2)
        with col1:
            if 'photo_url' in leading_candidate:
                st.image(leading_candidate['photo_url'], width=200)
            else:
                st.write("No photo available")
        with col2:
            st.header(leading_candidate['candidate_name'])
            st.subheader(leading_candidate['party_affiliation'])
            st.subheader("Total Vote: {}".format(leading_candidate['total_votes']))

    # Display statistics and visualizations
    st.markdown("""---""")
    st.header('Statistics')
    
    # Display table with candidate statistics
    st.table(aggregated_data)

    # Display bar chart and donut chart
    bar_fig = plot_colored_bar_chart(aggregated_data)
    st.plotly_chart(bar_fig)

    donut_fig = plot_donut_chart(aggregated_data, title='Vote Distribution')
    st.plotly_chart(donut_fig)

    # Update the last refresh time
    st.session_state['last_update'] = time.time()

# Sidebar layout
def sidebar():
    # Initialize last update time if not present in session state
    if st.session_state.get('last_update') is None:
        st.session_state['last_update'] = time.time()

    # Slider to control refresh interval
    refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 5, 60, 10)
    st_autorefresh(interval=refresh_interval * 1000, key="auto")

    # Button to manually refresh data
    if st.sidebar.button('Refresh Data'):
        update_data()

# Title of the Streamlit dashboard
st.title(':green[Real-time Election Dashboard]')

# Display sidebar
sidebar()

# Update and display data on the dashboard
update_data()
